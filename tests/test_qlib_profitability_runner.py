import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import run_qlib_profitability_pre2026 as runner
except ImportError:
    runner = None


class ProfitabilityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(runner, 'profitability development runner missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.input=self.base/'source';self.input.write_text('source')
        self.request_file=self.base/'request.json'
        self.req={'input_sha256':{'source/source':runner.sha(self.input)},'provider_relative':'provider',
            'output_subdir':runner.OUTPUT,'formations':[{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'}]}
        runner.write_once(self.request_file,self.req);self.reqsha=runner.sha(self.request_file)

    def form(self,*args):
        targets={name:{'2024-01-02':{'as_of':'2023-12-29','weights':{'SZ000001':.95}}} for name in runner.NAMES}
        return targets,[{'formation_asof':'2023-12-29','latest_factor_price_read':'2023-12-29'}]

    def simulate(self,*args,**kwargs):
        runner.write_once(kwargs['out']/'actual-boundary-artifact.json',{'name':kwargs['name'],'extra_bps':kwargs['extra_bps']})
        return {'status':'DAILY_PROXY_DEVELOPMENT_RECONCILED','2024_return_pct':2.,'2025_return_pct':3.,
            'average_exposure_pct':94.,'unverified_held_marks':0,'turnover_x_initial':4.}

    def run_trial(self,simulation=None):
        with patch.object(runner,'verify',return_value=(self.req,{'source/source':self.input})):
            return runner.run(self.base,self.base,self.base/'membership',self.request_file,self.reqsha,
                form_targets=self.form,simulation=simulation or self.simulate)

    def test_six_profiles_complete_only_primary_can_be_lead_and_fresh_output_is_required(self):
        summary=self.run_trial();out=self.base/runner.OUTPUT
        self.assertEqual(len(summary['results_by_extra_bps_and_family']),6)
        self.assertEqual(summary['selected_development_lead'],runner.PRIMARY)
        self.assertFalse(summary['objective_achieved']);self.assertFalse(summary['raw_share_execution_verified'])
        self.assertEqual(len(list(out.rglob('actual-boundary-artifact.json'))),6)
        self.assertEqual(runner.read(out/'terminal.json')['pending_profiles'],[])
        with self.assertRaisesRegex(ValueError,'no resume'):self.run_trial()

    def test_negative_primary_is_rejected_even_when_control_is_profitable(self):
        def simulation(*args,**kwargs):
            result=self.simulate(*args,**kwargs)
            if kwargs['name']==runner.PRIMARY:result['2024_return_pct']=-1.
            return result
        self.assertIsNone(self.run_trial(simulation)['selected_development_lead'])

    def test_original_simulation_interrupt_keeps_prefix_and_hashes_deleted_input_and_request(self):
        original=KeyboardInterrupt('Qlib boundary interruption')
        def simulation(*args,**kwargs):
            if kwargs['name']!='gp_assets_top_decile_conditional':
                self.input.unlink();self.request_file.write_text('{}');raise original
            return self.simulate(*args,**kwargs)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_trial(simulation)
        self.assertIs(caught.exception,original)
        out=self.base/runner.OUTPUT;terminal=runner.read(out/'terminal.json')
        self.assertEqual(len(terminal['completed_profiles']),1);self.assertEqual(len(terminal['pending_profiles']),5)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},{'source/source','frozen_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_post_run_source_change_blocks_summary_and_wrong_request_hash_never_forms_targets(self):
        def simulation(*args,**kwargs):
            result=self.simulate(*args,**kwargs);self.input.write_text('changed');return result
        with self.assertRaisesRegex(ValueError,'unchanged'):self.run_trial(simulation)
        self.assertFalse((self.base/runner.OUTPUT/'summary.json').exists())
        other=self.base/'unused'
        with self.assertRaisesRegex(ValueError,'request'):
            runner.verify(other,self.base,self.base/'membership',self.request_file,'bad-hash')
        self.assertFalse(other.exists())

    def test_incomplete_metrics_fail_inside_preserved_terminal_before_profile_completion(self):
        def simulation(*args,**kwargs):
            result=self.simulate(*args,**kwargs);del result['average_exposure_pct'];return result
        with self.assertRaisesRegex(ValueError,'complete finite development metrics'):
            self.run_trial(simulation)
        terminal=runner.read(self.base/runner.OUTPUT/'terminal.json')
        self.assertEqual(terminal['completed_profiles'],[])
        self.assertEqual(len(terminal['pending_profiles']),6)
        self.assertEqual(terminal['original_error']['type'],'ValueError')
        self.assertFalse((self.base/runner.OUTPUT/'summary.json').exists())

    @unittest.skipUnless(importlib.util.find_spec('pandas'), 'optional numerical summary requires pandas')
    def test_net_returns_equal_continuous_account_and_years_do_not_reset(self):
        import pandas as pd
        report=pd.DataFrame({'return':[.10,-.02,.05,-.01],'cost':[0.,0.,0.,0.],
            'account':[1100.,1078.,1131.9,1120.581],'value':[1045.,1024.1,1075.305,1064.55195],
            'total_cost':[0.,0.,0.,0.],'total_turnover':[0.,100.,200.,300.]},
            index=pd.to_datetime(['2024-01-02','2024-12-31','2025-01-02','2025-12-31']))
        summary=runner.summarize_report(report,1000)
        self.assertAlmostEqual(summary['2024_return_pct'],7.8)
        self.assertAlmostEqual(summary['2025_return_pct'],3.95)
        self.assertAlmostEqual(summary['net_compound_return_pct'],12.0581)
        report.loc[pd.Timestamp('2025-01-02'),'account']=1000.
        with self.assertRaisesRegex(ValueError,'conservation'):runner.summarize_report(report,1000)


if __name__=='__main__':unittest.main()
