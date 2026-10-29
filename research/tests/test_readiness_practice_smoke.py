import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tradepilot.data.readiness_cli import main


@unittest.skipUnless(
    os.environ.get("TRADEPILOT_RUN_OANDA_SMOKE") == "1",
    "credential-gated OANDA readiness smoke test",
)
class ReadinessPracticeSmokeTests(unittest.TestCase):
    def test_two_instrument_readiness(self):
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=14)
        with tempfile.TemporaryDirectory() as root:
            result = main((
                "run", "--start", start.isoformat().replace("+00:00", "Z"),
                "--end", end.isoformat().replace("+00:00", "Z"),
                "--data-output", f"{root}/data", "--report-output", f"{root}/reports",
                "--readiness-output", f"{root}/readiness", "--minimum-candles", "100",
                "--minimum-coverage", "0.95",
            ))
        self.assertEqual(result, 0)


if __name__ == "__main__": unittest.main()
