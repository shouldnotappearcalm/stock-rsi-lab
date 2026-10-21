import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import capture_price_delay_horizon_remaining_primary as api


class PriceDelayHorizonFourPrimaryTests(unittest.TestCase):
    def request(self, base):
        repo = Path(api.__file__).resolve().parents[1]
        for name in api.LOCAL:
            p = base / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        r = copy.deepcopy(api.PROFILE)
        for field, names, root in (('method_code_sha256', api.METHODS, repo),
                ('public_evidence_sha256', api.PUBLIC, repo), ('local_source_sha256', api.LOCAL, base)):
            r[field] = {n: api.file_sha(root / n) for n in names}
        p = base / 'frozen.json'
        p.write_text(json.dumps(r, indent=2) + '\n')
        return ['--source-root', str(base), '--request', str(p),
            '--expected-request-sha256', api.file_sha(p), '--output-dir', str(base / api.OUTPUT)]

    def test_preflight_and_existing_output_never_fetch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(api, 'read_wire') as fetch:
            base = Path(d)
            args = self.request(base)
            self.assertEqual(api.main(args + ['--preflight-only']), 0)
            self.assertFalse((base / api.OUTPUT).exists())
            (base / api.OUTPUT).mkdir()
            with self.assertRaisesRegex(ValueError, 'preserve'):
                api.main(args)
            fetch.assert_not_called()

    def test_four_original_receipts_retained_and_mutated_postcheck_cannot_complete(self):
        for mutate in (False, True):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as d:
                base = Path(d)
                args = self.request(base)
                calls = []
                def fetch(url, payload):
                    calls.append(url)
                    if mutate:
                        (base / api.LOCAL[1]).write_text('{"changed":true}')
                    return ['http_response'], [{'status': 200, 'final_url': url,
                        'body_base64': base64.b64encode(b'%PDF synthetic').decode(),
                        'body_truncated': False, 'body_complete': True,
                        'read_error_type': None, 'read_error': None}]
                with patch.object(api, 'read_wire', side_effect=fetch), patch.object(api.time, 'sleep'):
                    self.assertEqual(api.main(args), 2 if mutate else 0)
                self.assertEqual(calls, [x['url'] for x in api.DOCUMENTS])
                out = base / api.OUTPUT
                self.assertEqual(len(list(out.rglob('response-1.json'))), 4)
                self.assertEqual(len(list(out.rglob('reserved-1.json'))), 4)
                scope = api.read(out / 'price-delay-scope.json')
                self.assertEqual(scope['capture_complete'], not mutate)
                self.assertFalse(scope['documents_financially_reviewed'])
                self.assertFalse(scope['source_admitted_for_account_replay'])


if __name__ == '__main__':
    unittest.main()
