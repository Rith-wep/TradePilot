import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from reporting_helpers import create_context
from tradepilot.reporting.cli import main


class ReportCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.datasets = tempfile.TemporaryDirectory()
        self.reports = tempfile.TemporaryDirectory()
        self.addCleanup(self.datasets.cleanup)
        self.addCleanup(self.reports.cleanup)
        self.root, *_ = create_context(self.datasets.name)

    def generate(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"TRADEPILOT_IMPLEMENTATION_REVISION": "test-revision"}), contextlib.redirect_stdout(output):
            exit_code = main([
                "generate", str(self.root), "breakout", "--lookback", "2",
                "--output", self.reports.name,
            ])
        return exit_code, json.loads(output.getvalue())

    def test_cli_generation_reproducibility_and_verification(self) -> None:
        first_code, first = self.generate()
        second_code, second = self.generate()
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first["report_id"], second["report_id"])
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["implementation_revision"], "test-revision")
        verify_output = io.StringIO()
        with contextlib.redirect_stdout(verify_output):
            verify_code = main(["verify", str(first["report_path"])])
        verification = json.loads(verify_output.getvalue())
        self.assertEqual(verify_code, 0)
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["signal_count"], 1)

    def test_cli_verification_detects_corruption(self) -> None:
        _, generated = self.generate()
        with open(generated["report_path"], "w", encoding="utf-8") as handle:
            handle.write("corrupt")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["verify", generated["report_path"]])
        self.assertEqual(exit_code, 1)
        self.assertFalse(json.loads(output.getvalue())["valid"])


if __name__ == "__main__":
    unittest.main()
