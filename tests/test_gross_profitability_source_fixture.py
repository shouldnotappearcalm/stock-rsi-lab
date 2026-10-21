import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_gross_profitability_source_fixture as build


class GrossProfitSourceFreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method, self.raw = self.root / 'method.py', self.root / 'original.pdf'
        self.method.write_text('synthetic frozen method')
        self.raw.write_text('synthetic original source')
        self.paths = {'repo/method.py': self.method, 'source/original.pdf': self.raw}
        self.request = {'status': build.STATUS, 'contract': build.CONTRACT, 'instrument': 'SH600166',
            'report_years': [2023, 2024], 'pypdf_version': '6.10.0', 'max_publication_day': '2025-12-31',
            'portfolio_returns_permitted': False, 'ranking_permitted': False,
            '2026_financial_or_market_values_permitted': False,
            'method_sha256': {'method.py': build.sha(self.method)},
            'input_sha256': {name: build.sha(path) for name, path in self.paths.items()}}
        self.request_file = self.root / 'request.json'

    def verify(self, data=None):
        build.write(self.request_file, self.request if data is None else data)
        with patch.object(build, 'METHODS', ('method.py',)), patch.object(
                build, 'required_paths', return_value=self.paths), patch.object(
                build, 'read', side_effect=[build.read(self.request_file), {'documents': []}, {'expected_cells_CNY': {}}]):
            return build.verify(self.root, self.root, self.request_file, build.sha(self.request_file))

    def test_returns_ranking_future_data_and_extractor_version_cannot_change(self):
        for key, value in [('ranking_permitted', True), ('portfolio_returns_permitted', True),
                           ('2026_financial_or_market_values_permitted', True), ('pypdf_version', 'different'),
                           ('report_years', [2024, 2025]), ('max_publication_day', '2026-10-20')]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'fixed two-document'):
                self.verify({**self.request, key: value})

    def test_source_omission_mutation_and_frozen_request_rewrite_fail(self):
        changed = copy.deepcopy(self.request)
        del changed['input_sha256']['source/original.pdf']
        with self.assertRaisesRegex(ValueError, 'complete fixed'):
            self.verify(changed)
        self.raw.write_text('tampered original')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            self.verify()
        with self.assertRaisesRegex(ValueError, 'request changed'):
            build.verify(self.root, self.root, self.request_file, '0'*64)

    def test_existing_source_failure_is_not_overwritten(self):
        out = self.root / 'existing'
        out.mkdir()
        marker = out / 'terminal.json'
        marker.write_text('original failure')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            build.generate(self.root, self.root, self.request_file, 'unused', out)
        self.assertEqual(marker.read_text(), 'original failure')

    def test_interrupted_pdf_read_preserves_original_error_and_rechecks_inputs_and_request(self):
        build.write(self.request_file, self.request)
        frozen_sha = build.sha(self.request_file)
        original = KeyboardInterrupt('original PDF read interruption')
        def interrupt(path):
            self.raw.unlink()
            build.write(self.request_file, {})
            raise original
        out = self.root / 'interrupted'
        with patch.object(build, 'verify', return_value=(self.request, self.paths,
                {'documents': [{'statDate': '2023-12-31', 'file': 'synthetic.pdf'}]}, {})), patch.object(
                build, 'pdf_pages', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:
                build.generate(self.root, self.root, self.request_file, frozen_sha, out)
        self.assertIs(caught.exception, original)
        terminal = build.read(out / 'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertFalse(terminal['completed'])
        self.assertEqual({row['input'] for row in terminal['postcheck']['mismatches']},
                         {'source/original.pdf', 'frozen_source_request'})
        self.assertFalse((out / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
