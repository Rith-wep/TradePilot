"""Price Range Breakout v1 candidate detection."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from tradepilot.data.models import Candle
from tradepilot.data.sessions import TradingSessionCalendar
from tradepilot.indicators.models import PriceBasis
from tradepilot.strategies.base import (
    StrategyInputError,
    candle_price,
    configuration_fingerprint,
    observable_time,
    validate_indicator_alignment,
    validate_strategy_candles,
)
from tradepilot.strategies.models import (
    Direction,
    NamedValue,
    RuleEvidence,
    SetupRecord,
    StrategyIndicators,
    deduplicate_setups,
)


@dataclass(frozen=True, slots=True)
class BreakoutConfig:
    lookback: int = 20
    price_basis: PriceBasis = "mid"
    atr_period: int = 14
    minimum_breakout_atr: Decimal | None = None
    reject_unexpected_gaps: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.lookback, bool) or not isinstance(self.lookback, int) or self.lookback <= 0:
            raise ValueError("lookback must be a positive integer")
        if self.price_basis not in ("bid", "ask", "mid"):
            raise ValueError("price_basis must be 'bid', 'ask', or 'mid'")
        if isinstance(self.atr_period, bool) or not isinstance(self.atr_period, int) or self.atr_period <= 0:
            raise ValueError("atr_period must be a positive integer")
        if self.minimum_breakout_atr is not None:
            if not isinstance(self.minimum_breakout_atr, Decimal) or not self.minimum_breakout_atr.is_finite():
                raise ValueError("minimum_breakout_atr must be a finite Decimal")
            if self.minimum_breakout_atr < 0:
                raise ValueError("minimum_breakout_atr must not be negative")


class PriceRangeBreakoutStrategy:
    name = "price_range_breakout"
    version = "1.0.0"

    def __init__(self, config: BreakoutConfig | None = None) -> None:
        self.config = config or BreakoutConfig()

    def detect(
        self,
        candles: Sequence[Candle],
        indicators: StrategyIndicators,
        calendar: TradingSessionCalendar,
    ) -> tuple[SetupRecord, ...]:
        values = validate_strategy_candles(
            candles, calendar, reject_unexpected_gaps=self.config.reject_unexpected_gaps
        )
        atr_series = indicators.atr
        if self.config.minimum_breakout_atr is not None:
            if atr_series is None:
                raise StrategyInputError("ATR series is required when the breakout ATR filter is enabled")
            validate_indicator_alignment(
                values, atr_series, name="ATR", period=self.config.atr_period,
                price_basis=self.config.price_basis,
            )
        fingerprint = configuration_fingerprint(self.name, self.version, self.config, calendar.calendar_id)
        setups: list[SetupRecord] = []
        for index in range(self.config.lookback, len(values)):
            current = values[index]
            reference = values[index - self.config.lookback:index]
            range_high = max(candle_price(item, "high", self.config.price_basis) for item in reference)
            range_low = min(candle_price(item, "low", self.config.price_basis) for item in reference)
            close = candle_price(current, "close", self.config.price_basis)
            atr_value = atr_series.points[index].value if atr_series is not None else None
            for direction, crossed, distance, boundary, comparison in (
                (Direction.LONG, close > range_high, close - range_high, range_high, "close > prior range high"),
                (Direction.SHORT, close < range_low, range_low - close, range_low, "close < prior range low"),
            ):
                if not crossed:
                    continue
                if self.config.minimum_breakout_atr is not None:
                    if atr_value is None or distance < self.config.minimum_breakout_atr * atr_value:
                        continue
                evidence = [
                    RuleEvidence("strict_range_break", True, close, comparison),
                    RuleEvidence("current_candle_excluded", True, self.config.lookback, "reference uses preceding candles only"),
                ]
                indicator_values: list[NamedValue] = []
                if self.config.minimum_breakout_atr is not None:
                    evidence.append(RuleEvidence(
                        "minimum_atr_distance", True, distance,
                        f">= {self.config.minimum_breakout_atr} × ATR",
                    ))
                    indicator_values.append(NamedValue("atr", atr_value))
                setups.append(SetupRecord(
                    strategy_name=self.name,
                    strategy_version=self.version,
                    instrument=current.instrument.symbol,
                    timeframe=current.timeframe,
                    detection_candle_open_time=current.timestamp,
                    observable_at=observable_time(current),
                    direction=direction,
                    setup_type="range_breakout",
                    indicator_values=tuple(indicator_values),
                    rule_evidence=tuple(evidence + [
                        RuleEvidence("reference_high", True, range_high, "prior window maximum high"),
                        RuleEvidence("reference_low", True, range_low, "prior window minimum low"),
                    ]),
                    invalidation_conditions=(
                        "A later completed close returns to or through the broken range boundary.",
                    ),
                    structural_invalidation_reference=boundary,
                    configuration_fingerprint=fingerprint,
                ))
        return deduplicate_setups(setups)

