"""Calendar and causal tests for a single price-to-trailing-high hypothesis."""
from datetime import date
import math
import unittest
try:
    from stock_rsi.high52 import high52_score,build_targets
except ImportError:
    high52_score=build_targets=None

class High52Tests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(high52_score,'52-week-high module missing')

    def test_ratio_uses_maximum_high_not_first_or_last_price_return(self):
        self.assertAlmostEqual(high52_score([8.,9.,9.],[20.,10.,10.]),.45)
        self.assertAlmostEqual(high52_score([8.,9.,9.],[8.,10.,10.]),.9)
        self.assertAlmostEqual(high52_score([80.,90.,90.],[80.,100.,100.]),.9)

    def test_incomplete_or_inconsistent_bar_is_not_ranked(self):
        for closes,highs in (([1.,None],[2.,2.]),([1.,2.],[2.,1.]),
                             ([1.,2.],[2.,math.inf]),([1.,2.],[0.,3.]),([True,2.],[2.,3.])):
            self.assertIsNone(high52_score(closes,highs))
        with self.assertRaises(ValueError):high52_score([1.,2.],[2.])
        with self.assertRaises(ValueError):high52_score([],[])

    def test_complete_twelve_calendar_months_and_causal_historical_members(self):
        class Source:
            calendar=tuple([date(2022,12,30)]+[date(2023,m,15) for m in range(1,13)]+[date(2023,12,29),date(2024,1,2),date(2024,1,31),date(2024,2,1),date(2026,1,5)])
            def __init__(self):self.reads=[]
            def value(self,code,field,day):
                assert day<='2023-12-29','future read'
                self.reads.append(day)
                if field in ('volume','factor'):return 1.
                if field=='close':return 10.
                if field=='high':return 10.+int(code[-3:]) if day=='2023-01-15' else 10.
                raise AssertionError(field)
        source=Source();members={f'SH600{i:03d}':[('2020-01-01','2025-12-31')] for i in range(200)}
        members['SZ000999']=[('2024-01-02','2025-12-31')]
        targets,receipts=build_targets(source,members,end='2024-01-31')
        row=receipts[0];chosen=targets['near_52w_high']['2024-01-02']['weights']
        self.assertEqual(row['window_preceding_month_end'],'2022-12-30')
        self.assertEqual(row['window_begin'],'2023-01-15')
        self.assertEqual(row['window_end'],'2023-12-29')
        self.assertEqual(row['explicit_window_sessions'],13)
        self.assertEqual(tuple(chosen),tuple(f'SH600{i:03d}' for i in range(20)))
        self.assertNotIn('SZ000999',targets['eligible_equal_weight']['2024-01-02']['weights'])
        self.assertAlmostEqual(sum(chosen.values()),.95)
        self.assertLessEqual(max(source.reads),'2023-12-29')
        with self.assertRaises(ValueError):build_targets(source,members,end='2026-01-05')

    def test_truncated_calendar_cannot_substitute_shorter_history(self):
        class Source:
            calendar=tuple([date(2023,m,15) for m in range(1,13)]+[date(2024,1,2)])
            def value(self,*args):return 1.
        with self.assertRaises(ValueError):build_targets(Source(),{},end='2024-01-02')
