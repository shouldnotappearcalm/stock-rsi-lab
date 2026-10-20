import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.capture_low_beta60_raw_extension import SourceSession, authenticate_request, METHOD_FILES
except ImportError:
    SourceSession = authenticate_request = METHOD_FILES = None


class ExtensionSourceEntryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SourceSession, 'bounded source entry missing')

    def test_failed_administrative_login_is_recorded_once_and_not_retried(self):
        class SDK:
            attempts = 0
            def login(self):
                self.attempts += 1
                raise OSError('synthetic login unavailable')
            def logout(self):
                return type('Result', (), {'error_code': '0', 'error_msg': ''})()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            sdk = SDK()
            session = SourceSession(out, 'a' * 64, sdk)
            for _ in range(3):
                with self.assertRaises((OSError, RuntimeError)):
                    session('SH600153', 'daily', {})
            session.close()
            self.assertEqual(sdk.attempts, 1)
            self.assertEqual(len(list(out.glob('login-reserved-*.json'))), 1)
            result = json.loads((out / 'login-response-1.json').read_text())
            self.assertEqual(result['error_type'], 'OSError')
            self.assertTrue((out / 'logout-response.json').exists())

    def test_bad_request_or_method_binding_rejected_before_source_files(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'request.json'
            path.write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'request changed'):
                authenticate_request(path, '0' * 64, repo, base / 'no-sources')
            request = {'status': 'FROZEN_LOW_BETA60_RAW_EXTENSION_SOURCE_REQUEST',
                'window': ['2023-12-29', '2026-10-13'], 'maximum_source_reservations': 76,
                'max_attempts_per_query': 1, 'maximum_consecutive_failed_codes': 3,
                'maximum_administrative_login_attempts': 1, 'socket_timeout_seconds': 20,
                'output_directory': 'low-beta60-raw-extension-20261021',
                'baostock_version': '0.9.4', 'method_code_sha256': {n: '0' * 64 for n in METHOD_FILES}}
            path.write_text(json.dumps(request) + '\n')
            with self.assertRaisesRegex(ValueError, 'method changed'):
                authenticate_request(path, hashlib.sha256(path.read_bytes()).hexdigest(), repo, base / 'no-sources')

    def test_nonzero_sdk_login_response_retains_exact_provider_error_code(self):
        class SDK:
            def login(self):
                return type('Result', (), {'error_code': '10001020', 'error_msg': 'synthetic denied'})()
            def logout(self):
                return type('Result', (), {'error_code': '0', 'error_msg': ''})()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            session = SourceSession(out, 'a' * 64, SDK())
            with self.assertRaises(RuntimeError):
                session('SH600153', 'daily', {})
            saved = json.loads((out / 'login-response-1.json').read_text())
            self.assertEqual(saved.get('error_code'), '10001020')
            self.assertEqual(saved.get('error_msg'), 'synthetic denied')
            self.assertEqual(saved['error_type'], 'RuntimeError')
            session.close()
