"""Provider-neutral domain contracts for the future event-driven backtester."""

from tradepilot.backtesting.config import BacktestConfig, BacktestRun
from tradepilot.backtesting.events import CompletedCandleEvent, FillEvent, OpeningQuoteEvent
from tradepilot.backtesting.models import BacktestProvenance, CurrencyConversionObservation, InstrumentSpec, TradeDirection
from tradepilot.backtesting.orders import OrderLifecycleEvent, OrderRequest, OrderState
from tradepilot.backtesting.positions import PositionState
from tradepilot.backtesting.signal_policy import SignalOrderPolicy
from tradepilot.backtesting.simulation_models import SimulationCandidateReport, SimulationConfig, SimulationResult
from tradepilot.backtesting.simulator import EventDrivenSimulator, SimulationError

__all__ = [
    "BacktestConfig", "BacktestProvenance", "BacktestRun", "CompletedCandleEvent",
    "CurrencyConversionObservation", "FillEvent", "InstrumentSpec", "OpeningQuoteEvent",
    "OrderLifecycleEvent", "OrderRequest", "OrderState", "PositionState", "TradeDirection",
    "EventDrivenSimulator", "SignalOrderPolicy", "SimulationCandidateReport",
    "SimulationConfig", "SimulationError", "SimulationResult",
]
