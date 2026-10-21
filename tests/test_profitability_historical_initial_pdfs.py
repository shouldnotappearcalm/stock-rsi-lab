from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import capture_profitability_historical_initial_pdfs as capture


class Response(BytesIO):
    def __init__(self, url, body):
        super().__init__(body)
        self.url, self.status = url, 200
        self.headers = {'Content-Type': 'application/pdf', 'Content-Length': str(len(body))}


class HistoricalInitialPDFCaptureTests(unittest.TestCase):
    def test_source_backed_title_aliases_still_require_explicit_year_and_full_report(self):
        for title in ('600511_国药股份_2022年_年度报告', '《中国软件2022年年度报告》（修订稿）',
                      '《中国软件2022年年度报告》', '重庆水务2022年年度报告（更正版）',
                      '重庆水务集团股份有限公司2022年年报', '601636_2022年_年度报告'):
            with self.subTest(title=title): self.assertTrue(capture.full_title(title))
        for title in ('年报全文', '2023年年度报告', '2022年年度报告摘要', '2022年年报摘要',
                      '2022年年度报告（英文版）', '2022年年度报告（可视版）', '2022年半年度报告',
                      '关于2022年年度报告的更正公告'):
            with self.subTest(title=title): self.assertFalse(capture.full_title(title))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.old = self.base / 'old.pdf'
        self.old.write_bytes(b'%PDF-synthetic old source')
        self.paths = {'source/old.pdf': self.old}
        # Transport fixtures deliberately check PDF magic only, never admission
        # as a parsed financial report. The source stage keeps admission false.
        self.documents = []
        for index in range(36):
            record = {'capture_key': 'SYNTHETIC-'+str(index), 'instrument': 'SH600001',
                      'fiscal_year': 2022, 'url': 'https://static.cninfo.com.cn/finalpage/2023-04-27/'+str(index)+'.PDF',
                      'source_kind': 'REUSE_AUTHENTICATED_ORIGINAL_PDF' if index in (1,2) else 'FRESH_FROZEN_PDF_GET'}
            if index in (1,2):
                record.update(source_path='old.pdf', source_sha256=capture.file_sha(self.old))
            self.documents.append(record)
        self.request = {'documents': self.documents, 'resources': capture.resources(self.documents),
                        'cache_reuse_count': 2, 'input_sha256': {key: capture.file_sha(p) for key,p in self.paths.items()}}
        self.request_file = self.base / 'request.json'
        capture.write_once(self.request_file, self.request)
        self.sha = capture.file_sha(self.request_file)
        self.calls = []

    def run_capture(self, opener):
        with patch.object(capture, 'verify', return_value=(self.request, self.paths)):
            return capture.capture(self.base, self.base, self.old, self.request_file, self.sha,
                                   self.base/capture.OUTPUT, opener=opener, pause=lambda seconds: None)

    def good(self, request, timeout):
        self.calls.append(request.full_url)
        return Response(request.full_url, b'%PDF-'+b'SYNTHETIC'*125)

    def test_exact36_records34_GETs_and_two_unchanged_reuses_without_numeric_admission(self):
        result = self.run_capture(self.good)
        self.assertEqual(len(self.calls), 34)
        self.assertEqual(result['logical_attempts'], 34)
        self.assertEqual(result['documents_recorded'], 36)
        self.assertEqual(result['cached_reused'], 2)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['financial_numeric_values_decoded'])
        self.assertEqual(capture.file_sha(self.old), self.paths and self.request['input_sha256']['source/old.pdf'])
        with self.assertRaisesRegex(ValueError, 'no retry/resume'):
            self.run_capture(self.good)
        self.assertEqual(len(self.calls), 34)

    def test_original_nonPDF_responses_are_retained_three_failures_stop(self):
        def fail(request, timeout):
            self.calls.append(request.full_url)
            return Response(request.full_url, b'original nonPDF response')
        with self.assertRaisesRegex(ValueError, 'three consecutive'):
            self.run_capture(fail)
        out = self.base/capture.OUTPUT
        terminal = capture.read(out/'terminal.json')
        # Two intervening cache records reset the source-failure streak; five
        # document records (two reused) precede the third consecutive fresh fail.
        self.assertEqual(terminal['logical_attempts'], 4)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(len(list(out.rglob('body.bin'))), 4)
        self.assertFalse((out/'summary.json').exists())

    def test_interrupted_download_rehashes_cache_and_request_keeps_original_error(self):
        interrupted = KeyboardInterrupt('original PDF download interruption')
        def fail(request, timeout):
            self.old.write_bytes(b'changed cached bytes')
            self.request_file.write_text('{}')
            raise interrupted
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_capture(fail)
        self.assertIs(caught.exception, interrupted)
        terminal = capture.read(self.base/capture.OUTPUT/'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual(terminal['logical_attempts'], 1)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
                         {'source/old.pdf','frozen_source_request'})
        self.assertFalse((self.base/capture.OUTPUT/'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
