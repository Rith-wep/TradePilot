"""OANDA v20 historical bid/ask candle adapter.

The adapter owns HTTP/authentication and response parsing only. Normalization,
quality validation, immutable storage, and retries remain in the shared data
pipeline.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic, sleep
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tradepilot.data.providers.base import (
    ProviderCandle,
    ProviderError,
    ProviderPage,
    ProviderRequest,
    RateLimitError,
    TransientProviderError,
)


_ENDPOINTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}
_INSTRUMENTS = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD"}


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> HttpResponse: ...


class UrllibHttpTransport:
    """Small standard-library transport; it never includes auth values in errors."""

    def get(self, url: str, headers: Mapping[str, str], timeout_seconds: float) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS host
                return HttpResponse(response.status, response.read(), dict(response.headers.items()))
        except HTTPError as exc:
            return HttpResponse(exc.code, exc.read(), dict(exc.headers.items()) if exc.headers else {})
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError("OANDA request timed out") from exc
        except URLError as exc:
            raise TransientProviderError("OANDA network request failed") from exc


@dataclass(frozen=True, slots=True)
class OandaProviderConfig:
    environment: str = "practice"
    requests_per_second: float = 2.0
    maximum_candles_per_request: int = 5000

    def __post_init__(self) -> None:
        if self.environment not in _ENDPOINTS:
            raise ValueError("OANDA environment must be 'practice' or 'live'")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if not 1 <= self.maximum_candles_per_request <= 5000:
            raise ValueError("maximum_candles_per_request must be between 1 and 5000")


class OandaMarketDataProvider:
    """Fetch completed EUR/USD and GBP/USD H1 bid/ask candles from OANDA v20."""

    def __init__(
        self,
        token: str,
        account_id: str,
        *,
        config: OandaProviderConfig | None = None,
        transport: HttpTransport | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not token.strip() or not account_id.strip():
            raise ValueError("OANDA token and account ID are required")
        self._token = token
        self._account_id = account_id
        self.config = config or OandaProviderConfig()
        self._transport = transport or UrllibHttpTransport()
        self._clock = monotonic_clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    @property
    def name(self) -> str:
        return "oanda-v20"

    @property
    def dataset_version(self) -> str:
        return "oanda-v20-h1-bid-ask/v1"

    @property
    def is_synthetic(self) -> bool:
        return False

    def _throttle(self) -> None:
        now = self._clock()
        interval = 1.0 / self.config.requests_per_second
        if self._last_request_at is not None:
            delay = interval - (now - self._last_request_at)
            if delay > 0:
                self._sleeper(delay)
                now = self._clock()
        self._last_request_at = now

    @staticmethod
    def _cursor(value: str | None, request: ProviderRequest) -> datetime:
        if value is None:
            return request.start
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProviderError("invalid OANDA pagination cursor") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ProviderError("OANDA pagination cursor must be UTC")
        if not request.start < parsed < request.end:
            raise ProviderError("OANDA pagination cursor lies outside request boundaries")
        return parsed

    def fetch_page(self, request: ProviderRequest, cursor: str | None = None) -> ProviderPage:
        if (
            request.start.tzinfo is None or request.start.utcoffset() != timedelta(0)
            or request.end.tzinfo is None or request.end.utcoffset() != timedelta(0)
            or request.start >= request.end
        ):
            raise ProviderError("OANDA request requires a valid half-open UTC range")
        if request.timeframe != "H1":
            raise ProviderError("OANDA adapter supports H1 only")
        provider_instrument = _INSTRUMENTS.get(request.instrument.symbol)
        if provider_instrument is None:
            raise ProviderError("OANDA adapter supports EURUSD and GBPUSD only")
        page_start = self._cursor(cursor, request)
        page_end = min(
            request.end,
            page_start + timedelta(hours=self.config.maximum_candles_per_request),
        )
        query = urlencode({
            "from": page_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "to": page_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "granularity": "H1",
            "price": "BA",
        })
        url = (
            f"{_ENDPOINTS[self.config.environment]}/v3/accounts/"
            f"{self._account_id}/instruments/{provider_instrument}/candles?{query}"
        )
        self._throttle()
        response = self._transport.get(
            url,
            {"Authorization": f"Bearer {self._token}", "Accept-Datetime-Format": "RFC3339"},
            request.timeout_seconds,
        )
        request_id = response.headers.get("RequestID", response.headers.get("Request-Id", "unknown"))
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after is not None else None
            except ValueError:
                delay = None
            raise RateLimitError(f"OANDA rate limit exceeded (request_id={request_id})", delay)
        if response.status >= 500:
            raise TransientProviderError(f"OANDA service unavailable (status={response.status}, request_id={request_id})")
        if response.status != 200:
            raise ProviderError(f"OANDA request rejected (status={response.status}, request_id={request_id})")

        candles = self._parse(response.body, provider_instrument, page_start, page_end)
        next_cursor = page_end.isoformat().replace("+00:00", "Z") if page_end < request.end else None
        return ProviderPage(candles, next_cursor, {
            "adapter": "oanda-v20",
            "api_environment": self.config.environment,
            "provider_instrument": provider_instrument,
            "granularity": "H1",
            "price_component": "BA",
            f"request_id:{page_start.isoformat().replace('+00:00', 'Z')}": request_id,
        })

    @staticmethod
    def _parse(body: bytes, expected_instrument: str, start: datetime, end: datetime) -> tuple[ProviderCandle, ...]:
        try:
            payload = json.loads(body.decode("utf-8"))
            if payload.get("instrument") != expected_instrument or payload.get("granularity") != "H1":
                raise ValueError("response instrument or granularity does not match request")
            records = payload["candles"]
            if not isinstance(records, list):
                raise TypeError("candles must be an array")
            output: list[ProviderCandle] = []
            for record in records:
                if record.get("complete") is not True:
                    raise ValueError("response contains an incomplete candle")
                timestamp = datetime.fromisoformat(str(record["time"]).replace("Z", "+00:00"))
                if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
                    raise ValueError("candle timestamp is not UTC")
                if not start <= timestamp < end:
                    raise ValueError("candle lies outside verified page boundaries")
                bid, ask = record["bid"], record["ask"]
                output.append(ProviderCandle(
                    timestamp=timestamp, timeframe="H1",
                    bid_open=str(bid["o"]), bid_high=str(bid["h"]),
                    bid_low=str(bid["l"]), bid_close=str(bid["c"]),
                    ask_open=str(ask["o"]), ask_high=str(ask["h"]),
                    ask_low=str(ask["l"]), ask_close=str(ask["c"]),
                    complete=True,
                ))
            return tuple(output)
        except (AttributeError, json.JSONDecodeError, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ProviderError(f"malformed OANDA candle response: {exc}") from exc
