import unittest
from decimal import Decimal

from stock_rsi.data import Snapshot, canonical
from stock_rsi.time import parse_time
from stock_rsi.calendar import TradingCalendar
try:
    from stock_rsi.models import Decision
    from stock_rsi.scheduler import schedule
    from stock_rsi.broker import Broker
except ImportError:
    Decision = schedule = Broker = None

import test_time_data
from test_time_data import fixture


def snapshot():
    return Snapshot(canonical({"as_of": "2024-09-27T09:00:00+00:00", "records": [{"record_id": "e1"}]}))


def decision(action, qty=100):
    return Decision.from_dict({"action": action, "security_id": "SYN_A", "quantity": qty, "evidence_ids": ["e1"], "reason": "literal fixture"}, snapshot())


def bar(day, op=10, close=10, **kwargs):
    return {"security_id": "SYN_A", "trade_date": day, "open": op, "close": close, "limit_up": 11, "limit_down": 9, "suspended": False, **kwargs}


class ScheduleBrokerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Broker, "scheduler/decision/broker implementation missing")
        self.calendar = TradingCalendar(fixture()["sessions"])

    def test_wakes_use_actual_arrival_and_explicit_sessions(self):
        data = test_time_data.TimeDataTests().load(fixture())
        wakes = schedule(data, self.calendar, parse_time("2024-09-27T00:00:00+08:00"), parse_time("2024-10-09T23:00:00+08:00"), holding=True)
        events = [(w.at.isoformat(), tuple(w.reasons)) for w in wakes]
        self.assertIn(("2024-09-30T05:05:00+00:00", ("ARRIVAL:late-news",)), events)
        self.assertNotIn(("2024-09-30T03:45:00+00:00", ("ARRIVAL:late-news",)), events)
        self.assertEqual(len([w for w in wakes if "ARRIVAL:late-news" in w.reasons]), 1)
        self.assertFalse(any(w.at.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Shanghai')).date().isoformat() == "2024-10-01" and "PRE_OPEN" in w.reasons for w in wakes))

    def test_decision_rejects_bad_quantities_and_invisible_evidence(self):
        for quantity in (True, -1, 1.5, float('inf')):
            with self.assertRaises(ValueError):
                decision("BUY", quantity)
        bad = {"action": "BUY", "security_id": "SYN_A", "quantity": 100, "evidence_ids": ["future"], "reason": "x"}
        with self.assertRaises(ValueError):
            Decision.from_dict(bad, snapshot())
        with self.assertRaises(ValueError):
            decision("HOLD", 100)

    def test_close_signal_waits_until_next_session_after_holiday(self):
        broker = Broker(self.calendar, initial_cash="2000", cost_bps="20")
        broker.submit(decision("BUY"), parse_time("2024-09-30T17:00:00+08:00"))
        self.assertEqual(broker.on_open(bar("2024-09-30")), [])
        fills = broker.on_open(bar("2024-10-08"))
        self.assertEqual(len(fills), 1)
        self.assertEqual(broker.cash, Decimal("998.00"))
        self.assertEqual(broker.snapshot()["positions"]["SYN_A"]["quantity"], 100)
        self.assertEqual(broker.on_open(bar("2024-10-08")), [])

    def test_t_plus_one_and_no_negative_cash(self):
        broker = Broker(self.calendar, initial_cash="2000", cost_bps="20")
        broker.submit(decision("BUY"), parse_time("2024-09-27T17:00:00+08:00"))
        broker.on_open(bar("2024-09-30"))
        broker.submit(decision("SELL"), parse_time("2024-09-30T10:00:00+08:00"))
        self.assertEqual(broker.on_open(bar("2024-09-30")), [])
        broker.on_open(bar("2024-10-08", op=10.5))
        self.assertEqual(broker.cash, Decimal("2045.90"))
        self.assertEqual(broker.snapshot()["positions"], {})
        poor = Broker(self.calendar, initial_cash="1000", cost_bps="20")
        poor.submit(decision("BUY"), parse_time("2024-09-27T17:00:00+08:00"))
        self.assertEqual(poor.on_open(bar("2024-09-30")), [])
        self.assertEqual(poor.cash, Decimal("1000"))

    def test_limit_and_suspension_orders_expire_without_fills(self):
        for payload in (bar("2024-09-30", op=11), bar("2024-09-30", suspended=True)):
            broker = Broker(self.calendar, initial_cash="2000", cost_bps="20")
            broker.submit(decision("BUY"), parse_time("2024-09-27T17:00:00+08:00"))
            self.assertEqual(broker.on_open(payload), [])
            self.assertEqual(broker.on_open(bar("2024-10-08")), [])
            self.assertEqual(broker.cash, Decimal("2000"))

    def test_unknown_fill_data_is_not_suspension(self):
        broker = Broker(self.calendar, initial_cash="2000", cost_bps="20")
        broker.submit(decision("BUY"), parse_time("2024-09-27T17:00:00+08:00"))
        with self.assertRaises(ValueError):
            broker.on_open({"security_id": "SYN_A", "trade_date": "2024-09-30", "suspended": False})

    def test_fractional_cent_cash_is_rejected_before_account_mutation(self):
        with self.assertRaises(ValueError):Broker(self.calendar,initial_cash='1000.995',cost_bps='9.95')

    def test_repeated_nontrading_wakes_replace_unfilled_intent(self):
        broker = Broker(self.calendar, initial_cash="5000", cost_bps="20")
        broker.submit(decision("BUY"), parse_time("2024-09-27T17:00:00+08:00"))
        broker.submit(decision("BUY"), parse_time("2024-09-28T11:00:00+08:00"))
        fills = broker.on_open(bar("2024-09-30"))
        self.assertEqual(len(fills), 1)
        self.assertEqual(broker.snapshot()["positions"]["SYN_A"]["quantity"], 100)

    def test_single_open_wrapper_matches_one_bar_batch(self):
        first = Broker(self.calendar, initial_cash="2000", cost_bps="20")
        second = Broker(self.calendar, initial_cash="2000", cost_bps="20")
        at = parse_time("2024-09-27T17:00:00+08:00")
        first.submit(decision("BUY"), at)
        second.submit(decision("BUY"), at)
        payload = bar("2024-09-30")
        self.assertEqual(first.on_open(payload), second.on_market_open([payload]))
        self.assertEqual(first.snapshot(), second.snapshot())

    def test_side_specific_fees_and_minimum_commission_are_paid_from_cash(self):
        broker = Broker(self.calendar,initial_cash="20000",buy_cost_bps="5",sell_cost_bps="15",min_cost="5")
        broker.submit(decision("BUY",1000),parse_time("2024-09-27T17:00:00+08:00"))
        self.assertEqual(broker.on_open(bar("2024-09-30"))[0]["cost"],"5.00")
        broker.submit(decision("SELL",1000),parse_time("2024-09-30T17:00:00+08:00"))
        self.assertEqual(broker.on_open(bar("2024-10-08",op=11))[0]["cost"],"16.50")
        self.assertEqual(broker.cash,Decimal("20978.50"))
        poor = Broker(self.calendar,initial_cash="100.10",buy_cost_bps="5",sell_cost_bps="15",min_cost="5")
        poor.submit(decision("BUY"),parse_time("2024-09-27T17:00:00+08:00"))
        self.assertEqual(poor.on_open(bar("2024-09-30",op=1,limit_up="1.1",limit_down="0.9")),[])
        self.assertEqual(poor.cash,Decimal("100.10"))

    def test_sell_cannot_make_cash_negative_to_pay_minimum_commission(self):
        broker = Broker(self.calendar,initial_cash="10",min_cost="5")
        broker.cash = Decimal("0")
        broker.positions = {"SYN_A":[{"quantity":1,"price":Decimal("1"),"bought_on":self.calendar.days[0]}]}
        broker.submit(decision("SELL",1),parse_time("2024-09-27T17:00:00+08:00"))
        self.assertEqual(broker.on_open(bar("2024-09-30",op=1,limit_up="1.1",limit_down="0.9")),[])
        self.assertEqual(broker.cash,Decimal("0"))
        self.assertEqual(broker.positions["SYN_A"][0]["quantity"],1)
        self.assertEqual(broker.orders[0]["status"],"UNFILLED_FEES_CASH")


if __name__ == '__main__':
    unittest.main()
