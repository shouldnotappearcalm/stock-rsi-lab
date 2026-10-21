import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import capture_price_delay_horizon_raw as api
from scripts.fundamental_query_journal import digest
from tests.test_value_momentum_raw_reassembly_v2 import fixtures


class PriceDelayHorizonRawCaptureTests(unittest.TestCase):
    def test_exact_protocol_and_all_binding_sets_are_required(self):
        r = copy.deepcopy(api.PROFILE)
        for field, names in api.BINDINGS:
            r[field] = dict.fromkeys(names, 'a' * 64)
        r['immutable_financial_sha256'] = dict.fromkeys(api.FINANCIAL_FILES, 'b' * 64)
        r['coordinate_reference_proof_sha256'] = dict.fromkeys(api.COORDINATE_KEYS, 'c' * 64)
        api.check_scope(r)
        for field, value in [('candidate', 'other'), ('maximum_source_reservations', 346),
                             ('max_attempts_per_query', 2), ('maximum_consecutive_failed_codes', 4),
                             ('maximum_administrative_login_attempts', 2), ('socket_timeout_seconds', 21),
                             ('baostock_version', 'other'), ('portfolio_returns_to_compute', True),
                             ('investment_rules_changed', True), ('whole_cache_names', 103),
                             ('incremental_names', 79), ('cold_names', 22),
                             ('window', ['2023-12-29', '2026-10-21']), ('immutable_financial_sha256', {}),
                             ('coordinate_reference_proof_sha256', {})]:
            changed = copy.deepcopy(r)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                api.check_scope(changed)
        for field, _ in api.BINDINGS:
            changed = copy.deepcopy(r)
            changed[field] = {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                api.check_scope(changed)

    def test_checksum_failure_and_existing_output_cannot_connect_or_write(self):
        with tempfile.TemporaryDirectory() as d, patch.object(api.socket, 'setdefaulttimeout') as timeout:
            request = Path(d) / 'request.json'
            request.write_text('{}')
            out = Path(d) / api.OUTPUT
            args = ['--source-root', d, '--request', str(request), '--expected-request-sha256', '0' * 64,
                    '--output-dir', str(out), '--preflight-only']
            with self.assertRaises(ValueError):
                api.main(args)
            self.assertFalse(out.exists())
            timeout.assert_not_called()
            out.mkdir()
            with self.assertRaisesRegex(ValueError, 'existing'):
                api.main(args)

    def test_coordinate_variance_needs_registered_issuer_root_and_unchanged_saved_proof(self):
        old, fresh, notice = fixtures()
        code = 'SZ002608'
        for packet in (old, fresh):
            packet['instrument'] = code
            for field in ('bars', 'distributions', 'adjustments'):
                for row in packet[field]:
                    row['code'] = 'sz.002608'
        notice['instrument'] = code
        notice['file'] = code + '.pdf'
        proof = api.verify_coordinate_transition(fresh, old, notice)
        saved = {code: [proof]}
        full = copy.deepcopy(fresh)
        full['window'][0] = '2023-12-29'
        before = copy.deepcopy((old, full))
        actual = api.verify_cached_reference(code, 'reversal-raw-full-20261017', full, old, notice, saved)
        self.assertEqual(digest(actual), digest(proof))
        self.assertEqual((old, full), before)
        with self.assertRaises(ValueError):
            api.verify_cached_reference(code, 'reversal-raw-full-20261017', full, old, notice, {code: []})
        with self.assertRaises(ValueError):
            api.verify_cached_reference(code, 'unregistered-cache', full, old, notice, saved)
        changed = copy.deepcopy(full)
        changed['adjustments'][0]['backAdjustFactor'] = '9.000001'
        with self.assertRaises(ValueError):
            api.verify_cached_reference(code, 'reversal-raw-full-20261017', changed, old, notice, saved)

    def test_preflight_does_not_create_output_or_invoke_source_client(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / api.OUTPUT
            context = (api.PROFILE, [], [], {}, {}, {}, {}, {})
            with patch.object(api, 'authenticate_request', return_value=context), \
                    patch.object(api, 'version', return_value='0.9.4'), \
                    patch.object(api, 'SourceSession') as client, \
                    patch.object(api.socket, 'setdefaulttimeout') as timeout:
                self.assertEqual(api.main(['--source-root', d, '--request', 'frozen.json',
                    '--expected-request-sha256', 'a' * 64, '--output-dir', str(out), '--preflight-only']), 0)
            client.assert_not_called()
            timeout.assert_not_called()
            self.assertFalse(out.exists())

    def test_completion_requires_exact_scope_full_budget_cleanup_and_unchanged_inputs(self):
        codes = [f'SH{600000 + n}' for n in range(203)]
        manifest = {'requested_names': 203, 'names': 203,
            'per_code_sha256': dict.fromkeys(codes, 'a' * 64), 'errors_sha256': {}, 'pending_codes': [],
            'abnormal_exit': None, 'maximum_source_reservations': 345, 'query_reservations_consumed': 345}
        cleanup = {'login_attempted': True, 'logout_attempted': True, 'error_code': '0'}
        checked, login = {'source_inputs_unchanged_after_capture': True}, {'error_code': '0'}
        self.assertTrue(api.capture_complete(manifest, cleanup, checked, login, codes))
        for obj, field, value in [(manifest, 'names', 202), (manifest, 'errors_sha256', {'SH600000': 'h'}),
                (manifest, 'pending_codes', [codes[0]]), (manifest, 'abnormal_exit', {'error': 'interrupted'}),
                (manifest, 'query_reservations_consumed', 344), (manifest, 'maximum_source_reservations', 346),
                (cleanup, 'logout_attempted', False), (cleanup, 'error_code', '1'),
                (cleanup, 'error', 'socket failure'), (login, 'error_code', '1'),
                (checked, 'source_inputs_unchanged_after_capture', False)]:
            old = copy.deepcopy(obj)
            obj[field] = value
            with self.subTest(field=field):
                self.assertFalse(api.capture_complete(manifest, cleanup, checked, login, codes))
            obj.clear()
            obj.update(old)
        changed = copy.deepcopy(manifest)
        changed['per_code_sha256']['SZ000001'] = changed['per_code_sha256'].pop(codes[0])
        self.assertFalse(api.capture_complete(changed, cleanup, checked, login, codes))


if __name__ == '__main__':
    unittest.main()
