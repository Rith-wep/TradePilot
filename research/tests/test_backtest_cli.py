import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from reporting_helpers import build_run, create_context
from tradepilot.backtesting.cli import main
from tradepilot.reporting.storage import ReportStorage


class BacktestCliTests(unittest.TestCase):
    def test_cli_loads_verified_inputs_and_prints_deterministic_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, integrity, calendar, config, strategy, fingerprint, setups = create_context(directory)
            run = build_run(integrity, calendar, config, strategy, fingerprint, setups)
            stored = ReportStorage(directory + "/reports").save(run)
            args = [
                str(root), str(stored.report_path.parent),
                "--entry-expiry-hours", "2", "--max-holding-candles", "1",
            ]
            with patch.dict("os.environ", {"TRADEPILOT_IMPLEMENTATION_REVISION": "cli-test"}):
                first_output = io.StringIO()
                with redirect_stdout(first_output):
                    first_code = main(args)
                second_output = io.StringIO()
                with redirect_stdout(second_output):
                    second_code = main(args)
            self.assertEqual((first_code, second_code), (0, 0))
            first = json.loads(first_output.getvalue())
            second = json.loads(second_output.getvalue())
            self.assertEqual(first, second)
            self.assertIn("audit_log", first)
            self.assertNotIn("profit", first)


if __name__ == "__main__":
    unittest.main()
