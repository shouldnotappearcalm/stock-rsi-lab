from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import inspect_profitability_historical_initial as inspect
from tests.test_annual_profitability import pages


class HistoricalInitialContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw = self.base / 'original.pdf'
        self.raw.write_bytes(b'SYNTHETIC original PDF source')
        self.documents = [{
            'capture_key':'SYNTHETIC-' + str(i), 'instrument':'SH600001', 'fiscal_year':2022,
            'day':'2023-04-27', 'captured_at_utc':'2026-10-22T00:00:00+00:00',
            'source_sha256':inspect.file_sha(self.raw), 'source_path':'original.pdf', 'announcement_id':str(123456+i)
        } for i in range(5)]
        self.path_map = {'source/original.pdf':self.raw}
        self.request = {'input_sha256':{'source/original.pdf':inspect.file_sha(self.raw)},
                        'source_range_issuer_count':2, 'remaining_source_gap_issuers':['SZ001286']}
        self.request_file = self.base / 'request.json'
        inspect.write_once(self.request_file, self.request)
        self.sha = inspect.file_sha(self.request_file)
        (self.base / inspect.fixed.OUTPUT).mkdir()
        inspect.write_once(self.base / inspect.fixed.OUTPUT / 'case_results.json', {})

    def good(self, base, document):
        source = ['公司代码：600001\n2022年年度报告', *pages(2022)]
        result = inspect.fixed.inspect_document(document, source)
        result['all_extracted_page_text_sha256'] = {
            str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(source)}
        return result, source

    def test_real_worker_checks_original_bytes_before_extracting(self):
        document = self.documents[0]
        source = ['公司代码：600001\n2022年年度报告', *pages(2022)]
        with patch.object(inspect.fixed, 'pages_from_pdf', return_value=source) as extract:
            result, saved = inspect.inspect_one(str(self.base), document)
            self.assertEqual(result['status'],'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW')
            self.assertEqual(saved,source)
            self.raw.write_bytes(b'mutated')
            with self.assertRaisesRegex(ValueError,'worker source hash changed'):
                inspect.inspect_one(str(self.base), document)
            self.assertEqual(extract.call_count,1)

    def run_inspection(self, worker):
        with patch.object(inspect, 'verify', return_value=(self.request,self.path_map,self.documents)):
            return inspect.run(self.base,self.base,self.raw,self.request_file,self.sha,
                               self.base / inspect.OUTPUT,executor_factory=ThreadPoolExecutor,worker=worker)

    def test_all_editions_full_text_and_missing_issuers_retained_without_admission(self):
        # Thread-only synthetic runner avoids subprocesses in CI. Production
        # uses four process workers with the same ordered result persistence.
        result = self.run_inspection(self.good)
        out = self.base / inspect.OUTPUT
        self.assertEqual(result['document_count'],5)
        self.assertEqual(result['source_issuer_count'],1)
        self.assertEqual(result['remaining_source_gap_issuers'],['SZ001286'])
        self.assertEqual(result['source_observation_count'],10)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['historical_arrival_verified'])
        self.assertFalse(result['security_ranking_or_portfolio_returns_computed'])
        self.assertEqual(len(list(out.glob('*.pages.json'))),5)
        self.assertEqual(len(list(out.glob('batch-*.json'))),2)
        for d in self.documents:
            source = inspect.read(out / (d['capture_key']+'.pages.json'))
            case = inspect.read(out / (d['capture_key']+'.json'))
            self.assertEqual(source['source_sha256'],d['source_sha256'])
            self.assertEqual(case['all_extracted_page_text_sha256'],{
                str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(source['pages'])})
        with self.assertRaisesRegex(ValueError,'no retry/resume'):
            self.run_inspection(self.good)

    def test_wrong_identity_and_unknown_units_are_not_filtered_from_whole_cohort(self):
        def inspect_unsupported(base, document):
            source = ['公司代码：600001\n2022年年度报告', *pages(2022)]
            if document['capture_key'].endswith('0'):
                source[0] = source[0].replace('600001','600002')
            else:
                source = [p.replace('单位:元','单位:百万元') for p in source]
            # No shared monkeypatch during concurrent work.
            result = inspect.fixed.inspect_document(document,source)
            result['all_extracted_page_text_sha256'] = {
                str(i+1):hashlib.sha256(p.encode()).hexdigest() for i,p in enumerate(source)}
            return result,source
        result = self.run_inspection(inspect_unsupported)
        self.assertEqual(result['document_count'],5)
        self.assertEqual(result['status_counts'],{'COVER_IDENTITY_UNVERIFIED':1,'SOURCE_SCHEMA_UNSUPPORTED':4})
        self.assertEqual(result['supported_source_issuer_count'],0)
        self.assertEqual(result['source_observation_count'],0)

    def test_original_worker_interrupt_rehashes_inputs_and_never_submits_next_batch(self):
        original = KeyboardInterrupt('source decode interrupted')
        def interrupted(base, document):
            self.raw.write_bytes(b'changed source')
            self.request_file.write_text('{}')
            raise original
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_inspection(interrupted)
        self.assertIs(caught.exception,original)
        out = self.base / inspect.OUTPUT
        terminal = inspect.read(out / 'terminal.json')
        self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
        self.assertEqual(len(terminal['submitted_keys']),4)
        self.assertEqual(terminal['completed_documents'],0)
        self.assertEqual(len(terminal['pending']),5)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
                         {'source/original.pdf','frozen_source_request'})
        self.assertFalse((out / 'summary.json').exists())

    def test_worker_identity_and_extracted_text_conservation_fail_closed(self):
        def corrupt(base, document):
            result,source = self.good(base,document)
            result['all_extracted_page_text_sha256']['1'] = '0'*64
            return result,source
        with self.assertRaisesRegex(ValueError,'complete extracted physical pages'):
            self.run_inspection(corrupt)
        self.assertFalse((self.base / inspect.OUTPUT / 'summary.json').exists())

    def test_old_supported_report_regression_cannot_succeed(self):
        before,_ = self.good(str(self.base),self.documents[0])
        after = {**before,'status':'SOURCE_SCHEMA_UNSUPPORTED','source_observations':[]}
        with self.assertRaisesRegex(ValueError,'old supported initial report lost'):
            inspect.preserve_old_supported({before['capture_key']:after},{before['capture_key']:before})
        after = {**before,'source_sha256':'0'*64}
        with self.assertRaisesRegex(ValueError,'source observations changed'):
            inspect.preserve_old_supported({before['capture_key']:after},{before['capture_key']:before})


if __name__ == '__main__': unittest.main()
