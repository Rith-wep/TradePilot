import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from tradepilot.data.models import Instrument
from tradepilot.data.providers.base import ProviderError, ProviderRequest, RateLimitError
from tradepilot.data.providers.oanda import HttpResponse, OandaMarketDataProvider, OandaProviderConfig

START = datetime(2024, 1, 2, tzinfo=timezone.utc)
EURUSD = Instrument("EURUSD", "EUR", "USD", Decimal("0.0001"), 5)
GBPUSD = Instrument("GBPUSD", "GBP", "USD", Decimal("0.0001"), 5)


def record(index=0, *, complete=True, time=None):
    return {
        "complete": complete,
        "time": time or (START + timedelta(hours=index)).isoformat().replace("+00:00", "Z"),
        "bid": {"o": "1.10000", "h": "1.10100", "l": "1.09900", "c": "1.10050"},
        "ask": {"o": "1.10020", "h": "1.10120", "l": "1.09920", "c": "1.10070"},
    }


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers, timeout_seconds):
        self.calls.append((url, dict(headers), timeout_seconds))
        return self.responses.pop(0)


def response(records, *, instrument="EUR_USD", status=200, headers=None):
    body = json.dumps({"instrument": instrument, "granularity": "H1", "candles": records}).encode()
    return HttpResponse(status, body, headers or {"RequestID": "request-1"})


class OandaProviderTests(unittest.TestCase):
    def provider(self, transport, **config):
        return OandaMarketDataProvider(
            "secret-token", "secret-account", transport=transport,
            config=OandaProviderConfig(requests_per_second=1000, **config),
        )

    def test_parses_completed_bid_ask_h1_candles(self):
        transport = RecordingTransport([response([record()])])
        page = self.provider(transport).fetch_page(ProviderRequest(EURUSD, "H1", START, START + timedelta(hours=1)))
        self.assertEqual(page.candles[0].bid_open, "1.10000")
        self.assertEqual(page.candles[0].ask_close, "1.10070")
        self.assertEqual(page.metadata["price_component"], "BA")
        url, headers, timeout = transport.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer secret-token")
        self.assertEqual(parse_qs(urlparse(url).query)["price"], ["BA"])
        self.assertEqual(timeout, 30.0)

    def test_gbpusd_mapping_and_verified_page_boundaries(self):
        transport = RecordingTransport([
            response([record(0)], instrument="GBP_USD"),
            response([record(2)], instrument="GBP_USD"),
        ])
        provider = self.provider(transport, maximum_candles_per_request=2)
        request = ProviderRequest(GBPUSD, "H1", START, START + timedelta(hours=3))
        first = provider.fetch_page(request)
        self.assertEqual(first.next_cursor, "2024-01-02T02:00:00Z")
        second = provider.fetch_page(request, first.next_cursor)
        self.assertIsNone(second.next_cursor)
        self.assertIn("GBP_USD", transport.calls[0][0])

    def test_rejects_out_of_page_incomplete_and_malformed_responses(self):
        cases = (
            response([record(time=(START + timedelta(hours=2)).isoformat().replace("+00:00", "Z"))]),
            response([record(complete=False)]),
            HttpResponse(200, b"not-json", {}),
        )
        for item in cases:
            with self.subTest(body=item.body[:20]):
                with self.assertRaisesRegex(ProviderError, "malformed"):
                    self.provider(RecordingTransport([item])).fetch_page(
                        ProviderRequest(EURUSD, "H1", START, START + timedelta(hours=1))
                    )

    def test_rejects_unsupported_instrument_and_timeframe(self):
        usdjpy = Instrument("USDJPY", "USD", "JPY", Decimal("0.01"), 3)
        provider = self.provider(RecordingTransport([]))
        with self.assertRaisesRegex(ProviderError, "EURUSD and GBPUSD"):
            provider.fetch_page(ProviderRequest(usdjpy, "H1", START, START + timedelta(hours=1)))
        with self.assertRaisesRegex(ProviderError, "H1 only"):
            provider.fetch_page(ProviderRequest(EURUSD, "M5", START, START + timedelta(hours=1)))

    def test_rate_limit_exposes_retry_after_without_credentials(self):
        transport = RecordingTransport([HttpResponse(429, b'{"error":"limited"}', {"Retry-After": "2"})])
        with self.assertRaises(RateLimitError) as raised:
            self.provider(transport).fetch_page(ProviderRequest(EURUSD, "H1", START, START + timedelta(hours=1)))
        self.assertEqual(raised.exception.retry_after_seconds, 2.0)
        self.assertNotIn("secret-token", str(raised.exception))
        self.assertNotIn("secret-account", str(raised.exception))

    def test_authentication_error_is_redacted(self):
        transport = RecordingTransport([HttpResponse(401, b'{"error":"secret-token"}', {})])
        with self.assertRaises(ProviderError) as raised:
            self.provider(transport).fetch_page(ProviderRequest(EURUSD, "H1", START, START + timedelta(hours=1)))
        self.assertNotIn("secret-token", str(raised.exception))
        self.assertNotIn("secret-account", str(raised.exception))

    def test_request_rate_is_throttled(self):
        times = iter((0.0, 0.1, 0.5))
        sleeps = []
        transport = RecordingTransport([response([]), response([])])
        provider = OandaMarketDataProvider(
            "token", "account", transport=transport,
            config=OandaProviderConfig(requests_per_second=2),
            monotonic_clock=lambda: next(times), sleeper=sleeps.append,
        )
        request = ProviderRequest(EURUSD, "H1", START, START + timedelta(hours=1))
        provider.fetch_page(request)
        provider.fetch_page(request)
        self.assertEqual(sleeps, [0.4])


if __name__ == "__main__": unittest.main()
