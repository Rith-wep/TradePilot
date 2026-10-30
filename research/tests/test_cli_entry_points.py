import importlib
import tomllib
import unittest
from pathlib import Path


EXPECTED_ENTRY_POINTS = {
    "tradepilot-validate": "tradepilot.data.cli:main",
    "tradepilot-ingest-mock": "tradepilot.data.ingestion_cli:main",
    "tradepilot-ingest-oanda": "tradepilot.data.oanda_ingestion_cli:main",
    "tradepilot-oanda-readiness": "tradepilot.data.readiness_cli:main",
    "tradepilot-import-dukascopy": "tradepilot.data.dukascopy_csv_cli:main",
    "tradepilot-import-dukascopy-batch": "tradepilot.data.dukascopy_batch_cli:main",
    "tradepilot-audit": "tradepilot.data.audit_cli:main",
    "tradepilot-indicators": "tradepilot.indicators.cli:main",
    "tradepilot-strategy": "tradepilot.strategies.cli:main",
    "tradepilot-research-report": "tradepilot.reporting.cli:main",
    "tradepilot-backtest": "tradepilot.backtesting.cli:main",
}


class CliEntryPointTests(unittest.TestCase):
    def test_all_documented_commands_are_configured_and_importable(self) -> None:
        pyproject = Path(__file__).parents[1] / "pyproject.toml"
        with pyproject.open("rb") as stream:
            configured = tomllib.load(stream)["project"]["scripts"]

        self.assertEqual(configured, EXPECTED_ENTRY_POINTS)
        for target in configured.values():
            module_name, callable_name = target.split(":", maxsplit=1)
            entry = getattr(importlib.import_module(module_name), callable_name)
            self.assertTrue(callable(entry), target)

        command_reference = (
            Path(__file__).parents[2] / "docs" / "development.md"
        ).read_text(encoding="utf-8")
        for command in EXPECTED_ENTRY_POINTS:
            self.assertIn(f"`{command}`", command_reference)


if __name__ == "__main__":
    unittest.main()
