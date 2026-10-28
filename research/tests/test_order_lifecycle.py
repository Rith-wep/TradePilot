import unittest
from datetime import timedelta

from backtesting_helpers import OBSERVABLE, order
from tradepilot.backtesting.orders import OrderLifecycleEvent, OrderState, validate_transition


class OrderLifecycleTests(unittest.TestCase):
    def test_valid_order_state_transitions(self) -> None:
        for target in (OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED):
            validate_transition(OrderState.PENDING, target)
        event = OrderLifecycleEvent("event-1", "order-1", OrderState.PENDING, OrderState.EXPIRED, OBSERVABLE, "expiry reached")
        self.assertEqual(event.state, OrderState.EXPIRED)

    def test_invalid_terminal_and_direct_fill_transitions(self) -> None:
        with self.assertRaisesRegex(ValueError, "CREATED -> FILLED"):
            validate_transition(OrderState.CREATED, OrderState.FILLED)
        with self.assertRaisesRegex(ValueError, "FILLED -> CANCELLED"):
            validate_transition(OrderState.FILLED, OrderState.CANCELLED)

    def test_first_event_must_be_created(self) -> None:
        with self.assertRaisesRegex(ValueError, "first lifecycle"):
            OrderLifecycleEvent("event", "order", None, OrderState.PENDING, OBSERVABLE, "invalid")

    def test_expiry_is_explicit_and_after_execution_window(self) -> None:
        self.assertGreater(order().expires_at, order().earliest_execution_at)
        with self.assertRaisesRegex(ValueError, "expiry"):
            order(expires_at=OBSERVABLE)

    def test_invalid_order_timestamps_and_quantity(self) -> None:
        with self.assertRaisesRegex(ValueError, "created"):
            order(created_at=OBSERVABLE - timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "quantity"):
            order(quantity=0)


if __name__ == "__main__":
    unittest.main()
