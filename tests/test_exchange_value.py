from datetime import date
import copy
import unittest

try:
    from stock_rsi.exchange_value import build_targets
except ImportError:
    build_targets = None


class ExchangeValueTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(build_targets, 'published monthly value module missing')

    def fixture(self):
        class Prices:
            calendar = tuple(date.fromisoformat(d) for d in (
                '2023-11-30','2023-12-29','2024-01-02','2024-01-31','2024-02-01','2025-12-31','2026-01-05'))
            def __init__(self): self.reads=[]
            def value(self,code,field,day):
                self.reads.append(day)
                if day>'2023-12-29': raise AssertionError('future decision read')
                return 1.
        members={f'SZ000{i:03d}':[('2020-01-01','2030-12-31')] for i in range(100,200)}
        stocks={c:{'pe':str(i+1),'reported_special_name':False} for i,c in enumerate(members)}
        stocks['SZ000100']['reported_special_name']=True
        stocks['SZ000101']['pe']=None
        reports={'2023-11':{'month':'2023-11','article_build_day':'2023-12-07',
            'table_build_day':'2023-12-07','table_sha256':'source-proof','stocks':stocks}}
        return Prices(),members,reports

    def test_value_ranks_only_historical_eligible_names_with_full_next_month_lag(self):
        source,members,reports=self.fixture()
        targets,receipts=build_targets(source,members,reports,end='2024-01-31')
        weights=targets['szse_monthly_low_pe']['2024-01-02']['weights']
        self.assertEqual(tuple(weights),tuple(f'SZ000{i:03d}' for i in range(102,111)))
        self.assertAlmostEqual(sum(weights.values()),.95)
        self.assertEqual(receipts[0]['source_month'],'2023-11')
        self.assertEqual(receipts[0]['formation_asof'],'2023-12-29')
        self.assertLessEqual(max(source.reads),'2023-12-29')
        with self.assertRaises(ValueError):build_targets(source,members,reports,end='2026-01-05')

    def test_late_document_and_incomplete_public_snapshot_fail_before_ranking(self):
        source,members,reports=self.fixture()
        bad=copy.deepcopy(reports);bad['2023-11']['table_build_day']='2024-01-03'
        with self.assertRaises(ValueError):build_targets(source,members,bad,end='2024-01-31')
        del reports['2023-11']['stocks']['SZ000199']
        for i in range(190,199):del reports['2023-11']['stocks'][f'SZ000{i:03d}']
        with self.assertRaises(ValueError):build_targets(source,members,reports,end='2024-01-31')
