from datetime import date
import copy
from fractions import Fraction
import unittest

try:
    from stock_rsi import gross_profitability_monthly as signal
except ImportError:
    signal = None

from stock_rsi import annual_profitability as annual
from stock_rsi.data import digest
from tests.test_profitability_availability import document, case


class GrossProfitabilityMonthlyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(signal, 'gross profitability monthly signal missing')

    def fixture(self):
        class Prices:
            calendar = tuple(date.fromisoformat(s) for s in
                ('2023-12-29','2024-01-02','2024-01-31','2024-02-01','2024-06-28',
                 '2024-07-01','2024-07-31','2024-08-01','2025-12-31'))
            def __init__(self): self.reads=[]; self.missing=set()
            def value(self, code, field, day):
                self.reads.append((code,field,day))
                if day > '2023-12-29': raise AssertionError('future formation quote')
                return None if code in self.missing else 1.
        prices=Prices(); cohort=[f'SZ000{i:03}' for i in range(100,210)]
        memberships={c:[('2020-01-01','2025-12-31')] for c in cohort}
        rows=[]
        for i,code in enumerate(cohort):
            doc=document(2022,'2023-04-29',str(i+1));doc['instrument']=code
            observation=case(doc)['source_observations'][0]
            revenue=observation['payload']['cells']['revenue']
            revenue.update(value_CNY=f'{100+i}.00',literal=f'{100+i}.00')
            revenue['row_text']=revenue['row_text'].replace('100.00',f'{100+i}.00',1)
            revenue['row_text_sha256']=digest(revenue['row_text'])
            observation['record_id']=digest({k:v for k,v in observation.items() if k!='record_id'})
            current=annual.snapshot_observations([observation],'2023-12-29T15:05:00+08:00',mode=annual.RECONSTRUCTED)['records'][0]
            rows.append({'instrument':code,'industry_status':'NONFINANCIAL_IN_SOURCE_VINTAGE',
                'annual_status':'LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED','latest_fiscal_year':2022,
                'selected_source_sha256':doc['source_sha256'],'current_observation':current})
        view={'as_of':'2023-12-29T07:05:00+00:00','visibility_mode':annual.RECONSTRUCTED,
              'cohort_count':len(cohort),'classifications':rows}
        return prices,memberships,cohort,{'2024-01-02':view}

    def test_exact_gross_profit_rank_controls_and_95_percent_use_only_prior_close(self):
        prices,members,cohort,views=self.fixture()
        targets,receipts=signal.build_targets(prices,members,cohort,views,end='2024-01-31')
        primary=targets[signal.PRIMARY]['2024-01-02']['weights']
        self.assertEqual(list(primary),[f'SZ000{i:03}' for i in range(209,198,-1)])
        self.assertEqual(list(targets[signal.LOW_CONTROL]['2024-01-02']['weights']),cohort[:11])
        self.assertEqual(list(targets['eligible_equal_weight']['2024-01-02']['weights']),cohort)
        self.assertAlmostEqual(sum(primary.values()),.95)
        self.assertEqual(receipts[0]['eligible'],110)
        self.assertEqual(receipts[0]['ranked_source'][cohort[-1]]['score_fraction'],str(Fraction(139,200)))
        self.assertEqual({day for _,_,day in prices.reads},{'2023-12-29'})
        self.assertFalse(receipts[0]['investment_factor_admitted'])

    def test_each_exclusion_retained_without_future_parse_success_pool(self):
        prices,members,cohort,views=self.fixture();rows=views['2024-01-02']['classifications']
        members[cohort[0]]=[('2024-01-02','2025-12-31')]
        rows[1]['industry_status']='NOT_IN_SOURCE_VINTAGE'
        rows[2]['annual_status']='LATEST_SOURCE_SCHEMA_UNSUPPORTED';del rows[2]['current_observation']
        rows[3]['latest_fiscal_year']=2021
        prices.missing.add(cohort[4])
        targets,receipts=signal.build_targets(prices,members,cohort,views,end='2024-01-31')
        reasons={r['instrument']:r['reason'] for r in receipts[0]['cohort_admission']}
        self.assertEqual(reasons[cohort[0]],'NOT_IN_FORMATION_MEMBERSHIP')
        self.assertEqual(reasons[cohort[1]],'NOT_NONFINANCIAL_IN_2021_SOURCE')
        self.assertEqual(reasons[cohort[2]],'LATEST_SOURCE_SCHEMA_UNSUPPORTED')
        self.assertEqual(reasons[cohort[3]],'STALE_ANNUAL_SOURCE')
        self.assertEqual(reasons[cohort[4]],'NO_POSITIVE_FORMATION_QUOTE')
        self.assertEqual(len(reasons),110);self.assertEqual(receipts[0]['eligible'],105)

    def test_source_view_future_mode_identity_or_duplicate_rows_cannot_be_scored(self):
        for mutate in [lambda v:v.update(as_of='2024-01-31T07:05:00+00:00'),
                       lambda v:v.update(visibility_mode='OBSERVED'),
                       lambda v:v['classifications'].append(copy.deepcopy(v['classifications'][0])),
                       lambda v:v['classifications'][0].update(selected_source_sha256='b'*64),
                       lambda v:v['classifications'][0]['current_observation']['source'].update(public_day_end_at='2024-01-03T15:59:59+00:00')]:
            prices,members,cohort,views=self.fixture();mutate(views['2024-01-02'])
            with self.assertRaises(ValueError):signal.build_targets(prices,members,cohort,views,end='2024-01-31')

    def test_coverage_failure_and_hidden_future_views_are_never_used(self):
        prices,members,cohort,views=self.fixture();views['2026-01-05']={'future':'do not inspect'}
        signal.build_targets(prices,members,cohort,views,end='2024-01-31')
        for row in views['2024-01-02']['classifications'][:11]:row['annual_status']='NO_VISIBLE_ANNUAL_REPORT'
        with self.assertRaisesRegex(ValueError,'coverage'):signal.build_targets(prices,members,cohort,views,end='2024-01-31')
        with self.assertRaises(ValueError):signal.build_targets(prices,members,cohort,views,end='2026-01-05')

    def test_july_freshness_boundary_and_exact_tie_keeps_code_order(self):
        self.assertEqual(signal.minimum_fiscal_year('2024-06-30'),2022)
        self.assertEqual(signal.minimum_fiscal_year('2024-07-01'),2023)
        chosen=signal.rank_decile({'SZ000003':Fraction(1,3),'SZ000001':Fraction(1,3),'SZ000002':Fraction(-1,4)})
        self.assertEqual(chosen,('SZ000001',))
        self.assertEqual(signal.rank_decile({'SZ000003':Fraction(1,3),'SZ000001':Fraction(1,3),'SZ000002':Fraction(-1,4)},lowest=True),('SZ000002',))

    def test_each_completed_formation_can_be_persisted_before_a_later_failure(self):
        prices,members,cohort,views=self.fixture();completed=[]
        with self.assertRaises(KeyError):
            signal.build_targets(prices,members,cohort,views,end='2024-02-01',
                on_formation=lambda day,targets,receipt:completed.append((day,targets,receipt)))
        self.assertEqual([row[0] for row in completed],['2024-01-02'])
        self.assertEqual(completed[0][2]['eligible'],110)

    def test_large_active_cohort_with_under_half_source_coverage_is_rejected(self):
        prices,members,cohort,views=self.fixture();view=views['2024-01-02']
        for i in range(300,411):
            code=f'SZ000{i:03}';cohort.append(code);members[code]=[('2020-01-01','2025-12-31')]
            view['classifications'].append({'instrument':code,'industry_status':'NONFINANCIAL_IN_SOURCE_VINTAGE',
                'annual_status':'NO_VISIBLE_ANNUAL_REPORT'})
        view['cohort_count']=221
        with self.assertRaisesRegex(ValueError,'coverage'):
            signal.build_targets(prices,members,cohort,views,end='2024-01-31')


if __name__=='__main__':unittest.main()
