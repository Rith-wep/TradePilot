import os
import unittest
from datetime import timedelta
from unittest.mock import patch

from ingestion_helpers import EURUSD, START, raw_candle
from tradepilot.data.connectivity import verify_connectivity
from tradepilot.data.providers.mock import MockMarketDataProvider
from tradepilot.data.readiness_cli import main


class ReadinessConnectivityTests(unittest.TestCase):
    def test_completed_candle_connectivity(self):
        result = verify_connectivity(
            MockMarketDataProvider((raw_candle(0),)), EURUSD, START, START + timedelta(hours=1),
        )
        self.assertTrue(result.connected)

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(("connectivity",)), 2)


if __name__ == "__main__": unittest.main()
