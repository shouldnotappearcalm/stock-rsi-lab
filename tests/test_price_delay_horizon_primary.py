import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import capture_price_delay_horizon_primary as api


class PriceDelayHorizonPrimaryTests(unittest.TestCase):
    def setup_request(self, base):
        repo = Path(api.__file__).resolve().parents[1]
        for name in api.LOCAL:
            p = base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        r = copy.deepcopy(api.PROFILE)
        r['protocol_sha256'] = api.file_sha(repo / api.PROTOCOL)
        r['method_code_sha256'] = {n: api.file_sha(repo / n) for n in api.METHODS}
        r['local_source_sha256'] = {n: api.file_sha(base / n) for n in api.LOCAL}
        path = base / 'frozen.json'
        path.write_text(json.dumps(r))
        return path, ['--source-root', str(base), '--request', str(path),
            '--expected-request-sha256', api.file_sha(path), '--output-dir', str(base / api.OUTPUT)]

    def test_preflight_and_bad_checksum_preserve_output_and_do_not_fetch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(api, 'read_wire') as wire:
            base = Path(d)
            request, args = self.setup_request(base)
            self.assertEqual(api.main(args + ['--preflight-only']), 0)
            self.assertFalse((base / api.OUTPUT).exists())
            request.write_text('{}')
            with self.assertRaises(ValueError):
                api.main(args)
            wire.assert_not_called()

    def test_http_projection_failure_retains_response_and_forbids_retry(self):
        for body, complete, expected in [(b'%PDF fixture', True, 0), (b'wrong format', True, 2),
                                         (b'%PDF truncated', False, 2)]:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                _, args = self.setup_request(base)
                response = (['http_response'], [{'status': 200, 'final_url': api.PROFILE['url'],
                    'body_truncated': False, 'body_complete': complete, 'read_error_type': None,
                    'read_error': None, 'body_base64': base64.b64encode(body).decode()}])
                with patch.object(api, 'read_wire', return_value=response) as wire:
                    self.assertEqual(api.main(args), expected)
                    wire.assert_called_once()
                    with self.assertRaisesRegex(ValueError, 'preserve'):
                        api.main(args)
                out = base / api.OUTPUT
                self.assertEqual(len(list(out.rglob('response-1.json'))), 1)
                m = api.read(out / 'manifest.json')
                self.assertEqual(m['capture_complete'], expected == 0)
                self.assertFalse(m['documents_financially_reviewed'])
                self.assertFalse(m['source_admitted_for_account_replay'])
                self.assertEqual(m['http_query_reservations'], 1)


if __name__ == '__main__':
    unittest.main()
