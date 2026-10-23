from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import build_asset_availability_2026 as build
except ImportError:
    build=None


class AssetAvailabilityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build,'bounded asset availability runner missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.input=self.base/'original';self.input.write_text('original');self.request=self.base/'request.json'
        self.req={'input_sha256':{'source/original':build.sha(self.input)},'documents':[],'cohort':['SH600001'],
            'formations':[{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'},
                {'execution_session':'2026-01-05','as_of':'2025-12-31T15:05:00+08:00'}],
            'modes':['OBSERVED','RECONSTRUCTED_PUBLICATION_DAY_END']}
        build.write_once(self.request,self.req);self.reqsha=build.sha(self.request)
        for folder in (build.OLD_ASSETS,build.NEW_ASSETS,build.INDUSTRY,build.LEGACY):
            (self.base/folder).mkdir()
        for folder in (build.OLD_ASSETS,build.NEW_ASSETS):build.write_once(self.base/folder/'case_results.json',{})
        build.write_once(self.base/build.INDUSTRY/'catalog.json',{})
        f=self.req['formations'][0]
        for mode in self.req['modes']:
            snap=self.snapshot([],None,None,self.req['cohort'],f['as_of'],mode=mode)
            build.write_once(self.base/build.LEGACY/(f['execution_session']+'-'+mode+'.json'),snap)

    @staticmethod
    def snapshot(documents,reader,industry,cohort,as_of,*,mode):
        return {'as_of':datetime.fromisoformat(as_of).astimezone(timezone.utc).isoformat(),
            'visibility_mode':mode,'cohort_count':len(cohort),'classifications':[
                {'instrument':'SH600001','industry_status':'NOT_IN_SOURCE_VINTAGE',
                 'industry_classification_period':'2021Q3','annual_status':'NO_VISIBLE_ANNUAL_REPORT'}]}

    def run_source(self,builder=None):
        with patch.object(build,'verify',return_value=(self.req,{'source/original':self.input})):
            return build.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,builder=builder or self.snapshot)

    def test_explicit_session_month_transitions_and_invalid_calendars(self):
        days=['2023-12-29','2024-01-02','2024-01-03','2024-01-31','2024-02-01','2025-12-31','2026-01-05','2026-01-06']
        result=build.formations(days)
        self.assertEqual(result[0],{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'})
        self.assertEqual(result[-1],{'execution_session':'2026-01-05','as_of':'2025-12-31T15:05:00+08:00'})
        for bad in ([*days,days[-1]],list(reversed(days)),['2024-01-02','2024-01-03']):
            with self.assertRaises(ValueError):build.formations(bad)

    def test_all_modes_and_old_selection_parity_saved_before_success_and_no_overwrite(self):
        result=self.run_source();self.assertEqual(len(result['queries']),4)
        self.assertEqual(result['pre2026_parity_queries'],2)
        self.assertFalse(result['security_ranking_or_portfolio_returns_computed']);self.assertFalse(result['objective_achieved'])
        self.assertEqual(build.read(self.base/build.OUTPUT/'terminal.json')['pending_query_count'],0)
        with self.assertRaisesRegex(ValueError,'no resume'):self.run_source()

    def test_parity_rejects_changed_selection_but_allows_different_source_parse_states(self):
        def changed(*args,**kwargs):
            result=self.snapshot(*args,**kwargs)
            result['classifications'][0]['selected_capture_key']='forged'
            return result
        with self.assertRaisesRegex(ValueError,'legacy selection parity'):self.run_source(changed)
        term=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertEqual(term['pending_query_count'],4);self.assertEqual(term['completed_queries'],[])
        old=self.snapshot([],None,None,['SH600001'],'2023-12-29T15:05:00+08:00',mode='OBSERVED')
        new=build.read(self.base/build.LEGACY/'2024-01-02-OBSERVED.json')
        old['classifications'][0].update(annual_status='LATEST_SOURCE_SCHEMA_UNSUPPORTED',selected_source_status='SOURCE_SCHEMA_UNSUPPORTED')
        new['classifications'][0].update(annual_status='LATEST_ASSET_SOURCE_SUPPORTED_NOT_INVESTMENT_ADMITTED',selected_source_status='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA')
        build.assert_legacy_selection_parity(new,old)

    def test_interruption_preserves_original_error_prefix_and_changed_inputs(self):
        error=KeyboardInterrupt('bounded source stop');count=0
        def interrupted(*args,**kwargs):
            nonlocal count
            count+=1
            if count==2:
                self.input.unlink();self.request.write_text('{}');raise error
            return self.snapshot(*args,**kwargs)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(interrupted)
        self.assertIs(caught.exception,error)
        term=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertEqual(len(term['completed_queries']),1);self.assertEqual(term['pending_query_count'],3)
        self.assertEqual({r['input'] for r in term['postcheck']['mismatches']},{'source/original','frozen_source_request'})
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())

    def test_changed_dependency_prevents_success_even_after_every_query(self):
        def changed(*args,**kwargs):
            self.input.write_text('changed');return self.snapshot(*args,**kwargs)
        with self.assertRaisesRegex(ValueError,'unchanged asset availability'):self.run_source(changed)
        self.assertFalse((self.base/build.OUTPUT/'summary.json').exists())

    def test_2026_query_must_match_requested_clock_mode_and_cohort_count(self):
        def wrong_clock(*args,**kwargs):
            view=self.snapshot(*args,**kwargs)
            if args[4].startswith('2025-12-31'):view['as_of']='2026-01-05T07:05:00+00:00'
            return view
        with self.assertRaisesRegex(ValueError,'query identity'):self.run_source(wrong_clock)
        terminal=build.read(self.base/build.OUTPUT/'terminal.json')
        self.assertEqual(len(terminal['completed_queries']),2)
        self.assertEqual(terminal['pending_query_count'],2)


if __name__=='__main__':unittest.main()
