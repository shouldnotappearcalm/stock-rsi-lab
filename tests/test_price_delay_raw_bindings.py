import hashlib
from pathlib import Path
import tempfile
import unittest

import scripts.run_price_delay_raw_pre2026 as replay


class RawSourceBindingTests(unittest.TestCase):
    def authenticate(self, plan, base, repo):
        if not hasattr(replay, 'authenticate_plan_sources'):
            self.fail('raw account source bindings do not yet require the complete frozen file set')
        return replay.authenticate_plan_sources(plan, base, repo)

    def test_empty_or_partial_source_maps_fail_before_source_reads(self):
        for plan in ({'local_source_sha256': {}, 'public_evidence_sha256': {}},
                     {'local_source_sha256': {'price-delay-raw-dev-20261021/manifest.json': 'a'*64},
                      'public_evidence_sha256': {}}):
            with self.assertRaises(ValueError): self.authenticate(plan, Path('/nonexistent'), Path('/nonexistent'))

    def test_complete_bindings_authenticate_and_changed_audit_or_missing_mandatory_file_fails(self):
        if not hasattr(replay, 'LOCAL_FILES') or not hasattr(replay, 'PUBLIC_FILES'):
            self.fail('mandatory dataset and audit anchors have not been declared')
        audit = 'price-delay-event-source-independent-audit-20261021.json'
        self.assertIn(audit, replay.LOCAL_FILES)
        self.assertIn('price-delay-raw-dev-20261021/manifest.json', replay.LOCAL_FILES)
        with tempfile.TemporaryDirectory() as t:
            base, repo = Path(t)/'data', Path(t)/'repo'; plan = {}
            for field, root, names in (('local_source_sha256', base, replay.LOCAL_FILES),
                                       ('public_evidence_sha256', repo, replay.PUBLIC_FILES)):
                plan[field] = {}
                for name in names:
                    p = root/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'frozen pre2026 evidence')
                    plan[field][name] = hashlib.sha256(p.read_bytes()).hexdigest()
            self.authenticate(plan, base, repo)
            value = plan['local_source_sha256'].pop(audit)
            with self.assertRaises(ValueError): self.authenticate(plan, base, repo)
            plan['local_source_sha256'][audit] = value
            (base/audit).write_bytes(b'changed evidence')
            with self.assertRaises(ValueError): self.authenticate(plan, base, repo)

    def test_negative_control_strings_cannot_pass_as_booleans(self):
        if not hasattr(replay, 'valid_negative_controls'):
            self.fail('negative-control gate has no strict bool validation')
        valid = {str(i): True for i in range(4)}
        self.assertTrue(replay.valid_negative_controls(valid))
        for controls in ({}, {'a': True}, valid | {'3': 'false'}, valid | {'3': 1}, valid | {'3': False}):
            self.assertFalse(replay.valid_negative_controls(controls))
