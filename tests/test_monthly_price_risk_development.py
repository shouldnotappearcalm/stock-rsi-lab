import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_monthly_price_risk_development as replay


class MonthlyRiskAccountFreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method = self.root / 'method.py'
        self.raw = self.root / 'failed-state.json'
        self.method.write_text('frozen method')
        self.raw.write_text('frozen prior failed state')
        self.paths = {'repo/method.py': self.method, 'source/failed-state.json': self.raw}
        old = replay.original
        self.plan = {'status': replay.STATUS, 'strategy': replay.risk.POLICY_ID,
            'base_strategy': 'amihud22', 'decision_record_seed_policy_id': 'amihud22',
            'risk_contract': replay.risk.CONTRACT, 'phase': 'dev', 'candidate_budget': 1,
            'end': '2025-12-31', 'participation_bps': list(old.PARTICIPATION),
            'extra_bps': list(old.EXTRA_BPS), 'capitals': list(old.CAPITALS), 'profiles': list(old.PROFILES),
            'source_contract': old.source.CONTRACT, 'source_scenario_dir': old.SOURCE_DIR,
            'source_request_sha256': old.SOURCE_REQUEST_SHA, 'original_source_admission_overridden': False,
            'conditional_engineering_only': True, 'registry_allocation_assumed': False,
            '2026_evaluation_permitted': False, 'method_code_sha256': {'method.py': replay.file_sha(self.method)},
            'input_sha256': {n: replay.file_sha(p) for n, p in self.paths.items()}}
        self.plan_file = self.root / 'plan.json'

    def verify(self, changed=None, expected=None):
        replay.write(self.plan_file, self.plan if changed is None else changed)
        expected = replay.file_sha(self.plan_file) if expected is None else expected
        with patch.object(replay, 'METHOD_FILES', ('method.py',)), patch.object(
                replay, 'required_input_paths', return_value=self.paths):
            return replay.verify_plan(self.root, self.root, self.plan_file, expected)

    def test_same_original60profiles_and_new_composite_identity_are_bound(self):
        plan, paths = self.verify()
        self.assertEqual(len(plan['profiles']), 60)
        self.assertEqual(paths, self.paths)
        self.assertNotEqual(plan['strategy'], plan['decision_record_seed_policy_id'])

    def test_omitted_profiles_changed_alpha_allocation_assumption_or_future_fail(self):
        for key, value in [('profiles', self.plan['profiles'][:-1]), ('candidate_budget', 2),
                           ('base_strategy', 'different-alpha'), ('decision_record_seed_policy_id', 'different-alpha'),
                           ('end', '2026-10-20'), ('2026_evaluation_permitted', True),
                           ('registry_allocation_assumed', True), ('original_source_admission_overridden', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify({**self.plan, key: value})

    def test_omitted_prior_failure_changed_method_and_rewritten_plan_fail(self):
        changed = copy.deepcopy(self.plan)
        del changed['input_sha256']['source/failed-state.json']
        with self.assertRaises(ValueError):
            self.verify(changed)
        with self.assertRaises(ValueError):
            self.verify(expected='0' * 64)
        self.method.write_text('changed account code')
        with self.assertRaisesRegex(ValueError, 'account method changed'):
            self.verify()

    def test_unchanged_run_profiles_receives_overlay_context_and_error_is_preserved(self):
        self.verify()
        expected = replay.file_sha(self.plan_file)
        context = {'events': [], 'receipts': [], 'targets': {'SYNTHETIC': {'risk_overlay': 'bound'}}}
        interrupted = KeyboardInterrupt('original physical account interruption')
        def run_profiles(given, out, results):
            self.assertIs(given, context)
            results['100/0/100000'] = {'status': 'INVALID_SOURCE_OR_ACCOUNT'}
            self.raw.write_text('changed failed state')
            replay.write(self.plan_file, {})
            raise interrupted
        out = self.root / 'output'
        with patch.object(replay, 'verify_plan', return_value=(self.plan, self.paths)), patch.object(
                replay, 'load_inputs', return_value=context), patch.object(
                replay.original, 'run_profiles', side_effect=run_profiles) as called:
            with self.assertRaises(KeyboardInterrupt) as caught:
                replay.run(self.root, self.root, self.plan_file, expected, out)
        self.assertEqual(called.call_count, 1)
        self.assertIs(caught.exception, interrupted)
        terminal = replay.read(out / 'terminal.json')
        self.assertEqual(terminal['completed_profiles'], 1)
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
                         {'source/failed-state.json', 'frozen_account_plan'})
        self.assertFalse((out / 'summary.json').exists())

    def test_existing_failed_run_cannot_be_overwritten(self):
        out = self.root / 'prior-failure'
        out.mkdir()
        marker = out / 'terminal.json'
        marker.write_text('prior failed terminal')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            replay.run(self.root, self.root, self.plan_file, 'unused', out)
        self.assertEqual(marker.read_text(), 'prior failed terminal')

    def test_source_summary_reference_must_match_original_plan_and_actual_bytes(self):
        directory = self.root / replay.original.SOURCE_DIR
        directory.mkdir()
        summary = directory / 'summary.json'
        summary.write_text('synthetic source summary')
        old = {'source_summary_sha256': replay.file_sha(summary)}
        replay.authenticate_source_summary(self.root, old, old)
        with self.assertRaisesRegex(ValueError, 'source summary metadata changed'):
            replay.authenticate_source_summary(self.root, {'source_summary_sha256': 'wrong'}, old)
        summary.write_text('mutated source summary')
        with self.assertRaisesRegex(ValueError, 'source summary metadata changed'):
            replay.authenticate_source_summary(self.root, old, old)

    def test_audit_requires_every_frozen_input_before_loading_original_account_sources(self):
        directory = self.root / replay.TARGET_DIR
        directory.mkdir()
        for name in replay.TARGET_FILES:
            replay.write(directory / name, {})
        code_path = self.root / replay.TARGET_AUDIT_CODE
        code_path.parent.mkdir(parents=True)
        code_path.write_text('synthetic independent auditor')
        audit_path = self.root / replay.TARGET_AUDIT
        audit = {'status': 'PASS_INDEPENDENT_MONTHLY_PRICE_RISK_TARGET_AUDIT', 'request_sha256': 'fixed',
                 'audit_code_sha256': replay.file_sha(code_path), 'all_input_sha256': {},
                 'all_output_sha256': {n: replay.file_sha(directory / n) for n in replay.TARGET_FILES},
                 'critical_or_important_findings': []}
        replay.write(audit_path, audit)
        with patch.object(replay.risk, 'verify_request', return_value=({'input_sha256': {'source/data': 'sha'}}, {})), patch.object(
                replay.original, 'load_inputs') as load:
            with self.assertRaisesRegex(ValueError, 'independent risk target audit required'):
                replay.load_inputs(self.root, self.root, {'risk_target_request_sha256': 'fixed'})
            load.assert_not_called()
        audit['all_input_sha256'] = {'source/data': 'sha', 'frozen_risk_target_request': 'fixed'}
        replay.write(audit_path, audit)
        (directory / 'targets.json').write_text('mutated target')
        with patch.object(replay.risk, 'verify_request', return_value=({'input_sha256': {'source/data': 'sha'}}, {})), patch.object(
                replay.original, 'load_inputs') as load:
            with self.assertRaisesRegex(ValueError, 'target bytes changed'):
                replay.load_inputs(self.root, self.root, {'risk_target_request_sha256': 'fixed'})
            load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
