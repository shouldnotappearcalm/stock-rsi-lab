"""Separate execution-cost profiles for fixed-policy account feedback replay.

The extra fee is a declared cash stress, not calibrated market impact. It is
charged at each simulated fill and participates in cash affordability.
"""
from decimal import Decimal, ROUND_HALF_UP

from stock_rsi.broker import Broker
from stock_rsi.models import Decision


class SingleOrderLimitError(ValueError):
    pass


class ExecutionCostBroker(Broker):
    def __init__(self, calendar, initial_cash="100000", *, extra_cost_bps=0, **kwargs):
        if type(extra_cost_bps) is not int or not 0 <= extra_cost_bps <= 10000:
            raise ValueError("finite integer extra cost bps in [0,10000] required")
        super().__init__(calendar, initial_cash, **kwargs)
        self.extra_rate = Decimal(extra_cost_bps)/10000

    def _cost(self, gross, action):
        extra = (gross*self.extra_rate).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        return super()._cost(gross, action)+extra

    @staticmethod
    def _check_order_limit(decision):
        if not isinstance(decision, Decision):
            raise ValueError("typed Decision required")
        if type(decision.quantity) is not int or decision.action not in ("BUY", "SELL", "HOLD", "ABSTAIN"):
            raise ValueError("valid action and integer quantity required")
        if (decision.action in ("BUY", "SELL") and decision.quantity <= 0
                or decision.action in ("HOLD", "ABSTAIN") and decision.quantity != 0):
            raise ValueError("quantity does not match action")
        if decision.action == "BUY" and decision.quantity % 100:
            raise ValueError("A-share buys require 100-share lots")
        if decision.action in ("BUY", "SELL") and decision.quantity > 1000000:
            raise SingleOrderLimitError(
                f"single order exceeds 1000000 shares: {decision.action} {decision.security_id} {decision.quantity}")

    def submit(self, decision, at, expires_at=None):
        self._check_order_limit(decision)
        return super().submit(decision, at, expires_at)

    def replace_pending_intent(self, decisions, at, expires_at):
        # Validate the whole batch before cancelling or submitting any order.
        if not isinstance(decisions, (tuple, list)):
            raise ValueError("portfolio intent requires a decision list")
        for decision in decisions:
            self._check_order_limit(decision)
        return super().replace_pending_intent(decisions, at, expires_at)
