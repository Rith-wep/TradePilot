import hashlib
import json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tradepilot.data.dukascopy_batch import BATCH_PLAN_VERSION


FORMAT = "%Y-%m-%dT%H:%M:%S%z"
HEADER = "Etc/UTC,Open,High,Low,Close,Volume\n"


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_batch_plan(root: Path, *, instrument="EURUSD", changed=False, gap=False, bad_hash=False):
    months = ((2024, 1, 2), (2024, 2, 1))
    entries = []
    allowed_dates = {date(year, month, day) for year, month, day in months}
    closures = []
    for year, month, _ in months:
        for day in range(1, monthrange(year, month)[1] + 1):
            value = date(year, month, day)
            if value not in allowed_dates:
                closures.append(value.isoformat())
    for month_index, (year, month, day) in enumerate(months):
        label = f"{year:04d}-{month:02d}"
        bid = root / f"{instrument}_{label}_BID.csv"
        ask = root / f"{instrument}_{label}_ASK.csv"
        bid_rows = []
        ask_rows = []
        for hour in range(24):
            if gap and month_index == 1 and hour == 12:
                continue
            stamp = datetime(year, month, day, hour, tzinfo=timezone.utc).isoformat()
            close = "1.10060" if changed and month_index == 0 and hour == 0 else "1.10050"
            ask_close = "1.10080" if changed and month_index == 0 and hour == 0 else "1.10070"
            bid_rows.append(f"{stamp},1.10000,1.10100,1.09950,{close},100\n")
            ask_rows.append(f"{stamp},1.10020,1.10120,1.09970,{ask_close},90\n")
        bid.write_text(HEADER + "".join(bid_rows), encoding="utf-8")
        ask.write_text(HEADER + "".join(ask_rows), encoding="utf-8")
        entries.append({
            "month": label, "bid_path": bid.name, "ask_path": ask.name,
            "bid_sha256": "0" * 64 if bad_hash and month_index == 1 else _hash(bid),
            "ask_sha256": _hash(ask),
        })
    payload = {
        "schema_version": BATCH_PLAN_VERSION,
        "instrument": instrument,
        "timeframe": "H1",
        "timestamp_format": FORMAT,
        "delimiter": ",",
        "calendar": {
            "timezone": "UTC", "open_weekday": 0, "open_time": "00:00",
            "close_weekday": 6, "close_time": "23:59",
            "closure_dates": sorted(set(closures)), "name": "synthetic-month-calendar",
        },
        "months": entries,
    }
    plan = root / f"{instrument}-plan.json"
    plan.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return plan
