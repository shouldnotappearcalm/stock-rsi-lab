import ast
from datetime import date
from pathlib import Path
import unittest

from stock_rsi import annual_assets as assets
from stock_rsi import asset_expansion_monthly as old
try:
    from stock_rsi import asset_expansion_horizon as signal
except ImportError:
    signal=None
from stock_rsi.data import digest
from tests import test_asset_expansion_monthly as fixtures
from tests.test_annual_profitability import pages


class AssetExpansionHorizonTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(signal,'bounded horizon selector missing')

    def fixture(self):
        f=list(fixtures.AssetExpansionTests().fixture());prices,members,cohort,views,cases=f
        prices.calendar=tuple(date.fromisoformat(d) for d in ('2025-12-31','2026-01-05','2026-01-30','2026-02-02'))
        def value(code,field,day):
            if day!='2025-12-31':raise AssertionError('execution-day/future quote read')
            prices.reads.append((code,field,day));return None if code in prices.missing else 1.
        prices.value=value
        view=views.pop('2024-01-02');view['as_of']='2025-12-31T07:05:00+00:00';views['2026-01-05']=view
        for i,code in enumerate(cohort):
            members[code]=[('2020-01-01','2026-12-31')];key=str(i+1)
            balances=assets.parse_balance_only(pages(2024),2024)
            for period,c in balances.items():
                c['row_text']=c['row_text'].replace('200.00',f'{100+i}.00',1);c['row_text_sha256']=digest(c['row_text'])
                if period=='2024-12-31':c.update(literal=f'{100+i}.00',value_CNY=f'{100+i}.00')
            cases[key].update(fiscal_year=2024,asset_report=assets.make_report(code,2024,'2025-04-29',
                '2026-10-22T00:00:00+00:00','a'*64,key,balances))
            view['classifications'][i].update(latest_fiscal_year=2024,latest_publication_day='2025-04-29')
        return f

    def build(self,f):return signal.build_targets(*f[:4],f[4].__getitem__,start='2026-01-05',end='2026-01-30')

    def test_legacy_window_outputs_and_receipts_equal_and_old_cap_stays(self):
        f=fixtures.AssetExpansionTests().fixture();args=(*f[:4],f[4].__getitem__)
        self.assertEqual(old.build_targets(*args,end='2024-01-31'),signal.build_targets(*args,end='2024-01-31'))
        with self.assertRaises(ValueError):old.build_targets(*args,end='2026-01-05')
        with self.assertRaises(ValueError):signal.build_targets(*args,end='2026-10-22')

    def test_2026_exact_rule_and_prior_close_only_ignore_hidden_future(self):
        f=self.fixture();targets,receipts=self.build(f)
        self.assertEqual(list(targets[signal.PRIMARY]['2026-01-05']['weights']),f[2][:11])
        self.assertAlmostEqual(sum(targets[signal.PRIMARY]['2026-01-05']['weights'].values()),.95)
        self.assertEqual(receipts[0]['ranked_source'][f[2][-1]]['expansion_fraction'],'109/100')
        self.assertEqual({d for _,_,d in f[0].reads},{'2025-12-31'})
        f[3]['2026-02-02']=object();f[4]['hidden-future-case']=object()
        self.assertEqual(self.build(f),(targets,receipts))

    def test_latest_failure_current_only_and_fixed100_guard_are_unchanged(self):
        f=self.fixture();f[4]['1'].update(status='COVER_IDENTITY_UNVERIFIED',asset_report=None)
        r=f[4]['2']['asset_report'];r['payload']['balances'].pop('2023-12-31');r['record_id']=digest({k:v for k,v in r.items() if k!='record_id'})
        _,receipts=self.build(f);reasons={r['instrument']:r['reason'] for r in receipts[0]['cohort_admission']}
        self.assertEqual(reasons[f[2][0]],'LATEST_COVER_IDENTITY_UNVERIFIED')
        self.assertEqual(reasons[f[2][1]],'LATEST_HAS_NO_EXPLICIT_PRIOR_YEAR_END')
        for row in f[3]['2026-01-05']['classifications'][2:11]:row.pop('selected_capture_key');row['annual_status']='NO_VISIBLE_ANNUAL_REPORT'
        with self.assertRaisesRegex(ValueError,'fixed100'):self.build(f)

    def test_rank_body_matches_original_semantics_except_first_window_guard(self):
        def body(module):
            tree=ast.parse(Path(module.__file__).read_text())
            f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_targets')
            return ast.dump(ast.Module(body=f.body[1:],type_ignores=[]))
        self.assertEqual(body(old),body(signal))


if __name__=='__main__':unittest.main()
