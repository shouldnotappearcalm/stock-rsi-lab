import copy
import unittest
import json
import tempfile
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    from scripts.capture_frozen_target_development_data import clipped_packet, target_codes
except ImportError:
    clipped_packet=target_codes=None


class FrozenTargetCaptureTests(unittest.TestCase):
    def test_reuse_removes_later_source_rows_without_mutating_original(self):
        self.assertIsNotNone(clipped_packet,'frozen-target capture missing')
        source={'instrument':'SH600001','bars':[{'date':'2025-12-31'},{'date':'2026-01-05'}],
            'distributions':[{'dividOperateDate':'2025-06-01'},{'dividOperateDate':'2026-06-01'}],
            'adjustments':[{'dividOperateDate':'2025-06-01'},{'dividOperateDate':'2026-06-01'}],
            'quarantine':[{'reason':'MISSING_OPERATE_DATE','record':{'dividOperateDate':''}}]}
        original=copy.deepcopy(source);clipped=clipped_packet(source)
        self.assertEqual(clipped['bars'],[{'date':'2025-12-31'}])
        self.assertEqual(len(clipped['distributions']),1);self.assertEqual(len(clipped['adjustments']),1)
        self.assertEqual(len(clipped['quarantine']),1)
        self.assertEqual(source,original)

    def test_capture_universe_is_bound_to_development_targets(self):
        self.assertIsNotNone(target_codes,'frozen-target capture missing')
        targets={'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}}
        self.assertEqual(target_codes(targets),['SH600001'])
        with self.assertRaises(ValueError):target_codes({'2026-01-05':targets['2024-01-02']})
        with self.assertRaises(ValueError):target_codes({'2024-01-02':{'as_of':'2024-01-02','weights':{'SH600001':.95}}})
        with self.assertRaises(ValueError):target_codes({'2024-01-02':{'as_of':'2023-12-29','weights':{'SH688001':.95}}})

    def test_resume_rejects_changed_calendar_before_any_provider_access(self):
        from scripts import capture_frozen_target_development_data as capture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reuse=root/'reuse';out=root/'out';reuse.mkdir();out.mkdir()
            (reuse/'calendar.json').write_text(json.dumps({'sessions':['2023-12-29','2024-01-02','2025-12-31']}))
            (reuse/'manifest.json').write_text(json.dumps({'calendar_sha256':capture.sha256_file(reuse/'calendar.json'),'per_code_sha256':{}}))
            (root/'targets.json').write_text(json.dumps({'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}}))
            request={'window':['2023-12-29','2025-12-31'],'capture_code_sha256':capture.sha256_file(capture.__file__),
                     'shared_validation_sha256':capture.sha256_file(Path(capture.__file__).with_name('capture_low_risk_raw_account_data.py')),
                     'target_sha256':capture.sha256_file(root/'targets.json'),'reuse_manifest_sha256':capture.sha256_file(reuse/'manifest.json'),
                     'codes':['SH600001']}
            (root/'request.json').write_text(json.dumps(request));(out/'request.json').write_bytes((root/'request.json').read_bytes())
            (out/'progress.json').write_text('{}');(out/'calendar.json').write_text('{"sessions":[]}')
            def denied_login():raise RuntimeError('unexpected provider access')
            with patch.dict(sys.modules,{'baostock':SimpleNamespace(login=denied_login)}):
                with self.assertRaisesRegex(ValueError,'checkpoint calendar'):
                    capture.main(['--request',str(root/'request.json'),'--expected-request-sha256',capture.sha256_file(root/'request.json'),
                                  '--targets',str(root/'targets.json'),'--reuse-dir',str(reuse),'--output-dir',str(out),'--resume'])
