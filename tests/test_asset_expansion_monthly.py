import copy
from datetime import date
from fractions import Fraction
import unittest

try:
    from stock_rsi import asset_expansion_monthly as signal
except ImportError:
    signal=None

from stock_rsi import annual_assets as assets
from stock_rsi.data import digest
from tests.test_annual_profitability import pages


class AssetExpansionTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(signal,'asset-expansion signal module missing')

    def fixture(self):
        class Prices:
            calendar=tuple(date.fromisoformat(s) for s in ('2023-12-29','2024-01-02','2024-01-31','2024-02-01','2025-12-31'))
            def __init__(self):self.reads=[];self.missing=set()
            def value(self,code,field,day):
                if day>'2023-12-29':raise AssertionError('future formation quote')
                self.reads.append((code,field,day));return None if code in self.missing else 1.
        prices=Prices();cohort=[f'SZ000{i:03}' for i in range(100,210)];cases={};metadata=[]
        for i,code in enumerate(cohort):
            balances=assets.parse_balance_only(pages(2022),2022)
            for period,cell in balances.items():
                cell['row_text']=cell['row_text'].replace('200.00',f'{100+i}.00',1)
                cell['row_text_sha256']=digest(cell['row_text'])
                if period=='2022-12-31':cell.update(literal=f'{100+i}.00',value_CNY=f'{100+i}.00')
            report=assets.make_report(code,2022,'2023-04-29','2026-10-22T00:00:00+00:00','a'*64,str(i+1),balances)
            key=str(i+1);cases[key]={'capture_key':key,'instrument':code,'fiscal_year':2022,'source_sha256':'a'*64,
                'status':'ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA','asset_report':report}
            metadata.append({'instrument':code,'industry_status':'NONFINANCIAL_IN_SOURCE_VINTAGE',
                'annual_status':'LATEST_SOURCE_SCHEMA_UNSUPPORTED','latest_fiscal_year':2022,
                'latest_publication_day':'2023-04-29','selected_capture_key':key,'selected_source_sha256':'a'*64})
        views={'2024-01-02':{'as_of':'2023-12-29T07:05:00+00:00','visibility_mode':assets.RECONSTRUCTED,
            'cohort_count':len(cohort),'classifications':metadata}}
        members={c:[('2020-01-01','2025-12-31')] for c in cohort}
        return prices,members,cohort,views,cases

    def build(self,fixture,**kwargs):
        prices,members,cohort,views,cases=fixture
        return signal.build_targets(prices,members,cohort,views,cases.__getitem__,end='2024-01-31',**kwargs)

    def test_low_expansion_rank_is_exact_and_ignores_GP_numeric_failure(self):
        f=self.fixture();targets,receipts=self.build(f)
        self.assertEqual(list(targets[signal.PRIMARY]['2024-01-02']['weights']),f[2][:11])
        self.assertEqual(list(targets[signal.HIGH_CONTROL]['2024-01-02']['weights']),list(reversed(f[2]))[:11])
        self.assertEqual(list(targets['eligible_equal_weight']['2024-01-02']['weights']),f[2])
        self.assertAlmostEqual(sum(targets[signal.PRIMARY]['2024-01-02']['weights'].values()),.95)
        self.assertEqual(receipts[0]['ranked_source'][f[2][-1]]['expansion_fraction'],'109/100')
        self.assertEqual({d for _,_,d in f[0].reads},{'2023-12-29'})
        self.assertFalse(receipts[0]['investment_factor_admitted'])

    def test_latest_failure_and_current_only_report_never_use_older_pairs(self):
        f=self.fixture();rows=f[3]['2024-01-02']['classifications'];cases=f[4]
        cases['older-unused']=copy.deepcopy(cases['1'])
        cases['1'].update(status='ASSET_SOURCE_SCHEMA_UNSUPPORTED',asset_report=None)
        report=cases['2']['asset_report'];current=copy.deepcopy(report['payload']['balances']['2022-12-31'])
        current.update(header_line='项目 附注 2022年12月31日 2022年1月1日',reported_comparative_balance_date='2022-01-01')
        cases['2']['asset_report']=assets.make_report(f[2][1],2022,'2023-04-29','2026-10-22T00:00:00+00:00','a'*64,'2',{'2022-12-31':current})
        rows[2].pop('selected_capture_key');rows[2]['annual_status']='AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'
        rows[3]['industry_status']='NOT_IN_SOURCE_VINTAGE'
        rows[4]['latest_fiscal_year']=2021
        f[1][f[2][5]]=[('2024-01-02','2025-12-31')];f[0].missing.add(f[2][6])
        _,receipts=self.build(f);reasons={r['instrument']:r['reason'] for r in receipts[0]['cohort_admission']}
        self.assertEqual([reasons[c] for c in f[2][:7]],['LATEST_ASSET_SOURCE_SCHEMA_UNSUPPORTED',
            'LATEST_HAS_NO_EXPLICIT_PRIOR_YEAR_END','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS',
            'NOT_NONFINANCIAL_IN_2021_SOURCE','STALE_ANNUAL_ASSETS','NOT_IN_FORMATION_MEMBERSHIP','NO_POSITIVE_FORMATION_QUOTE'])
        self.assertEqual(receipts[0]['eligible'],103);self.assertEqual(len(reasons),110)

    def test_future_report_payload_is_not_hashed_and_unaligned_metadata_views_fail(self):
        for change in [lambda v,c:v.update(as_of='2024-01-31T07:05:00+00:00'),
                       lambda v,c:v.update(visibility_mode='OBSERVED'),
                       lambda v,c:v['classifications'].append(copy.deepcopy(v['classifications'][0])),
                       lambda v,c:c['1'].update(source_sha256='b'*64),
                       lambda v,c:c['1']['asset_report'].update(public_day_end_at='2024-01-03T15:59:59+00:00',payload=object())]:
            f=self.fixture();change(f[3]['2024-01-02'],f[4])
            with self.subTest(change=change),self.assertRaises(ValueError):self.build(f)

    def test_source_digest_and_fiscal_column_corruption_fail(self):
        for mutate in [lambda r:r['payload']['balances']['2021-12-31'].update(value_CNY='999.00'),
                       lambda r:r['payload']['balances']['2021-12-31'].update(column_index=0)]:
            f=self.fixture();r=f[4]['1']['asset_report'];mutate(r)
            if r['payload']['balances']['2021-12-31']['column_index']==0:
                r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'})
            with self.assertRaises(ValueError):self.build(f)

    def test_future_views_are_ignored_and_minimum100_is_the_declared_coverage_guard(self):
        f=self.fixture();f[3]['2026-01-05']={'future':'not read'};f[4]['future-unused']=object()
        self.build(f)
        for row in f[3]['2024-01-02']['classifications'][:11]:row.pop('selected_capture_key');row['annual_status']='NO_VISIBLE_ANNUAL_REPORT'
        with self.assertRaisesRegex(ValueError,'coverage'):self.build(f)
        with self.assertRaises(ValueError):signal.build_targets(f[0],f[1],f[2],f[3],f[4].__getitem__,end='2026-01-05')

    def test_completed_formation_prefix_is_reported_before_later_missing_metadata(self):
        f=self.fixture();completed=[]
        with self.assertRaises(KeyError):signal.build_targets(f[0],f[1],f[2],f[3],f[4].__getitem__,end='2024-02-01',
            on_formation=lambda day,targets,receipt:completed.append((day,receipt['eligible'])))
        self.assertEqual(completed,[('2024-01-02',110)])


if __name__=='__main__':unittest.main()
