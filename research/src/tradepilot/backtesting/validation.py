"""Cross-record validation for backtesting timing and provenance."""

from datetime import datetime

from tradepilot.backtesting.config import BacktestConfig
from tradepilot.backtesting.events import FillEvent, FillPurpose, OpeningQuoteEvent, required_price_side
from tradepilot.backtesting.models import CurrencyConversionObservation
from tradepilot.backtesting.orders import OrderRequest, OrderState
from tradepilot.data.integrity import IntegrityReport
from tradepilot.reporting.models import ResearchContent
from tradepilot.reporting.storage import report_identifier


def validate_provenance(
    config: BacktestConfig,
    integrity: IntegrityReport,
    report_id: str,
    report: ResearchContent,
) -> None:
    if not integrity.valid:
        raise ValueError("dataset integrity verification must pass")
    expected = config.provenance
    if report_identifier(report) != report_id:
        raise ValueError("research report ID does not match canonical report content")
    comparisons = (
        (expected.dataset_id, integrity.dataset_id, "dataset ID"),
        (expected.dataset_checksum, integrity.dataset_checksum, "dataset checksum"),
        (expected.research_report_id, report_id, "research report ID"),
        (expected.dataset_id, report.dataset_id, "report dataset ID"),
        (expected.dataset_checksum, report.dataset_checksum, "report dataset checksum"),
        (expected.strategy_name, report.strategy_name, "strategy name"),
        (expected.strategy_version, report.strategy_version, "strategy version"),
        (expected.configuration_fingerprint, report.configuration_fingerprint, "configuration fingerprint"),
        (config.instrument.symbol, report.instrument, "instrument"),
        (config.timeframe, report.timeframe, "timeframe"),
    )
    for configured, actual, label in comparisons:
        if configured != actual:
            raise ValueError(f"{label} provenance mismatch")


def validate_order_quote(order: OrderRequest, quote: OpeningQuoteEvent) -> None:
    if quote.instrument != order.instrument:
        raise ValueError("opening quote instrument does not match order")
    if quote.dataset_id != order.provenance.dataset_id or quote.dataset_checksum != order.provenance.dataset_checksum:
        raise ValueError("opening quote provenance does not match order")
    if quote.candle_open_time < order.earliest_execution_at:
        raise ValueError("opening quote precedes earliest execution time")
    if quote.candle_open_time >= order.expires_at:
        raise ValueError("opening quote is unavailable before order expiry")
    if quote.candle_open_time <= order.detection_candle_open_time:
        raise ValueError("detection candle opening quote cannot execute its signal")


def validate_order_configuration(order: OrderRequest, config: BacktestConfig) -> None:
    if order.instrument != config.instrument.symbol:
        raise ValueError("order instrument does not match configuration")
    if order.provenance != config.provenance:
        raise ValueError("order provenance does not match configuration")
    if order.quantity > config.risk_policy.max_quantity:
        raise ValueError("order quantity exceeds configured maximum")
    if order.quantity % config.instrument.quantity_increment != 0:
        raise ValueError("order quantity does not align with instrument increment")


def validate_fill(order: OrderRequest, current_state: OrderState, fill: FillEvent) -> None:
    if current_state is not OrderState.PENDING:
        raise ValueError("only a pending order can be filled")
    if fill.order_id != order.order_id or fill.provenance != order.provenance:
        raise ValueError("fill provenance does not match order")
    if fill.purpose is not FillPurpose.ENTRY:
        raise ValueError("an order request can create a position only from an entry fill")
    if fill.direction is not order.direction or fill.quantity != order.quantity:
        raise ValueError("fill direction or quantity does not match order")
    if fill.price_side is not required_price_side(order.direction, FillPurpose.ENTRY):
        raise ValueError("fill uses the wrong executable price side")
    if fill.filled_at < order.earliest_execution_at or fill.filled_at < order.signal_observable_at:
        raise ValueError("fill occurs before signal observability")
    if fill.filled_at >= order.expires_at:
        raise ValueError("fill occurs at or after order expiry")


def validate_conversion_observation(
    config: BacktestConfig,
    observation: CurrencyConversionObservation | None,
    financial_event_at: datetime,
) -> None:
    if config.account_currency == config.instrument.quote_currency:
        if observation is not None:
            raise ValueError("conversion observation is unnecessary when account and quote currencies match")
        return
    if observation is None:
        raise ValueError("account/quote currency mismatch requires a conversion observation")
    currencies = {observation.base_currency, observation.quote_currency}
    if currencies != {config.instrument.quote_currency, config.account_currency}:
        raise ValueError("conversion pair is incompatible with quote and account currencies")
    if observation.observed_at > financial_event_at:
        raise ValueError("future conversion observations cannot value earlier financial events")
