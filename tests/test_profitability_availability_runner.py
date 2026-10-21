from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_profitability_availability as build


class AvailabilityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'; self.source.write_text('source')
        self.request = self.base / 'request.json'
        self.req = {'input_sha256': {'source/source': build.file_sha(self.source)},
                    'documents': [], 'cohort': ['SH600001'],
                    'formations': [{'execution_session': '2024-01-02', 'as_of': '2023-12-29T15:05:00+08:00'}],
                    'modes': ['OBSERVED', 'RECONSTRUCTED_PUBLICATION_DAY_END']}
        build.write_once(self.request, self.req); self.reqsha = build.file_sha(self.request)
        for name, obj in ((build.V7_OUTPUT, {}), (build.INDUSTRY_OUTPUT, {})):
            folder = self.base / name; folder.mkdir()
            build.write_once(folder / ('case_results.json' if name == build.V7_OUTPUT else 'catalog.json'), obj)

    def run_source(self, builder):
        with patch.object(build, 'verify', return_value=(self.req, {'source/source': self.source})):
            return build.run(self.base, self.base, self.base / 'membership', self.request, self.reqsha, builder=builder)

    @staticmethod
    def snapshot(*args, **kwargs):
        return {'classifications': [{'instrument': 'SH600001', 'annual_status': 'NO_VISIBLE_ANNUAL_REPORT',
                                     'industry_status': 'NOT_IN_SOURCE_VINTAGE'}]}

    def test_complete_queries_and_fresh_only(self):
        result = self.run_source(self.snapshot)
        self.assertEqual(len(result['queries']), 2)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['objective_achieved'])
        self.assertEqual(build.read(self.base / build.OUTPUT / 'terminal.json')['pending_query_count'], 0)
        with self.assertRaisesRegex(ValueError, 'no resume'): self.run_source(self.snapshot)

    def test_interrupt_retains_prefix_original_exception_and_request_posthash(self):
        error = KeyboardInterrupt('source interrupted')
        def builder(*args, **kwargs):
            if kwargs['mode'] != 'OBSERVED':
                self.source.unlink(); self.request.write_text('{}'); raise error
            return self.snapshot()
        with self.assertRaises(KeyboardInterrupt) as caught: self.run_source(builder)
        self.assertIs(caught.exception, error)
        terminal = build.read(self.base / build.OUTPUT / 'terminal.json')
        self.assertEqual(len(terminal['completed_queries']), 1)
        self.assertEqual(terminal['pending_query_count'], 1)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']}, {'source/source', 'frozen_source_request'})
        self.assertFalse((self.base / build.OUTPUT / 'summary.json').exists())

    def test_input_change_blocks_success_after_all_queries(self):
        def builder(*args, **kwargs):
            self.source.write_text('changed'); return self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unchanged availability'): self.run_source(builder)
        self.assertFalse((self.base / build.OUTPUT / 'summary.json').exists())

    def test_parent_catalog_aliases_are_resolved_without_dropping_original_bindings(self):
        fixed = self.base / 'gross-profitability-fixed12-annual-pdfs-20261022'
        fixed.mkdir()
        build.write_once(fixed / 'documents.json', [{'capture_key':'test', 'source_path':'old/original.bin'}])
        root, base, membership = self.base, self.base, self.base / 'membership'
        self.assertEqual(build.resolve('catalog/PDF/test', root, base, membership), base / 'old/original.bin')
        self.assertEqual(build.resolve('catalog/membership_intervals', root, base, membership), membership)
        self.assertEqual(build.resolve('catalog/metadata/SH600001', root, base, membership),
                         base / 'cninfo-csi500-reports-20261017/codes/SH600001.json')
        with self.assertRaises(ValueError): build.resolve('catalog/PDF/unknown', root, base, membership)
        with self.assertRaises(ValueError): build.resolve('catalog/metadata/../secret', root, base, membership)


if __name__ == '__main__': unittest.main()
