"""Synthetic histories catch wrong skip periods, season labels and future reads."""
import calendar
import copy
from datetime import date
import math
import unittest

try:
    from stock_rsi.return_families import return_scores, highest_decile, build_targets, choose_development_lead
except ImportError:
    return_scores=highest_decile=build_targets=choose_development_lead=None


class ReturnFamilyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(return_scores,'return-family implementation is missing')

    def test_twenty_day_sign_and_long_term_skip_are_independent_of_recent_year(self):
        monthly=[100.]*61;monthly[48]=80.;monthly[-1]=120.
        months=[(i%12)+1 for i in range(61)]
        first=return_scores(monthly,months,[100.]*20+[90.],2)
        self.assertAlmostEqual(first['contrarian20'],.1)
        self.assertAlmostEqual(first['contrarian60_12'],.2)
        changed=monthly.copy();changed[49:]=[1000.]*12
        second=return_scores(changed,months,[100.]*20+[90.],2)
        self.assertEqual(first['contrarian60_12'],second['contrarian60_12'])

    def test_seasonality_predicts_upcoming_month_and_missing_values_cannot_rank(self):
        months=[12]+[m for _ in range(5) for m in range(1,13)]
        monthly=[100.]
        for month in months[1:]:monthly.append(monthly[-1]*(1.1 if month==1 else 1))
        self.assertAlmostEqual(return_scores(monthly,months,[100.]*21,1)['seasonal5'],.1)
        self.assertAlmostEqual(return_scores(monthly,months,[100.]*21,2)['seasonal5'],0)
        broken=monthly.copy();broken[4]=None
        self.assertIsNone(return_scores(broken,months,[100.]*21,1))
        self.assertIsNone(return_scores(monthly,months,[100.]*20+[float('nan')],1))
        self.assertEqual(highest_decile({f'S{i:02d}':-1. for i in range(20)}),('S00','S01'))
        with self.assertRaises(ValueError):highest_decile({'A':math.inf})

    def test_target_formation_is_unchanged_by_future_prices_and_is_capped_before_2026(self):
        class SyntheticPrices:
            def __init__(self):
                monthly=[date(y,m,calendar.monthrange(y,m)[1]) for y in range(2018,2026) for m in range(1,13)]
                self.calendar=tuple(sorted(monthly+[date(2024,1,2),date(2026,1,5)]));self.reads=[];self.future=999.
            def value(self,symbol,field,day):
                self.reads.append(day)
                if day>'2025-12-31':raise AssertionError('future market read')
                return 1. if field in ('volume','factor') else 100.
        source=SyntheticPrices();members={f'SH600{i:03d}':[('2010-01-01','2030-12-31')] for i in range(200)}
        targets,receipts=build_targets(source,members)
        self.assertEqual(len(receipts),24)
        self.assertEqual(targets['contrarian20']['2024-01-02']['as_of'],'2023-12-31')
        self.assertEqual(len(targets['contrarian20']['2024-01-02']['weights']),20)
        source.future=1e9
        self.assertEqual(build_targets(source,members)[0],targets)
        self.assertLessEqual(max(source.reads),'2025-12-31')
        with self.assertRaises(ValueError):build_targets(source,members,end='2026-01-05')

    def test_lead_selection_uses_worst_development_year_and_rejects_unverified_marks(self):
        def metrics(a,b,turn=1):return {'2024_return_pct':a,'2025_return_pct':b,'average_exposure_pct':95.,
            'unverified_held_marks':0,'turnover_x_initial':turn}
        results={'A':metrics(12,13),'B':metrics(10,90),'C':metrics(-1,100)}
        self.assertEqual(choose_development_lead(results),'A')
        results['A']['unverified_held_marks']=1
        self.assertEqual(choose_development_lead(results),'B')
        results['B']['2025_return_pct']=-1
        self.assertIsNone(choose_development_lead(results))
