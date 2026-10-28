import unittest
from decimal import Decimal

from tradepilot.data.models import Instrument


class InstrumentTests(unittest.TestCase):
    def test_valid_fx_instrument(self) -> None:
        instrument = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
        self.assertEqual(instrument.quote_currency, "USD")

    def test_symbol_must_match_currencies(self) -> None:
        with self.assertRaisesRegex(ValueError, "symbol must equal"):
            Instrument("GBPUSD", "EUR", "USD", Decimal("0.0001"), 5)


if __name__ == "__main__":
    unittest.main()

