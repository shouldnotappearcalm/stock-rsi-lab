from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import run_qlib_asset_expansion_pre2026 as runner
except ImportError:
    runner=None


class AssetExpansionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(runner,'asset-expansion development runner missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.source=self.base/'source';self.source.write_text('frozen source');self.request=self.base/'request.json'
        self.req={'input_sha256':{'source/source':runner.sha(self.source)},'provider_relative':runner.PROVIDER,
            'formations':[{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'}]}
        runner.write_once(self.request,self.req);self.reqsha=runner.sha(self.request)

    def formation(self,*args):
        targets={n:{'2024-01-02':{'as_of':'2023-12-29','weights':{'SZ000001':.95}}} for n in runner.NAMES}
        return targets,[{'formation_asof':'2023-12-29','latest_factor_price_read':'2023-12-29'}]

    def simulation(self,*args,**kwargs):
        runner.write_once(kwargs['out']/'account-artifact.json',{'name':kwargs['name'],'extra_bps':kwargs['extra_bps']})
        return {'status':'DAILY_PROXY_DEVELOPMENT_RECONCILED','2024_return_pct':1.,'2025_return_pct':2.,
            'average_exposure_pct':94.,'turnover_x_initial':3.,'unverified_held_marks':0}

    def run_trial(self,simulation=None):
        with patch.object(runner,'verify',return_value=(self.req,{'source/source':self.source})):
            return runner.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,
                form_targets=self.formation,simulation=simulation or self.simulation)

    def test_six_profiles_keep_primary_only_and_preserve_engineering_limits(self):
        result=self.run_trial();self.assertEqual(len(result['results_by_extra_bps_and_family']),6)
        self.assertEqual(result['selected_development_lead'],runner.PRIMARY)
        self.assertEqual(len(list((self.base/runner.OUTPUT).rglob('account-artifact.json'))),6)
        self.assertFalse(result['raw_share_execution_verified']);self.assertFalse(result['objective_achieved'])
        with self.assertRaisesRegex(ValueError,'no resume'):self.run_trial()

    def test_profitable_control_cannot_replace_failed_primary(self):
        def fail(*args,**kwargs):
            row=self.simulation(*args,**kwargs)
            if kwargs['name']==runner.PRIMARY:row['2024_return_pct']=-1.
            return row
        self.assertIsNone(self.run_trial(fail)['selected_development_lead'])

    def test_unverified_held_mark_blocks_otherwise_profitable_primary(self):
        def unverified(*args,**kwargs):
            row=self.simulation(*args,**kwargs)
            if kwargs['name']==runner.PRIMARY:row['unverified_held_marks']=1
            return row
        self.assertIsNone(self.run_trial(unverified)['selected_development_lead'])

    def test_incomplete_metrics_keep_original_failure_before_profile_completion(self):
        def incomplete(*args,**kwargs):
            row=self.simulation(*args,**kwargs);del row['average_exposure_pct'];return row
        with self.assertRaisesRegex(ValueError,'complete finite'):self.run_trial(incomplete)
        terminal=runner.read(self.base/runner.OUTPUT/'terminal.json')
        self.assertEqual(terminal['completed_profiles'],[]);self.assertEqual(len(terminal['pending_profiles']),6)
        self.assertEqual(terminal['original_error']['type'],'ValueError')

    def test_interrupt_preserves_completed_prefix_and_deleted_source_request_posthash(self):
        original=KeyboardInterrupt('asset-expansion simulation interrupted')
        def interrupted(*args,**kwargs):
            if kwargs['name']!='low_asset_expansion_decile_conditional':
                self.source.unlink();self.request.write_text('{}');raise original
            return self.simulation(*args,**kwargs)
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_trial(interrupted)
        self.assertIs(caught.exception,original);terminal=runner.read(self.base/runner.OUTPUT/'terminal.json')
        self.assertEqual(len(terminal['completed_profiles']),1);self.assertEqual(len(terminal['pending_profiles']),5)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},{'source/source','frozen_request'})
        self.assertFalse((self.base/runner.OUTPUT/'summary.json').exists())

    def test_changed_source_blocks_success_after_all_profiles_and_bad_request_hash_fails_early(self):
        def changed(*args,**kwargs):
            row=self.simulation(*args,**kwargs);self.source.write_text('changed');return row
        with self.assertRaisesRegex(ValueError,'unchanged'):self.run_trial(changed)
        self.assertFalse((self.base/runner.OUTPUT/'summary.json').exists())
        with self.assertRaisesRegex(ValueError,'request'):runner.verify(self.base,self.base,self.base/'membership',self.request,'bad')


if __name__=='__main__':unittest.main()
