import math
import unittest
from datetime import date

try:
    from stock_rsi.illiquidity import illiquidity_score,build_targets
except ImportError:illiquidity_score=build_targets=None


class IlliquidityTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(illiquidity_score)

    def test_twenty_two_returns_and_documented_thousand_yuan_conversion(self):
        closes=[100*1.01**i for i in range(23)]
        score=illiquidity_score(closes,[100.]*22,[1.]*22)
        self.assertAlmostEqual(score,1e-7)
        self.assertAlmostEqual(illiquidity_score(closes,[200.]*22,[1.]*22),score/2)
        self.assertAlmostEqual(illiquidity_score([p*77 for p in closes],[100.]*22,[9.]*22),score)

    def test_zero_volume_or_amount_and_incomplete_prices_are_not_fake_liquidity(self):
        closes=[100.]*23;amount=[100.]*22;volume=[1.]*22
        self.assertEqual(illiquidity_score(closes,amount,volume),0.)
        for invalid in (None,0.,-1.,math.nan,math.inf):
            self.assertIsNone(illiquidity_score(closes,amount[:-1]+[invalid],volume))
            self.assertIsNone(illiquidity_score(closes[:-1]+[invalid],amount,volume))
            self.assertIsNone(illiquidity_score(closes,amount,volume[:-1]+[invalid]))
        with self.assertRaises(ValueError):illiquidity_score(closes[:-1],amount,volume)
        with self.assertRaises(ValueError):illiquidity_score(closes,amount[:-1],volume[:-1])

    def test_explicit_window_historical_membership_and_future_guard(self):
        days=('2023-11-29 2023-11-30 2023-12-01 2023-12-04 2023-12-05 2023-12-06 '
              '2023-12-07 2023-12-08 2023-12-11 2023-12-12 2023-12-13 2023-12-14 '
              '2023-12-15 2023-12-18 2023-12-19 2023-12-20 2023-12-21 2023-12-22 '
              '2023-12-25 2023-12-26 2023-12-27 2023-12-28 2023-12-29').split()
        class Source:
            calendar=tuple(map(date.fromisoformat,days+['2024-01-02','2024-01-03','2026-01-05']))
            def __init__(self):self.reads=[]
            def value(self,code,field,day):
                assert day<='2023-12-29','future query';self.reads.append(day)
                if field=='close':return 100*1.01**days.index(day)
                if field=='amount':return float(201-int(code[-3:]))
                return 1.
        members={f'SH600{i:03d}':[('2020-01-01','2025-12-31')] for i in range(200)}
        members['SZ000999']=[('2024-01-02','2025-12-31')]
        source=Source();targets,receipts=build_targets(source,members,end='2024-01-03')
        chosen=targets['amihud22']['2024-01-02']['weights']
        self.assertEqual(tuple(chosen),tuple(f'SH600{i:03d}' for i in range(199,179,-1)))
        self.assertAlmostEqual(sum(chosen.values()),.95)
        self.assertNotIn('SZ000999',targets['eligible_equal_weight']['2024-01-02']['weights'])
        self.assertEqual(receipts[0]['baseline_close_day'],'2023-11-29')
        self.assertEqual(receipts[0]['return_begin'],'2023-11-30')
        self.assertEqual(receipts[0]['daily_return_observations'],22)
        self.assertEqual(max(source.reads),'2023-12-29')
        with self.assertRaises(ValueError):build_targets(source,members,end='2026-01-05')
        source.calendar=source.calendar[1:]
        with self.assertRaises(ValueError):build_targets(source,members,end='2024-01-03')
