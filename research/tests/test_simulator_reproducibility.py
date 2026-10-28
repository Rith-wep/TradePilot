import unittest

from simulator_helpers import build_context
from tradepilot.backtesting.policies import FinancingModel
from tradepilot.backtesting.simulator import EventDrivenSimulator, SimulationError


class SimulatorReproducibilityTests(unittest.TestCase):
    def test_identical_inputs_produce_identical_results(self) -> None:
        context = build_context(stop_pips="10", target_pips="20")
        first = EventDrivenSimulator().run(*context)
        second = EventDrivenSimulator().run(*context)
        self.assertEqual(first, second)

    def test_provenance_mismatch_is_rejected(self) -> None:
        integrity, report, config, calendar = build_context()
        report = report.__class__(
            report.report_id, "f" * 64, report.dataset_checksum, report.instrument,
            report.timeframe, report.strategy_name, report.strategy_version,
            report.configuration_fingerprint, report.session_calendar_id, report.signals,
        )
        with self.assertRaisesRegex(SimulationError, "dataset ID"):
            EventDrivenSimulator().run(integrity, report, config, calendar)

    def test_explicit_financing_is_rejected(self) -> None:
        with self.assertRaisesRegex(SimulationError, "FinancingModel.NONE"):
            EventDrivenSimulator().run(*build_context(financing=FinancingModel.EXPLICIT_RATES))


if __name__ == "__main__":
    unittest.main()
