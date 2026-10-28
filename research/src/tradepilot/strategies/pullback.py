"""EMA/RSI Trend Pullback v1 fresh-crossover candidate detection."""

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
class PullbackConfig:
    ema_period: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    rsi_recovery_level: Decimal = Decimal("50")
    price_basis: PriceBasis = "mid"
    reject_unexpected_gaps: bool = True

    def __post_init__(self) -> None:
        for name in ("ema_period", "rsi_period", "atr_period"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.rsi_recovery_level, Decimal) or not self.rsi_recovery_level.is_finite():
            raise ValueError("rsi_recovery_level must be a finite Decimal")
        if not Decimal(0) < self.rsi_recovery_level < Decimal(100):
            raise ValueError("rsi_recovery_level must be between 0 and 100")
        if self.price_basis not in ("bid", "ask", "mid"):
            raise ValueError("price_basis must be 'bid', 'ask', or 'mid'")


class EmaRsiPullbackStrategy:
    name = "ema_rsi_trend_pullback"
    version = "1.0.0"

    def __init__(self, config: PullbackConfig | None = None) -> None:
        self.config = config or PullbackConfig()

    def detect(
        self,
        candles: Sequence[Candle],
        indicators: StrategyIndicators,
        calendar: TradingSessionCalendar,
    ) -> tuple[SetupRecord, ...]:
        values = validate_strategy_candles(
            candles, calendar, reject_unexpected_gaps=self.config.reject_unexpected_gaps
        )
        if indicators.ema is None or indicators.rsi is None or indicators.atr is None:
            raise StrategyInputError("EMA, RSI, and ATR series are required")
        for series, name, period in (
            (indicators.ema, "EMA", self.config.ema_period),
            (indicators.rsi, "RSI", self.config.rsi_period),
            (indicators.atr, "ATR", self.config.atr_period),
        ):
            validate_indicator_alignment(
                values, series, name=name, period=period, price_basis=self.config.price_basis
            )
        fingerprint = configuration_fingerprint(self.name, self.version, self.config, calendar.calendar_id)
        setups: list[SetupRecord] = []
        for index in range(1, len(values)):
            ema_previous = indicators.ema.points[index - 1].value
            ema_current = indicators.ema.points[index].value
            rsi_previous = indicators.rsi.points[index - 1].value
            rsi_current = indicators.rsi.points[index].value
            atr_current = indicators.atr.points[index].value
            if None in (ema_previous, ema_current, rsi_previous, rsi_current, atr_current):
                continue
            previous_close = candle_price(values[index - 1], "close", self.config.price_basis)
            current_close = candle_price(values[index], "close", self.config.price_basis)
            long_rules = (
                ema_current > ema_previous,
                previous_close <= ema_previous,
                current_close > ema_current,
                rsi_current > self.config.rsi_recovery_level,
                rsi_current > rsi_previous,
            )
            short_rules = (
                ema_current < ema_previous,
                previous_close >= ema_previous,
                current_close < ema_current,
                rsi_current < self.config.rsi_recovery_level,
                rsi_current < rsi_previous,
            )
            for direction, rules in ((Direction.LONG, long_rules), (Direction.SHORT, short_rules)):
                if not all(rules):
                    continue
                long = direction is Direction.LONG
                reference = (
                    candle_price(values[index - 1], "low", self.config.price_basis) - atr_current
                    if long else
                    candle_price(values[index - 1], "high", self.config.price_basis) + atr_current
                )
                evidence = (
                    RuleEvidence("ema_trend", True, ema_current - ema_previous, "> 0" if long else "< 0"),
                    RuleEvidence("previous_close_pullback", True, previous_close, "<= previous EMA" if long else ">= previous EMA"),
                    RuleEvidence("fresh_price_recovery", True, current_close, "> current EMA" if long else "< current EMA"),
                    RuleEvidence("rsi_level_recovery", True, rsi_current, f"> {self.config.rsi_recovery_level}" if long else f"< {self.config.rsi_recovery_level}"),
                    RuleEvidence("rsi_momentum", True, rsi_current - rsi_previous, "> 0" if long else "< 0"),
                )
                current = values[index]
                setups.append(SetupRecord(
                    strategy_name=self.name,
                    strategy_version=self.version,
                    instrument=current.instrument.symbol,
                    timeframe=current.timeframe,
                    detection_candle_open_time=current.timestamp,
                    observable_at=observable_time(current),
                    direction=direction,
                    setup_type="ema_rsi_fresh_recovery",
                    indicator_values=(
                        NamedValue("ema_previous", ema_previous),
                        NamedValue("ema_current", ema_current),
                        NamedValue("rsi_previous", rsi_previous),
                        NamedValue("rsi_current", rsi_current),
                        NamedValue("atr_current", atr_current),
                    ),
                    rule_evidence=evidence,
                    invalidation_conditions=(
                        "A later completed close reaches or crosses the structural invalidation reference.",
                        "The EMA slope no longer supports the candidate direction.",
                    ),
                    structural_invalidation_reference=reference,
                    configuration_fingerprint=fingerprint,
                ))
        return deduplicate_setups(setups)
