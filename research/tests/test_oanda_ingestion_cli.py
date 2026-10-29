import os
import unittest
from unittest.mock import patch

from tradepilot.data.oanda_ingestion_cli import main


class OandaIngestionCliTests(unittest.TestCase):
    def test_missing_credentials_fail_without_disclosure(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["EURUSD", "--start", "2024-01-01T00:00:00Z", "--end", "2024-01-02T00:00:00Z"]), 2)


if __name__ == "__main__": unittest.main()
