import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import run_asset_expansion_targets_2026 as run
except ImportError:
    run=None


class HorizonTargetRunnerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run,'frozen horizon target runner missing')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.input=self.base/'source';self.input.write_text('source');self.request=self.base/'request.json'
        self.req={'input_sha256':{'source/source':run.sha(self.input)},'cohort':['SH600001'],
            'formations':[{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'},
                {'execution_session':'2026-01-05','as_of':'2025-12-31T15:05:00+08:00'}]}
        self.targets={n:{} for n in run.signal.NAMES};self.receipts=[]
        for q in self.req['formations']:
            d,prior=q['execution_session'],q['as_of'][:10]
            for n in run.signal.NAMES:self.targets[n][d]={'as_of':prior,'weights':{'SH600001':.95}}
            self.receipts.append({'execution_session':d,'formation_asof':prior,'source_as_of':q['as_of'],
                'latest_factor_price_read':prior,'eligible':100})
        (self.base/run.OLD_TARGETS).parent.mkdir(parents=True)
        run.write_once(self.base/run.OLD_TARGETS,{n:{'2024-01-02':self.targets[n]['2024-01-02']} for n in run.signal.NAMES})
        run.write_once(self.base/run.OLD_RECEIPTS,self.receipts[:1]);run.write_once(self.request,self.req);self.reqsha=run.sha(self.request)

    def former(self,base,req,on_formation):
        for receipt in self.receipts:
            d=receipt['execution_session'];on_formation(d,{n:self.targets[n][d] for n in run.signal.NAMES},receipt)
        return self.targets,self.receipts

    def execute(self,former=None):
        with patch.object(run,'verify',return_value=(self.req,{'source/source':self.input})),\
             patch.object(run,'prefix_evidence',return_value={'all_pre2026_byte_prefixes_equal':True}):
            return run.run(self.base,self.base,self.base/'membership',self.request,self.reqsha,former=former or self.former)

    def test_complete_targets_and_legacy_parity_are_saved_without_returns_or_overwrite(self):
        result=self.execute();self.assertEqual(result['completed_formations'],2);self.assertEqual(result['pre2026_target_parity_formations'],1)
        self.assertFalse(result['portfolio_returns_computed']);self.assertFalse(result['objective_achieved'])
        self.assertEqual(run.read(self.base/run.OUTPUT/'targets.json'),self.targets)
        with self.assertRaisesRegex(ValueError,'no resume'):self.execute()

    def test_ast_authentication_rejects_weight_threshold_and_window_guard_rule_changes(self):
        old=Path(run.signal.__file__).with_name('asset_expansion_monthly.py').read_text();new=Path(run.signal.__file__).read_text()
        run.assert_same_policy_ast(old,new)
        for changed in (new.replace('.95/len(selected)','.99/len(selected)'),new.replace('len(scores)>=100','len(scores)>=99'),
            new.replace('START<=start<=end<=END','True')):
            with self.assertRaises(ValueError):run.assert_same_policy_ast(old,changed)

    def test_old_target_mismatch_stops_before_any_2026_formation(self):
        self.targets[run.signal.PRIMARY]['2024-01-02']['weights']['SH600001']=.94
        with self.assertRaisesRegex(ValueError,'legacy target'):self.execute()
        t=run.read(self.base/run.OUTPUT/'terminal.json')
        self.assertEqual(t['completed_formations'],[]);self.assertEqual(len(t['pending_formations']),2)
        self.assertFalse((self.base/run.OUTPUT/'summary.json').exists())

    def test_interrupt_retains_original_exception_completed_prefix_and_changed_source_request(self):
        error=KeyboardInterrupt('horizon stopped')
        def interrupted(base,req,on_formation):
            on_formation('2024-01-02',{n:self.targets[n]['2024-01-02'] for n in run.signal.NAMES},self.receipts[0])
            self.input.unlink();self.request.write_text('{}');raise error
        with self.assertRaises(KeyboardInterrupt) as caught:self.execute(interrupted)
        self.assertIs(caught.exception,error);t=run.read(self.base/run.OUTPUT/'terminal.json')
        self.assertEqual(t['completed_formations'],['2024-01-02']);self.assertEqual(t['pending_formations'],['2026-01-05'])
        self.assertEqual({x['input'] for x in t['postcheck']['mismatches']},{'source/source','frozen_request'})

    def test_changed_source_blocks_summary_after_all_formations(self):
        def changed(base,req,on_formation):
            result=self.former(base,req,on_formation);self.input.write_text('changed');return result
        with self.assertRaisesRegex(ValueError,'unchanged horizon'):self.execute(changed)
        self.assertFalse((self.base/run.OUTPUT/'summary.json').exists())

    def test_aggregate_mutation_after_callback_cannot_replace_persisted_targets(self):
        def changed(base,req,on_formation):
            result=self.former(base,req,on_formation)
            self.targets[run.signal.PRIMARY]['2026-01-05']['weights']['SH600001']=.94
            return result
        with self.assertRaisesRegex(ValueError,'persisted formation aggregates'):self.execute(changed)
        self.assertFalse((self.base/run.OUTPUT/'targets.json').exists())

    def test_opaque_historical_prefix_matches_without_decoding_future_tail_and_refuses_drift(self):
        req={'cohort':['SH600001'],'input_sha256':{}}
        for provider,calendar in ((run.OLD_PROVIDER,'2025-12-30\n2025-12-31\n'),
            (run.PROVIDER,'2025-12-30\n2025-12-31\n2026-01-05\n')):
            root=self.base/provider;(root/'calendars').mkdir(parents=True);(root/'calendars/day.txt').write_text(calendar)
            (root/'features/sh600001').mkdir(parents=True)
            for field in ('close','volume','factor'):
                f=root/'features/sh600001'/(field+'.day.bin');f.write_bytes(struct.pack('<3f',0.,1.,2.)+(b'FUTR' if provider==run.PROVIDER else b''))
                if provider==run.OLD_PROVIDER:req['input_sha256']['source/'+provider+'/features/sh600001/'+field+'.day.bin']=run.sha(f)
        proof=run.prefix_evidence(self.base,req)
        self.assertEqual(proof['feature_prefix_count'],3);self.assertTrue(proof['no2026_float_values_decoded_in_prefix_check'])
        f=self.base/run.PROVIDER/'features/sh600001/close.day.bin';f.write_bytes(struct.pack('<3f',0.,1.,9.)+b'FUTR')
        with self.assertRaisesRegex(ValueError,'opaque feature prefix'):run.prefix_evidence(self.base,req)


if __name__=='__main__':unittest.main()
