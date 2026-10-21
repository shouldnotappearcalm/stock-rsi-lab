import copy
from datetime import date
import importlib
import unittest

class ExchangeSizeTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.exchange_size')
        except ModuleNotFoundError:self.fail('separate frozen published-size hypothesis absent')
    def fixture(self):
        class Prices:
            calendar=tuple(date.fromisoformat(d) for d in ('2023-11-30','2023-12-29','2024-01-02','2024-01-31','2024-02-01','2025-12-31','2026-01-05'))
            def __init__(self):self.reads=[]
            def value(self,code,field,day):
                self.reads.append(day)
                if day>'2023-12-29':raise AssertionError('future factor query')
                return 1.
        members={f'SZ000{i:03d}':[('2020-01-01','2030-12-31')] for i in range(100,200)}
        stocks={c:{'pe':None,'issued_10k_shares':str(i+100),'listed_10k_shares':'1','close':'2','reported_special_name':False} for i,c in enumerate(members)}
        reports={'2023-11':{'month':'2023-11','article_build_day':'2023-12-07','table_build_day':'2023-12-07','table_sha256':'source','stocks':stocks}}
        return Prices(),members,reports
    def test_published_product_uses_issued_units_not_listed_or_current_price_and_ignores_pe(self):
        api=self.api();p,m,r=self.fixture();r['2023-11']['stocks']['SZ000100']['close']='200';r['2023-11']['stocks']['SZ000101']['pe']='-5'
        t,rec=api.build_targets(p,m,r,end='2024-01-31');selected=tuple(t['szse_monthly_small_issued_cap']['2024-01-02']['weights'])
        self.assertEqual(tuple(f'SZ000{i:03d}' for i in range(101,111)),selected)
        self.assertEqual('200000000',rec[0]['published_A_cap_CNY']['SZ000100']);self.assertEqual('2023-11',rec[0]['source_month'])
        self.assertAlmostEqual(.95,sum(t['szse_monthly_small_issued_cap']['2024-01-02']['weights'].values()))
        self.assertEqual(max(p.reads),'2023-12-29')
        with self.assertRaises(ValueError):api.build_targets(p,m,r,end='2026-01-05')
    def test_missing_share_field_excludes_stock_and_insufficient_historical_source_coverage_stops(self):
        api=self.api();p,m,r=self.fixture();r['2023-11']['stocks']['SZ000100']['issued_10k_shares']=None
        t,rec=api.build_targets(p,m,r,end='2024-01-31')
        self.assertEqual(99,rec[0]['eligible']);self.assertNotIn('SZ000100',t['szse_monthly_small_issued_cap']['2024-01-02']['weights'])
        for i in range(194,200):del r['2023-11']['stocks'][f'SZ000{i:03d}']
        with self.assertRaisesRegex(ValueError,'coverage'):api.build_targets(p,m,r,end='2024-01-31')
    def test_equal_products_break_by_code_and_invalid_shares_or_late_source_reject(self):
        api=self.api();p,m,r=self.fixture()
        for row in r['2023-11']['stocks'].values():row['issued_10k_shares']='100'
        t,_=api.build_targets(p,m,r,end='2024-01-31');self.assertEqual(tuple(f'SZ000{i:03d}' for i in range(100,110)),tuple(t['szse_monthly_small_issued_cap']['2024-01-02']['weights']))
        for change in ('late','invalid'):
            bad=copy.deepcopy(r)
            if change=='late':bad['2023-11']['table_build_day']='2024-01-03'
            else:bad['2023-11']['stocks']['SZ000100']['listed_10k_shares']='101'
            with self.subTest(change=change),self.assertRaises(ValueError):api.build_targets(p,m,bad,end='2024-01-31')

if __name__=='__main__':unittest.main()
