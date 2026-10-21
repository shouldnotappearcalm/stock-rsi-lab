import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class ValueMomentumRawCaptureTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.capture_value_momentum_raw_pre2026')
        except ModuleNotFoundError:self.fail('bounded103-name pre2026source entry absent')
    def scope(self,api):
        return {'status':'FROZEN_VALUE_MOMENTUM_RAW_SOURCE_REQUEST','candidate':'szse_value_momentum_equal','window':['2023-12-29','2025-12-31'],
            'codes':sorted([f'SZ000{i:03d}' for i in range(100,196)]+list(api.FRESH_CODES)),'reuse_routes':dict.fromkeys((f'SZ000{i:03d}' for i in range(100,196)),{}),
            'fresh_codes':list(api.FRESH_CODES),'reuse_sources':[{'directory':n} for n in api.SOURCE_NAMES],'maximum_new_query_reservations':28,'max_attempts_per_query':1,
            'maximum_consecutive_failed_fresh_codes':3,'maximum_cross_restart_administrative_login_attempts':3,'socket_timeout_seconds':20}
    def test_exact_source_scope_accepts_and_future_or_wider_scope_rejects(self):
        api=self.api();r=self.scope(api);api.check_scope(r)
        for key,value in (('window',['2023-12-29','2026-10-20']),('candidate','momentum_leg_control'),('maximum_new_query_reservations',29),
                          ('max_attempts_per_query',2),('socket_timeout_seconds',21),('maximum_cross_restart_administrative_login_attempts',4),
                          ('fresh_codes',list(api.FRESH_CODES)[:-1])):
            v=copy.deepcopy(r);v[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):api.check_scope(v)
    def test_bad_external_checksum_creates_no_output_or_source_connection(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d,patch.object(api.socket,'setdefaulttimeout') as timeout:
            request=Path(d)/'request.json';request.write_text('{}');out=Path(d)/'out'
            with self.assertRaises(ValueError):api.main(['--request',str(request),'--expected-request-sha256','0'*64,'--targets',str(Path(d)/'targets.json'),'--source-root',d,'--output-dir',str(out),'--preflight-only'])
            self.assertFalse(out.exists());timeout.assert_not_called()
    def test_partial_calendar_stays_unclassified_and_original_packet_unchanged(self):
        api=self.api();from scripts.capture_low_risk_raw_account_data import BAR_FIELDS
        row=['2024-04-02','sz.001389','10','11','9','10','10','10000','100000','3','1','0']
        packet={'instrument':'SZ001389','window':['2023-12-29','2025-12-31'],'bars':[dict(zip(BAR_FIELDS,row))],'distributions':[],'adjustments':[],'quarantine':[]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'packet.json';p.write_text(json.dumps(packet));before=p.read_bytes()
            _,diag=api.load_reuse_packet(p,'SZ001389',api.sha256_file(p),['2023-12-29','2024-04-02','2025-12-31'])
            with self.assertRaisesRegex(ValueError,'full explicit'):
                api.authenticate_reuse(p,'SZ001389',api.sha256_file(p),['2023-12-29','2024-04-02','2025-12-31'])
            complete,_=api.authenticate_reuse(p,'SZ001389',api.sha256_file(p),['2024-04-02'])
            self.assertEqual(complete,packet)
            self.assertFalse(diag['full_explicit_calendar_covered']);self.assertFalse(diag['missing_sessions_classified_as_prelisting']);self.assertEqual(p.read_bytes(),before)

if __name__=='__main__':unittest.main()
