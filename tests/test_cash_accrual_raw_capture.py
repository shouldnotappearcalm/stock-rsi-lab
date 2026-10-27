from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from scripts import capture_cash_accrual_raw_pre2026 as r

class CashAccrualRawCaptureTests(TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name);self.known={};self.codes=[f'SH{600001+i}' for i in range(30)]+['SH600129'];routes={}
        self.packet=lambda c:{'instrument':c,'window':['2023-12-29','2025-12-31'],'bars':[{'date':'2023-12-29','close':'10'}],'distributions':[],'adjustments':[],'quarantine':[]}
        for c in self.codes[:-1]:
            p=self.base/'reuse/codes'/(c+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(self.packet(c)));h=r.shared.sha(p);self.known[str(p.resolve())]=h
            routes[c]={'directory':'reuse','packet_sha256':h,'fingerprint':r.source_fingerprint(self.packet(c)),'complete_calendar':True}
        self.req={**deepcopy(r.PROFILE),'inventory':{'codes':self.codes,'fresh_codes':['SH600129'],'source_conflicts':{},'reuse_routes':routes,'sessions':['2023-12-29'],'target_sha256':'a'*64}}
        self.calls=[];owner=self
        class SDK:
            def login(self):owner.calls.append('login');return type('Reply',(),{'error_code':'0','error_msg':'ok'})()
            def logout(self):owner.calls.append('logout');return type('Reply',(),{'error_code':'0','error_msg':'ok'})()
        self.sdk=SDK()
    def load(self,p,c,h,sessions):
        if r.shared.sha(p)!=h:raise ValueError('packet bytes changed')
        return json.loads(Path(p).read_text()),{'full_explicit_calendar_covered':True}
    def capture(self,fetcher=None):
        with patch.object(r,'load_reuse_packet',side_effect=self.load),patch.object(r,'calendar_diagnostic',return_value={'full_explicit_calendar_covered':True}):
            return r.capture(self.req,self.known,self.base,'a'*64,sdk=self.sdk,fetcher=fetcher or (lambda j,c,h,f:self.packet(c)))
    def test_synthetic_orchestration_copies30_and_captures_one_with_cleanup(self):
        t=self.capture();self.assertTrue(t['complete']);self.assertFalse(t['source_admitted_for_replay']);self.assertEqual(self.calls,['login','logout'])
        m=r.shared.read(self.base/r.OUTPUT/'manifest.json');self.assertEqual(len(m['per_code_sha256']),31)
    def test_native_capture_error_keeps30_source_prefix_and_logout(self):
        def failed(*args):raise ValueError('native provider failure')
        with self.assertRaisesRegex(ValueError,'native provider failure'):self.capture(failed)
        t=r.shared.read(self.base/r.OUTPUT/'terminal.json');self.assertFalse(t['complete']);self.assertEqual(len(t['completed_codes']),30);self.assertEqual(self.calls,['login','logout'])
    def test_changed_original_is_rejected_before_network(self):
        Path(next(iter(self.known))).write_text('{}')
        with self.assertRaises(ValueError):self.capture()
        self.assertEqual(self.calls,[])
    def test_mutated_copy_during_cleanup_is_not_complete_source(self):
        def logout():
            (self.base/r.OUTPUT/'codes'/(self.codes[0]+'.json')).write_text('{}');return type('Reply',(),{'error_code':'0','error_msg':'ok'})()
        self.sdk.logout=logout
        with self.assertRaises(ValueError):self.capture()
        self.assertFalse(r.shared.read(self.base/r.OUTPUT/'terminal.json')['complete'])
    def test_budget_future_window_or_extra_instrument_cannot_change(self):
        for k,v in [('window',['2023-12-29','2026-10-27']),('maximum_new_query_reservations',5),('fresh_codes',['SH600129','SH600130']),('max_attempts_per_identity',2)]:
            with self.subTest(k=k),self.assertRaises(ValueError):r.validate({**self.req,k:v})
