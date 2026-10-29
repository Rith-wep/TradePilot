"""Credential-gated OANDA real-data readiness orchestration."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from tradepilot.data.connectivity import verify_connectivity
from tradepilot.data.ingestion import HistoricalIngestor, IngestionConfig, IngestionError
from tradepilot.data.integrity import verify_dataset
from tradepilot.data.models import Instrument
from tradepilot.data.providers.oanda import OandaMarketDataProvider, OandaProviderConfig
from tradepilot.data.readiness import ReadinessPolicy, ReadinessStatus, build_readiness_report
from tradepilot.data.readiness_storage import ReadinessReportStore, ReadinessStorageError
from tradepilot.data.sessions import WeeklySessionCalendar
from tradepilot.data.storage import ParquetDatasetStore, StorageError
from tradepilot.core.canonical import canonical_value
from tradepilot.workflows.real_data_readiness import (
    ReportStorageError,
    resolve_implementation_revision,
    verify_candidate_pipeline,
)


INSTRUMENTS = (
    Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5),
    Instrument("GBPUSD", "GBP", "USD", Decimal("0.0001"), 5),
)


def _utc_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0) or parsed.minute or parsed.second or parsed.microsecond:
        raise argparse.ArgumentTypeError("timestamp must be a UTC hour ending in Z")
    return parsed


def _calendar() -> WeeklySessionCalendar:
    # Common OANDA/New York trading week; holidays remain explicit future policy input.
    from datetime import time
    return WeeklySessionCalendar(
        "America/New_York", 6, time(17), 4, time(17), frozenset(), "oanda-fx-week",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify OANDA real-data research readiness")
    sub = parser.add_subparsers(dest="command", required=True)
    connection = sub.add_parser("connectivity")
    connection.add_argument("--environment", choices=("practice", "live"), default="practice")
    run = sub.add_parser("run")
    run.add_argument("--start", required=True, type=_utc_hour)
    run.add_argument("--end", required=True, type=_utc_hour)
    run.add_argument("--environment", choices=("practice", "live"), default="practice")
    run.add_argument("--data-output", type=Path, default=Path("data"))
    run.add_argument("--report-output", type=Path, default=Path("reports"))
    run.add_argument("--readiness-output", type=Path, default=Path("readiness-reports"))
    run.add_argument("--minimum-candles", type=int, default=200)
    run.add_argument("--minimum-coverage", default="0.99")
    run.add_argument("--approve-revisions", action="store_true")
    run.add_argument("--max-range-days", type=int, default=31)
    run.add_argument("--requests-per-second", type=float, default=2.0)
    run.add_argument("--timeout", type=float, default=30.0)
    run.add_argument("--max-retries", type=int, default=3)
    return parser


def _provider(args) -> OandaMarketDataProvider | None:
    token = os.environ.get("OANDA_API_TOKEN", "")
    account = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not account:
        return None
    return OandaMarketDataProvider(
        token, account,
        config=OandaProviderConfig(
            environment=args.environment,
            requests_per_second=getattr(args, "requests_per_second", 2.0),
        ),
    )


def _connectivity(provider, start, end) -> tuple[dict[str, object], ...]:
    return tuple(canonical_value(verify_connectivity(provider, item, start, end)) for item in INSTRUMENTS)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = _provider(args)
    if provider is None:
        print(json.dumps({"status": "FAILED", "error_code": "MISSING_CREDENTIALS"}, sort_keys=True))
        return 2
    now_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if args.command == "connectivity":
        results = _connectivity(provider, now_hour - timedelta(hours=3), now_hour)
        ready = all(item["connected"] for item in results)
        print(json.dumps({"status": "READY" if ready else "FAILED", "connectivity": results}, indent=2, sort_keys=True))
        return 0 if ready else 1

    if args.max_range_days <= 0 or args.end - args.start > timedelta(days=args.max_range_days):
        print(json.dumps({"status": "FAILED", "error_code": "UNBOUNDED_RANGE"}, sort_keys=True))
        return 2
    if args.end > now_hour:
        print(json.dumps({"status": "FAILED", "error_code": "INCOMPLETE_RANGE"}, sort_keys=True))
        return 2
    connectivity = _connectivity(provider, max(args.start, args.end - timedelta(hours=3)), args.end)
    if not all(item["connected"] for item in connectivity):
        print(json.dumps({"status": "FAILED", "error_code": "CONNECTIVITY_FAILED", "connectivity": connectivity}, sort_keys=True))
        return 1

    calendar = _calendar()
    policy = ReadinessPolicy(
        minimum_candles=args.minimum_candles,
        minimum_coverage=Decimal(args.minimum_coverage),
    )
    store = ParquetDatasetStore(args.data_output)
    ingestor = HistoricalIngestor(
        provider, store,
        config=IngestionConfig(
            batch_duration=timedelta(days=min(args.max_range_days, 31)),
            request_timeout_seconds=args.timeout, max_retries=args.max_retries,
        ),
    )
    revision = resolve_implementation_revision(Path.cwd())
    outputs = []
    exit_code = 0
    for instrument in INSTRUMENTS:
        previous_id = store.latest_dataset_id(provider.name, instrument, "H1")
        try:
            ingestion = ingestor.ingest(
                instrument, "H1", args.start, args.end,
                allow_revisions=args.approve_revisions,
            )
            integrity = verify_dataset(ingestion.stored.snapshot_path)
            preliminary = build_readiness_report(
                integrity, requested_start=args.start, requested_end=args.end,
                calendar=calendar, policy=policy, previous_dataset_id=previous_id,
                revisions=ingestion.stored.revisions,
                revisions_approved=args.approve_revisions,
            )
            evidence = ()
            if preliminary.content.status is ReadinessStatus.READY:
                try:
                    evidence = verify_candidate_pipeline(
                        integrity, calendar, args.report_output / instrument.symbol,
                        implementation_revision=revision, created_at=datetime.now(timezone.utc),
                    )
                except (ValueError, ReportStorageError):
                    # The final report records PIPELINE_NOT_VERIFIED and remains deterministic.
                    evidence = ()
            report = build_readiness_report(
                integrity, requested_start=args.start, requested_end=args.end,
                calendar=calendar, policy=policy, previous_dataset_id=previous_id,
                revisions=ingestion.stored.revisions,
                revisions_approved=args.approve_revisions, pipeline=evidence,
                pipeline_required=True,
            )
            stored = ReadinessReportStore(args.readiness_output).save(report)
            outputs.append({
                "instrument": instrument.symbol, "status": report.content.status.value,
                "dataset_id": integrity.dataset_id, "readiness_report_id": report.report_id,
                "readiness_path": str(stored.path), "pipeline": canonical_value(evidence),
            })
            if report.content.status is ReadinessStatus.FAILED:
                exit_code = 1
        except (IngestionError, StorageError, ReadinessStorageError, ValueError) as exc:
            code = "UNAPPROVED_REVISIONS" if "conflicting candle" in str(exc) and not args.approve_revisions else "INGESTION_FAILED"
            outputs.append({"instrument": instrument.symbol, "status": "FAILED", "error_code": code, "error": str(exc)})
            exit_code = 1
    print(json.dumps({"status": "READY" if exit_code == 0 else "FAILED", "instruments": outputs}, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
