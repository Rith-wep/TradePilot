"""Golden compatibility tests for externally meaningful content identities.

Expected bytes and hashes are deliberately literal. Never replace these
constants by values calculated from the implementation inside an assertion.
An intentional identity change requires explicit migration review.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from accounting_helpers import accounting_context
from ingestion_helpers import EURUSD, raw_candle
from reporting_helpers import build_run, create_context
from simulator_helpers import build_context
from validation_helpers import candles, evaluation
from tradepilot.accounting.engine import build_accounting
from tradepilot.backtesting.simulator import EventDrivenSimulator
from tradepilot.data.models import Instrument
from tradepilot.data.normalization import normalize_provider_candle
from tradepilot.data.providers.dukascopy_csv import DukascopyCsvMarketDataProvider
from tradepilot.data.source_artifacts import (
    SOURCE_ARTIFACT_SCHEMA_VERSION,
    SourceArtifact,
    SourceArtifactManifest,
)
from tradepilot.data.storage import canonical_dataset_checksum, dataset_identifier
from tradepilot.reporting.canonical import canonical_json_bytes, sha256_hex
from tradepilot.reporting.storage import report_identifier
from tradepilot.validation.models import (
    VALIDATION_MODEL_VERSION,
    BootstrapInterval,
    UncertaintyStatus,
    ValidationContent,
)
from tradepilot.validation.parameters import select_configuration
from tradepilot.validation.partition_governance import publish_sealed_partitions
from tradepilot.validation.partitions import chronological_partitions
from tradepilot.validation.reporting import build_validation_report
from tradepilot.validation.robustness import summarize_robustness


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class IdentityGoldenTests(unittest.TestCase):
    def test_canonical_json_bytes_decimal_and_checksum_are_stable(self):
        payload = {
            "amount": Decimal("1.2300"),
            "precise": Decimal("1.1234567890123456789012345678901234"),
            "timestamp": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "flag": True,
        }
        expected = (
            b'{"amount":"1.2300","flag":true,'
            b'"precise":"1.1234567890123456789012345678901234",'
            b'"timestamp":"2024-01-02T03:04:05Z"}'
        )
        self.assertEqual(canonical_json_bytes(payload), expected)
        self.assertEqual(
            sha256_hex(expected),
            "7d60aff5bc717f814150400c715e6de51f3162b79496a57219097d7f72839196",
        )

    def test_legacy_dataset_identity_is_stable(self):
        values = tuple(
            normalize_provider_candle(
                raw_candle(index),
                instrument=EURUSD,
                provider="mock",
                dataset_version="mock-v1",
                is_synthetic=True,
            )
            for index in range(2)
        )
        self.assertEqual(
            canonical_dataset_checksum(values),
            "6a2c92b8b22cd2fb4388a3988e54a90e5a5f5465dda3acf56d5ba2dc14e04d76",
        )
        self.assertEqual(
            dataset_identifier(values, EURUSD, "H1"),
            "849717bac80d133247f31b61f7ce035fea23729a01eef2f1cf365ddbc6cb5048",
        )

    def test_batch_dataset_and_source_provenance_identity_are_stable(self):
        bid = FIXTURES / "dukascopy" / "eurusd_h1_bid.csv"
        ask = FIXTURES / "dukascopy" / "eurusd_h1_ask.csv"
        bid_hash = "89f1043ab29112380578d48d335fb653b262e27f598727b036306e734d5b8828"
        ask_hash = "85841b3c415ae09fef3478c1880fa2dae9bf97c665229c824cc239837ee34c78"
        provider = DukascopyCsvMarketDataProvider(
            bid,
            ask,
            timestamp_format="%Y-%m-%dT%H:%M:%S%z",
            expected_bid_sha256=bid_hash,
            expected_ask_sha256=ask_hash,
            is_synthetic=True,
        )
        instrument = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
        values = tuple(
            normalize_provider_candle(
                item,
                instrument=instrument,
                provider="dukascopy-csv-batch",
                dataset_version="fixture-v1",
                is_synthetic=True,
            )
            for item in provider.candles
        )
        artifacts = SourceArtifactManifest(
            SOURCE_ARTIFACT_SCHEMA_VERSION,
            "EURUSD",
            "H1",
            "%Y-%m-%dT%H:%M:%S%z",
            ",",
            "golden-fixture-calendar",
            (
                SourceArtifact(
                    "2024-01", "BID", bid.name, bid_hash, 221, 3,
                    values[0].timestamp, values[-1].timestamp,
                ),
                SourceArtifact(
                    "2024-01", "ASK", ask.name, ask_hash, 220, 3,
                    values[0].timestamp, values[-1].timestamp,
                ),
            ),
        )
        self.assertEqual(
            canonical_dataset_checksum(values),
            "a5267ba1e2b2a64a08c5d2377b29c02f18c0ce745326de1441b89d947c579076",
        )
        self.assertEqual(
            artifacts.checksum,
            "029713a191f4fcde538a562d236080a80836305da41df668bbccbce276bd5c55",
        )
        self.assertEqual(
            dataset_identifier(values, instrument, "H1", artifacts.checksum),
            "5247c04c7b256575c4b093b61daa15ab4c11daafb0c6dd513e01de710a66a559",
        )

    def test_candidate_report_identity_is_stable(self):
        with tempfile.TemporaryDirectory() as root:
            _, integrity, calendar, config, strategy, fingerprint, setups = create_context(root)
            run = build_run(integrity, calendar, config, strategy, fingerprint, setups)
        self.assertEqual(
            report_identifier(run.content),
            "77fd547c8dd00072b9479140ae689586d5f921c0ecf45afb91e2940962b436ad",
        )

    def test_simulation_identity_is_stable(self):
        result = EventDrivenSimulator().run(*build_context(stop_pips="10", target_pips="20"))
        self.assertEqual(
            result.configuration_id,
            "1fb450e84cbbcbb5b7f07fa30a01efcb445d134bafc1a750b78ca007ded71fc8",
        )
        self.assertEqual(
            result.simulation_id,
            "911f10222568cada189e58807c43e2c55313af2e9e82fc346ff7f8cf3b8e653a",
        )
        self.assertEqual(
            sha256_hex(canonical_json_bytes(result)),
            "45d6117e5ce4bedaf3b3f994a609e2ff04ce9df18bbddbeb80c773dcf58f0b44",
        )

    def test_accounting_identity_is_stable(self):
        simulation, simulation_config, accounting_config = accounting_context(
            stop_pips="10", holding=2,
        )
        report = build_accounting(simulation, simulation_config, accounting_config)
        self.assertEqual(
            report.report_id,
            "ef73b8e0444062e84ccfa7e76335d6f238d77d94ba4538e771c169346cb9b976",
        )

    def test_validation_identity_is_stable(self):
        item = evaluation()
        robustness = summarize_robustness((item,))
        content = ValidationContent(
            VALIDATION_MODEL_VERSION,
            "a" * 64,
            "b" * 64,
            "strategy",
            "1.0.0",
            "revision",
            (),
            (),
            (item.configuration,),
            (item,),
            select_configuration((item,)),
            None,
            None,
            robustness,
            BootstrapInterval(
                UncertaintyStatus.DEFINED, Decimal("-1"), Decimal("2"), 30, 5, 1000,
            ),
            ("SYNTHETIC_DATA_ONLY",),
        )
        self.assertEqual(
            build_validation_report(content).report_id,
            "0588e186ceb2145e7ac77bbcfedac25c2b6e2dbb97dbea1f81647f5843caa26b",
        )

    def test_partition_and_sealed_plan_identities_are_stable(self):
        partitions = chronological_partitions(candles(100), "a" * 64)
        self.assertEqual(
            tuple(item.partition_id for item in partitions),
            (
                "6523114ae7f790d61fe139da8b9db07d18a3321d0217417f126a5cdfd3a33abc",
                "feaa723ce97fbe03cb448fca212dcde91d0af929fd5552b4ef53ccd3b27f59ee",
                "aa7cbcfebc5c1a2d23b8186b878d6f1599c5fdde7b06f9fb493479b0f682a5d4",
            ),
        )
        with tempfile.TemporaryDirectory() as root:
            plan = publish_sealed_partitions(
                root,
                dataset_id="a" * 64,
                dataset_checksum="b" * 64,
                partitions=partitions,
            )
        self.assertEqual(
            plan.plan_id,
            "93b180d354a1f86ecce4751b3c797e40711b575f070d130fbea9d248a52e6e85",
        )


if __name__ == "__main__":
    unittest.main()
