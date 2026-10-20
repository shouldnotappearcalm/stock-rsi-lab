import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.capture_low_beta60_minutes_2026 import authenticate_inputs
except ImportError:
    authenticate_inputs = None


class Minute2026EntryTests(unittest.TestCase):
    def test_actual_entry_rejects_wrong_external_sha_or_non247_budget_before_source_access(self):
        self.assertIsNotNone(authenticate_inputs, 'fixed actual247 entry missing')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'plan.json'
            path.write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'plan changed'):
                authenticate_inputs(root, root, path, '0' * 64)
            p = {'status': 'FROZEN_LOW_BETA60_2026_MINUTE_EXTENSION_SOURCE', 'max_fresh_query_reservations': 1,
                 'max_attempts_per_request': 1, 'stop_after_consecutive_source_failures': 3,
                 'inter_query_delay_seconds': .05, 'host': '116.205.183.150:7709',
                 'timeout_seconds': 3, 'package_version': '3.2.3', 'window': ['2026-01-01', '2026-10-13'],
                 'output_directory': 'low-beta60-minutes-2026-20261021', 'method_code_sha256': {}}
            path.write_text(json.dumps(p) + '\n')
            with self.assertRaisesRegex(ValueError, 'protocol'):
                authenticate_inputs(root, root, path, hashlib.sha256(path.read_bytes()).hexdigest())
