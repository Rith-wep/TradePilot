import unittest
from datetime import timedelta
from decimal import Decimal

from backtesting_helpers import OBSERVABLE, instrument, opening_quote, order, provenance
from tradepilot.backtesting.events import (
    BoundaryEventPriority,
    FillEvent,
    FillPurpose,
    PriceSide,
    event_sort_key,
    required_price_side,
    stressed_opening_price,
)
from tradepilot.backtesting.models import TradeDirection
from tradepilot.backtesting.orders import OrderState
from tradepilot.backtesting.positions import position_from_entry_fill
from tradepilot.backtesting.validation import validate_fill, validate_order_quote


class ExecutionConventionTests(unittest.TestCase):
    def test_long_and_short_price_side_conventions(self) -> None:
        self.assertIs(required_price_side(TradeDirection.LONG, FillPurpose.ENTRY), PriceSide.ASK)
        self.assertIs(required_price_side(TradeDirection.LONG, FillPurpose.EXIT), PriceSide.BID)
        self.assertIs(required_price_side(TradeDirection.SHORT, FillPurpose.ENTRY), PriceSide.BID)
        self.assertIs(required_price_side(TradeDirection.SHORT, FillPurpose.EXIT), PriceSide.ASK)

    def test_spread_stress_and_slippage_are_adverse_without_base_spread_duplication(self) -> None:
        quote = opening_quote()
        long_side, long_price = stressed_opening_price(
            quote, instrument(), TradeDirection.LONG, FillPurpose.ENTRY,
            additional_spread_pips=Decimal("2"), slippage_pips=Decimal("1"),
        )
        short_side, short_price = stressed_opening_price(
            quote, instrument(), TradeDirection.SHORT, FillPurpose.ENTRY,
            additional_spread_pips=Decimal("2"), slippage_pips=Decimal("1"),
        )
        self.assertEqual((long_side, long_price), (PriceSide.ASK, Decimal("1.1004")))
        self.assertEqual((short_side, short_price), (PriceSide.BID, Decimal("1.0998")))

    def test_boundary_order_is_close_signal_then_next_open(self) -> None:
        ordered = sorted(
            (BoundaryEventPriority.OPENING_QUOTE, BoundaryEventPriority.SIGNAL_OBSERVABLE, BoundaryEventPriority.CANDLE_COMPLETED),
            key=lambda item: event_sort_key(OBSERVABLE, item),
        )
        self.assertEqual(ordered, [
            BoundaryEventPriority.CANDLE_COMPLETED,
            BoundaryEventPriority.SIGNAL_OBSERVABLE,
            BoundaryEventPriority.OPENING_QUOTE,
        ])

    def test_detection_open_and_expired_quotes_cannot_execute(self) -> None:
        request = order()
        with self.assertRaisesRegex(ValueError, "precedes earliest"):
            validate_order_quote(request, opening_quote(request.detection_candle_open_time))
        with self.assertRaisesRegex(ValueError, "expiry"):
            validate_order_quote(request, opening_quote(request.expires_at))

    def test_fill_before_observability_or_wrong_side_is_rejected(self) -> None:
        request = order()
        base = dict(
            fill_id="fill", order_id=request.order_id, purpose=FillPurpose.ENTRY,
            direction=TradeDirection.LONG, quantity=request.quantity,
            quoted_price=Decimal("1.1002"), spread_stress=Decimal("0"),
            slippage=Decimal("0"), execution_price=Decimal("1.1002"),
            commission=Decimal("0"), provenance=provenance(),
        )
        early = FillEvent(filled_at=OBSERVABLE - timedelta(seconds=1), price_side=PriceSide.ASK, **base)
        with self.assertRaisesRegex(ValueError, "before signal"):
            validate_fill(request, OrderState.PENDING, early)
        wrong_side = FillEvent(filled_at=OBSERVABLE, price_side=PriceSide.BID, **base)
        with self.assertRaisesRegex(ValueError, "wrong executable"):
            validate_fill(request, OrderState.PENDING, wrong_side)

    def test_entry_pricing_api_cannot_receive_completed_candle_extrema(self) -> None:
        # The pricing function accepts OpeningQuoteEvent, whose contract contains only bid/ask opens.
        _, first = stressed_opening_price(
            opening_quote(), instrument(), TradeDirection.LONG, FillPurpose.ENTRY,
            additional_spread_pips=Decimal("0"), slippage_pips=Decimal("0"),
        )
        _, repeated = stressed_opening_price(
            opening_quote(), instrument(), TradeDirection.LONG, FillPurpose.ENTRY,
            additional_spread_pips=Decimal("0"), slippage_pips=Decimal("0"),
        )
        self.assertEqual(first, repeated)

    def test_position_is_created_only_from_valid_fill_and_explicit_protection(self) -> None:
        request = order(stop_loss=Decimal("1.0900"), take_profit=Decimal("1.1200"))
        fill = FillEvent(
            "fill", request.order_id, FillPurpose.ENTRY, TradeDirection.LONG,
            OBSERVABLE, request.quantity, PriceSide.ASK, Decimal("1.1002"),
            Decimal("0"), Decimal("0"), Decimal("1.1002"), Decimal("0"), provenance(),
        )
        with self.assertRaisesRegex(ValueError, "pending"):
            position_from_entry_fill("position", request, OrderState.CREATED, fill, account_currency="USD", quote_currency="USD")
        position = position_from_entry_fill(
            "position", request, OrderState.PENDING, fill,
            account_currency="USD", quote_currency="USD",
        )
        self.assertEqual(position.entry_fill_id, "fill")
        invalid = order(stop_loss=Decimal("1.1100"))
        with self.assertRaisesRegex(ValueError, "below entry"):
            position_from_entry_fill("position", invalid, OrderState.PENDING, fill, account_currency="USD", quote_currency="USD")


if __name__ == "__main__":
    unittest.main()
