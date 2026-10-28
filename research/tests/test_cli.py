import contextlib
import io
import json
import unittest
from pathlib import Path

from tradepilot.data.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_cli_prints_valid_json_report(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(ROOT / "fixtures/synthetic_eurusd_h1.csv")])
        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(report["valid"])
        self.assertEqual(report["candle_count"], 5)

    def test_cli_returns_load_error_for_missing_file(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main([str(ROOT / "fixtures/missing.csv")])
        self.assertEqual(exit_code, 2)
        self.assertFalse(json.loads(output.getvalue())["valid"])


if __name__ == "__main__":
    unittest.main()
