import math
from datetime import date
import unittest
try:
    from stock_rsi.intermediate_momentum import intermediate_score,build_targets
except ImportError:intermediate_score=build_targets=None

class IntermediateMomentumTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(intermediate_score)
    def test_six_old_month_returns_have_the_right_sign(self):
        self.assertAlmostEqual(intermediate_score([100.,110.,120.,130.,140.,150.,160.]),.6)
        self.assertAlmostEqual(intermediate_score([100.,99.,98.,97.,96.,95.,94.]),-.06)
        with self.assertRaises(ValueError):intermediate_score([100.]*6)
        self.assertIsNone(intermediate_score([100.]*6+[None]))
        self.assertIsNone(intermediate_score([100.]*6+[math.inf]))
        self.assertIsNone(intermediate_score([100.]*6+[0.]))
    def test_fixed_month_boundaries_skip_latest_six_months(self):
        class Source:
            calendar=tuple([date(2022,12,30)]+[date(2023,m,28) for m in range(1,13)]+[date(2024,1,2),date(2024,1,31),date(2024,2,1),date(2026,1,5)])
            def __init__(self):self.close_reads=[];self.latest_price=100.
            def value(self,code,field,day):
                assert day<='2023-12-28','future read'
                if field in ('factor','volume'):return 1.
                assert field=='close';self.close_reads.append(day)
                if day=='2023-12-28':return self.latest_price
                assert day<='2023-06-28','excluded recent return close read'
                return 100.+int(code[-3:]) if day=='2023-06-28' else 100.
        members={f'SH600{i:03d}':[('2020-01-01','2025-12-31')] for i in range(200)}
        members['SZ000999']=[('2024-01-02','2025-12-31')]
        source=Source();targets,receipts=build_targets(source,members,end='2024-01-31')
        row=receipts[0];self.assertEqual(row['signal_begin_close'],'2022-12-30');self.assertEqual(row['signal_end_close'],'2023-06-28')
        chosen=targets['intermediate_mom12_7']['2024-01-02']['weights'];self.assertEqual(tuple(chosen),tuple(f'SH600{i:03d}' for i in range(199,179,-1)))
        self.assertAlmostEqual(sum(chosen.values()),.95)
        self.assertNotIn('SZ000999',targets['eligible_equal_weight']['2024-01-02']['weights'])
        source.latest_price=1e9;self.assertEqual(build_targets(source,members,end='2024-01-31')[0],targets)
        with self.assertRaises(ValueError):build_targets(source,members,end='2026-01-05')
    def test_truncated_exchange_calendar_cannot_shift_the_window(self):
        class Source:
            calendar=tuple([date(2023,m,28) for m in range(1,13)]+[date(2024,1,2)])
            def value(self,*args):return 1.
        with self.assertRaises(ValueError):build_targets(Source(),{},end='2024-01-02')
