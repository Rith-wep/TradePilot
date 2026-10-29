import json
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from ingestion_helpers import EURUSD, START
from tradepilot.data.ingestion import HistoricalIngestor, IngestionError
from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import ProviderRequest
from tradepilot.data.providers.dukascopy_csv import (
    DukascopyCsvError, DukascopyCsvMarketDataProvider, file_sha256,
)
from tradepilot.data.storage import ParquetDatasetStore


ROOT = Path(__file__).resolve().parents[1]
BID = ROOT / "fixtures/dukascopy/eurusd_h1_bid.csv"
ASK = ROOT / "fixtures/dukascopy/eurusd_h1_ask.csv"
FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def provider(**kwargs):
    return DukascopyCsvMarketDataProvider(BID, ASK, timestamp_format=FORMAT, is_synthetic=True, **kwargs)


class DukascopyCsvProviderTests(unittest.TestCase):
    def write(self, content):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "side.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_and_aligns_exact_decimal_strings(self):
        value = provider()
        self.assertEqual(len(value.candles), 3)
        self.assertEqual(value.candles[0].bid_open, "1.10000")
        self.assertEqual(value.candles[0].ask_close, "1.10070")
        self.assertEqual(value.start, START)

    def test_hash_verification_and_metadata_provenance(self):
        value = provider(expected_bid_sha256=file_sha256(BID), expected_ask_sha256=file_sha256(ASK))
        page = value.fetch_page(ProviderRequest(EURUSD, "H1", value.start, value.end))
        self.assertEqual(page.metadata["bid_sha256"], file_sha256(BID))
        self.assertEqual(page.metadata["volume_policy"], "validated_not_stored")
        with self.assertRaisesRegex(DukascopyCsvError, "SHA-256 mismatch"):
            provider(expected_bid_sha256="0" * 64)

    def test_timestamp_format_is_required_and_strict(self):
        with self.assertRaisesRegex(ValueError, "required"):
            DukascopyCsvMarketDataProvider(BID, ASK, timestamp_format="")
        with self.assertRaisesRegex(DukascopyCsvError, "row 2"):
            DukascopyCsvMarketDataProvider(BID, ASK, timestamp_format="%d.%m.%Y %H:%M")

    def test_rejects_bad_header_volume_duplicate_and_order(self):
        header = "Etc/UTC,Open,High,Low,Close,Volume\n"
        good = "2024-01-02T00:00:00+00:00,1,2,0.5,1.5,1\n"
        cases = (
            "Time,Open,High,Low,Close,Volume\n" + good,
            header + good.replace(",1\n", ",-1\n"),
            header + good + good,
            header + good + "2024-01-01T23:00:00+00:00,1,2,0.5,1.5,1\n",
        )
        for content in cases:
            with self.subTest(content=content[:20]):
                bad = self.write(content)
                with self.assertRaises(DukascopyCsvError):
                    DukascopyCsvMarketDataProvider(bad, ASK, timestamp_format=FORMAT)

    def test_rejects_unaligned_sides_without_fabrication(self):
        shortened = self.write("\n".join(ASK.read_text(encoding="utf-8").splitlines()[:-1]) + "\n")
        with self.assertRaisesRegex(DukascopyCsvError, "never fabricated"):
            DukascopyCsvMarketDataProvider(BID, shortened, timestamp_format=FORMAT)

    def test_existing_ingestion_rejects_invalid_ohlc_and_bid_ask(self):
        invalid_ohlc = self.write(BID.read_text(encoding="utf-8").replace("1.10100,1.09950", "1.09800,1.09950", 1))
        crossed_ask = self.write(ASK.read_text(encoding="utf-8").replace("1.10020", "1.09900", 1))
        for bid, ask in ((invalid_ohlc, ASK), (BID, crossed_ask)):
            with self.subTest(bid=bid.name, ask=ask.name), tempfile.TemporaryDirectory() as output:
                value = DukascopyCsvMarketDataProvider(bid, ask, timestamp_format=FORMAT, is_synthetic=True)
                with self.assertRaisesRegex(IngestionError, "failed validation"):
                    HistoricalIngestor(value, ParquetDatasetStore(output)).ingest(EURUSD, "H1", value.start, value.end)

    def test_only_eurusd_h1_is_supported(self):
        gbpusd = Instrument("GBPUSD", "GBP", "USD", Decimal("0.0001"), 5)
        value = provider()
        with self.assertRaisesRegex(DukascopyCsvError, "EURUSD H1"):
            value.fetch_page(ProviderRequest(gbpusd, "H1", value.start, value.end))

    def test_ingestion_records_hashes_and_reuses_snapshot(self):
        with tempfile.TemporaryDirectory() as output:
            value = provider()
            ingestor = HistoricalIngestor(value, ParquetDatasetStore(output))
            first = ingestor.ingest(EURUSD, "H1", value.start, value.end)
            second = ingestor.ingest(EURUSD, "H1", value.start, value.end)
            self.assertEqual(first.stored.dataset_id, second.stored.dataset_id)
            retrievals = list((first.stored.snapshot_path.parent.parent / "retrievals").glob("*.json"))
            record = json.loads(retrievals[0].read_text(encoding="utf-8"))
            self.assertEqual(record["provider_metadata"]["bid_sha256"], value.bid_sha256)


if __name__ == "__main__": unittest.main()
