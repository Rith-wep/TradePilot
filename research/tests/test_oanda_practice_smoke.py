import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import ProviderRequest
from tradepilot.data.providers.oanda import OandaMarketDataProvider


@unittest.skipUnless(os.environ.get("TRADEPILOT_RUN_OANDA_SMOKE") == "1", "credential-gated OANDA smoke test")
class OandaPracticeSmokeTests(unittest.TestCase):
    def test_completed_eurusd_h1_response(self):
        token = os.environ["OANDA_API_TOKEN"]
        account = os.environ["OANDA_ACCOUNT_ID"]
        instrument = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        page = OandaMarketDataProvider(token, account).fetch_page(
            ProviderRequest(instrument, "H1", end - timedelta(hours=2), end)
        )
        self.assertTrue(page.candles)
        self.assertTrue(all(item.complete for item in page.candles))


if __name__ == "__main__": unittest.main()
