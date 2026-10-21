import copy
from datetime import date
import importlib
import math
import unittest

class ValueMomentumTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.exchange_value_momentum')
        except ModuleNotFoundError:self.fail('fixed two-sleeve value/momentum hypothesis absent')
    def test_eleven_returns_skip_latest_complete_month_and_reject_incomplete_history(self):
        api=self.api();prices=[100.]*11+[120.,9999.]
        self.assertAlmostEqual(.2,api.momentum_12_2(prices));self.assertAlmostEqual(.2,api.momentum_12_2(prices[:-1]+[.001]))
        for bad in (None,0.,-1.,math.inf,math.nan):self.assertIsNone(api.momentum_12_2(prices[:3]+[bad]+prices[4:]))
        with self.assertRaises(ValueError):api.momentum_12_2(prices[1:])
    def test_sleeve_budgets_add_overlap_and_never_choose_a_higher_scoring_leg(self):
        api=self.api();w=api.merge_equal_sleeves(('A','B'),('B','C'))
        self.assertEqual(set(w),{'A','B','C'});self.assertAlmostEqual(w['A'],.2375);self.assertAlmostEqual(w['B'],.475);self.assertAlmostEqual(sum(w.values()),.95)
        self.assertAlmostEqual(api.merge_equal_sleeves(('A',),('A',))['A'],.95)
        for v,m in (((),('A',)),(('A','A'),('B',))):
            with self.assertRaises(ValueError):api.merge_equal_sleeves(v,m)
    def fixture(self):
        ends=[date(2022,12,28)]+[date(2023,m,28) for m in range(1,13)]
        class Prices:
            calendar=tuple(ends+[date(2024,1,2),date(2024,1,31),date(2024,2,1),date(2026,1,5)])
            def __init__(self):self.reads=[]
            def value(self,code,field,day):
                assert day<='2023-12-28','future scalar query';self.reads.append((code,field,day))
                if field in ('factor','volume'):return 1.
                idx=ends.index(date.fromisoformat(day));return 100+int(code[-3:])/100 if idx==11 else 100.
        names={f'SZ000{i:03d}':[('2020-01-01','2025-12-31')] for i in range(100,200)}
        names['SZ000999']=[('2024-01-02','2025-12-31')]
        stocks={c:{'pe':str(i+1),'reported_special_name':False} for i,c in enumerate(names)}
        reports={'2023-11':{'month':'2023-11','article_build_day':'2023-12-07','table_build_day':'2023-12-07','table_sha256':'original','stocks':stocks}}
        return Prices(),names,reports
    def test_two_independent_rankings_same_historical_sample_and_source_month(self):
        api=self.api();p,m,r=self.fixture();t,rec=api.build_targets(p,m,r,end='2024-01-31');x=rec[0]
        self.assertEqual(x['value_selected'],[f'SZ000{i:03d}' for i in range(100,110)])
        self.assertEqual(x['momentum_selected'],[f'SZ000{i:03d}' for i in range(199,189,-1)])
        w=t[api.FAMILIES[0]]['2024-01-02']['weights'];self.assertEqual(len(w),20);self.assertAlmostEqual(sum(w.values()),.95);self.assertAlmostEqual(w['SZ000100'],.0475)
        self.assertEqual(x['source_month'],'2023-11');self.assertEqual(x['ranking_return_months'],[f'2023-{i:02d}' for i in range(1,12)])
        self.assertEqual(x['skipped_ranking_month'],'2023-12');self.assertEqual(x['latest_factor_price_read'],'2023-12-28');self.assertNotIn('SZ000999',w)
        with self.assertRaises(ValueError):api.build_targets(p,m,r,end='2026-01-05')
    def test_source_and_calendar_fail_closed_and_missing_pe_is_not_neutral(self):
        api=self.api();p,m,r=self.fixture();bad=copy.deepcopy(r);bad['2023-11']['table_build_day']='2024-01-03'
        with self.assertRaises(ValueError):api.build_targets(p,m,bad,end='2024-01-31')
        bad=copy.deepcopy(r);bad['2023-11']['stocks']['SZ000100']['pe']='NaN'
        with self.assertRaises(ValueError):api.build_targets(p,m,bad,end='2024-01-31')
        r['2023-11']['stocks']['SZ000100']['pe']=None;t,rec=api.build_targets(p,m,r,end='2024-01-31');self.assertEqual(rec[0]['eligible'],99);self.assertNotIn('SZ000100',t[api.FAMILIES[0]]['2024-01-02']['weights'])
        p.calendar=tuple(d for d in p.calendar if d!=date(2023,6,28))
        with self.assertRaises(ValueError):api.build_targets(p,m,r,end='2024-01-31')

if __name__=='__main__':unittest.main()
