import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import build_monthly_price_risk_targets as builder


class MonthlyRiskTargetFreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method = self.root / 'method.py'
        self.source = self.root / 'source.json'
        self.method.write_text('fixed method')
        self.source.write_text('fixed source')
        self.paths = {'repo/method.py': self.method, 'source/source.json': self.source}
        self.request = {'status': builder.STATUS, 'contract': builder.CONTRACT, 'policy_id': builder.POLICY_ID,
            'candidate_budget': 1, 'minimum_formation_raw_close_CNY': '1.00', 'surviving_target_budget': '.95',
            'end': '2025-12-31', 'portfolio_returns_permitted': False, '2026_evaluation_permitted': False,
            'method_code_sha256': {'method.py': builder.file_sha(self.method)},
            'input_sha256': {name: builder.file_sha(p) for name, p in self.paths.items()}}
        self.request_file = self.root / 'request.json'

    def verify(self, request=None, expected=None):
        self.request_file.write_text(json.dumps(self.request if request is None else request))
        expected = builder.file_sha(self.request_file) if expected is None else expected
        with patch.object(builder, 'METHOD_FILES', ('method.py',)), patch.object(
                builder, 'required_input_paths', return_value=self.paths):
            return builder.verify_request(self.root, self.root, self.request_file, expected)

    def test_complete_fixed_request_is_accepted(self):
        _, paths = self.verify()
        self.assertEqual(paths, self.paths)

    def primary_fixture(self):
        directory = self.root / builder.PRIMARY_DIR
        directory.mkdir()
        names = ['capture-manifest.json', 'szse-listing-rules-2023-08.pdf',
                 'sse-delist-rule-2020-12-31.html', 'sse-delist-rule-2020-12-31.html.txt',
                 'sse-delist-2024-01-09.html', 'sse-delist-2024-01-09.html.txt',
                 'szse-page-113.png', 'szse-page-116.png']
        pages = {f'page-{page}.{ext}': '' for page in (1, 113, 114, 115, 116, 188, 189)
                 for ext in ('png', 'txt')}
        names += ['review-' + name for name in pages]
        for name in names:
            (directory / name).write_text('SYNTHETIC ' + name)
        digests = {name: builder.file_sha(directory / name) for name in names}
        review = {'capture_manifest_sha256': digests['capture-manifest.json'],
                  'sources': [{'local_path': names[i], 'sha256': digests[names[i]]} for i in (1, 2, 4)],
                  'reading_page_artifact_sha256': {name: digests['review-' + name] for name in pages}}
        review_path = self.root / 'experiments/qlib/amihud-monthly-price-risk-primary-review.json'
        review_path.parent.mkdir(parents=True)
        builder.write(review_path, review)
        manifest = {'portfolio_returns_computed': False, 'historical_arrival_verified': False,
                    'file_sha256': digests}
        builder.write(directory / 'manifest.json', manifest)
        discovery = {'source_manifest_sha256': builder.file_sha(directory / 'manifest.json'),
                     'independent_review_sha256': builder.file_sha(review_path),
                     'formal_primary_file_sha256': digests}
        discovery_path = review_path.with_name('amihud-monthly-price-risk-primary-discovery.json')
        builder.write(discovery_path, discovery)
        return directory, manifest, discovery_path, discovery

    def test_primary_requires_canonical22_even_with_self_consistent_empty_manifest(self):
        directory, manifest, discovery_path, discovery = self.primary_fixture()
        self.assertEqual(len(builder.authenticated_primary_paths(self.root, self.root)), 23)
        manifest['file_sha256'] = {}
        discovery['formal_primary_file_sha256'] = {}
        builder.write(directory / 'manifest.json', manifest)
        discovery['source_manifest_sha256'] = builder.file_sha(directory / 'manifest.json')
        builder.write(discovery_path, discovery)
        with self.assertRaisesRegex(ValueError, 'canonical22'):
            builder.authenticated_primary_paths(self.root, self.root)

    def test_primary_manifest_anchor_and_actual_page_bytes_are_checked(self):
        directory, manifest, _, _ = self.primary_fixture()
        (directory / 'review-page-113.png').write_text('changed page')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            builder.authenticated_primary_paths(self.root, self.root)
        manifest['file_sha256'] = {}
        builder.write(directory / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            builder.authenticated_primary_paths(self.root, self.root)

    def failed_fixture(self):
        directory = self.root / builder.FAILED_DIR
        names = [f'{p}/{c}/{capital}/{name}' for p in (100, 500, 1000)
                 for c in (0, 5, 10, 20, 40) for capital in ('100000', '1000000', '10000000', '100000000')
                 for name in ('error.json', 'failed_account_state.json', 'failure_trace.json',
                              'partial_case.json', 'tape_accessed_pairs.json')]
        names += ['summary.json', 'input-before.json', 'event_source_receipts.json',
                  'input-postcheck.json', 'derived_events.json', 'terminal.json', 'case_results.json']
        for name in names:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC ' + name)
        expected = {name: builder.file_sha(directory / name) for name in names}
        prefix = self.root / 'experiments/qlib/illiquidity-source-scenario-development'
        prefix.parent.mkdir(parents=True)
        Path(str(prefix) + '-results.json').write_bytes((directory / 'summary.json').read_bytes())
        audit_path = Path(str(prefix) + '-independent-ledger-audit.json')
        audit = {'all_output_sha256': expected, 'plan_sha256': builder.BASE_PLAN_SHA,
                 'completed_profiles': 0, 'failed_profiles': 60,
                 'raw_confirmation_passes_independently': False, 'summary_sha256': expected['summary.json']}
        builder.write(audit_path, audit)
        verification_path = Path(str(prefix) + '-run-verification.json')
        verification = {'all307_local_output_file_sha256': expected, 'plan_sha256': builder.BASE_PLAN_SHA,
                        'independent_audit_sha256': builder.file_sha(audit_path),
                        'summary_sha256': expected['summary.json']}
        builder.write(verification_path, verification)
        return directory, verification_path, verification, audit_path, audit

    def test_old307_failure_files_are_bound_and_mutation_is_rejected(self):
        directory, _, _, _, _ = self.failed_fixture()
        self.assertEqual(len(builder.authenticated_failed_paths(self.root, self.root)), 307)
        (directory / '100/40/1000000/failed_account_state.json').write_text('changed cash')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            builder.authenticated_failed_paths(self.root, self.root)

    def test_old_failure_subset_rejected_even_with_matching_public_reports(self):
        _, verification_path, verification, audit_path, audit = self.failed_fixture()
        del audit['all_output_sha256']['100/40/1000000/failed_account_state.json']
        builder.write(audit_path, audit)
        verification['independent_audit_sha256'] = builder.file_sha(audit_path)
        builder.write(verification_path, verification)
        with self.assertRaisesRegex(ValueError, 'canonical307'):
            builder.authenticated_failed_paths(self.root, self.root)

    def test_threshold_budget_candidate_search_and_future_permissions_are_frozen(self):
        for key, value in [('minimum_formation_raw_close_CNY', '1.1'), ('surviving_target_budget', '1'),
                           ('candidate_budget', 2), ('end', '2026-10-20'),
                           ('portfolio_returns_permitted', True), ('2026_evaluation_permitted', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify({**self.request, key: value})

    def test_source_omission_byte_mutation_and_request_rewrite_are_rejected(self):
        changed = copy.deepcopy(self.request)
        del changed['input_sha256']['source/source.json']
        with self.assertRaises(ValueError):
            self.verify(changed)
        with self.assertRaises(ValueError):
            self.verify(expected='0' * 64)
        self.source.write_text('changed source')
        with self.assertRaisesRegex(ValueError, 'frozen source bytes'):
            self.verify()

    def test_preexisting_failure_output_is_not_overwritten(self):
        out = self.root / 'output'
        out.mkdir()
        marker = out / 'terminal.json'
        marker.write_text('original failed run')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            builder.build(self.root, self.root, self.request_file, 'unused', out)
        self.assertEqual(marker.read_text(), 'original failed run')

    def test_interruption_keeps_original_and_rechecks_every_source_and_request(self):
        # Wrapper-only fixture: real calendar/target logic is not invoked here.
        self.request_file.write_text(json.dumps(self.request))
        expected = builder.file_sha(self.request_file)
        context = {'targets': {str(i): {} for i in range(24)},
                   'calendar': SimpleNamespace(days=['WRAPPER_ONLY'] * 486)}
        interrupted = KeyboardInterrupt('original generation interruption')
        def interrupt(*args):
            self.source.unlink()
            self.request_file.write_text('{}')
            raise interrupted
        out = self.root / 'interrupted-output'
        with patch.object(builder, 'verify_request', return_value=(self.request, self.paths)), patch.object(
                builder.original, 'verify_plan', return_value=({}, {})), patch.object(
                builder.original, 'load_inputs', return_value=context), patch.object(
                builder, 'build_overlay_targets', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:
                builder.build(self.root, self.root, self.request_file, expected, out)
        self.assertIs(caught.exception, interrupted)
        terminal = builder.read(out / 'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual({m['input'] for m in terminal['postcheck']['mismatches']},
                         {'source/source.json', 'frozen_risk_target_request'})
        self.assertFalse(terminal['completed'])
        self.assertFalse((out / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
