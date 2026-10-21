from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from scripts import capture_profitability_initial_annual_metadata as capture


STAMP = int(datetime.fromisoformat('2023-04-27T00:00:00+08:00').timestamp() * 1000)


def row(code='600001', title='2022年年度报告', identity='123456'):
    return {'secCode': code, 'announcementTitle': title, 'announcementTime': STAMP,
            'announcementId': identity, 'adjunctUrl': 'finalpage/2023-04-27/' + identity + '.PDF'}


def metadata(rows):
    return {'totalAnnouncement': len(rows), 'hasMore': False, 'announcements': rows}


class Response(BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status
        self.url = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
        self.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body))}


class InitialAnnualMetadataTests(unittest.TestCase):
    def test_original_title_variants_and_all_distinct_revised_reports_are_retained(self):
        data = metadata([row(), row(title='公司2022年度报告全文', identity='234567'),
                         row(title='2022年年度报告摘要', identity='345678'),
                         row(title='2022年年度报告（可视版）', identity='456789')])
        allrows, selected = capture.select_rows('SH600001', data)
        self.assertEqual(len(allrows), 4)
        self.assertEqual([r['announcement_id'] for r in selected], ['123456', '234567'])
        self.assertEqual(allrows[2]['classification'], 'SUMMARY')
        self.assertEqual(allrows[3]['classification'], 'VISUAL_EDITION')
        _, amended = capture.select_rows('SH600001', metadata([row(title='2022年年度报告（修订版）')]))
        self.assertEqual(len(amended), 1)

    def test_incomplete_page_future_wrong_code_duplicate_unsafe_path_or_no_full_report_fail(self):
        wrong = row(); wrong['announcementTime'] = int(datetime.fromisoformat('2026-04-27T00:00:00+08:00').timestamp()*1000)
        unsafe = row(); unsafe['adjunctUrl'] = '../outside.pdf'
        cases = [metadata([wrong]), metadata([row(code='600002')]), metadata([row(), row()]),
                 metadata([unsafe]), metadata([row(title='2022年年度报告摘要')]),
                 {**metadata([row()]), 'totalAnnouncement': 31},
                 {**metadata([row()]), 'hasMore': True}, metadata([row(), row(identity='222222'), row(identity='333333')])]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                capture.select_rows('SH600001', data)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw = self.base / 'old-source.json'
        self.raw.write_text('original source metadata')
        self.paths = {'source/old-source.json': self.raw}
        self.codes = ['SH' + str(600001+i) for i in range(12)]
        self.request = {'codes': self.codes, 'resources': {code: capture.metadata_resource(code, 'org-'+code) for code in self.codes},
                        'input_sha256': {k: capture.file_sha(p) for k,p in self.paths.items()}}
        self.request_file = self.base / 'request.json'
        capture.write_once(self.request_file, self.request)
        self.sha = capture.file_sha(self.request_file)
        self.calls = []

    def opener(self, request, timeout):
        code = parse_qs(request.data.decode())['stock'][0].split(',')[0]
        self.calls.append(code)
        self.assertEqual(parse_qs(request.data.decode())['seDate'], ['2023-01-01~2023-12-31'])
        return Response(json.dumps(metadata([row(code=code, identity='2022'+code)])).encode())

    def run_capture(self, opener):
        with patch.object(capture, 'verify', return_value=(self.request, self.paths)):
            return capture.capture(self.base, self.base, self.request_file, self.sha,
                                   self.base / capture.OUTPUT, opener=opener, pause=lambda seconds: None)

    def test_all12_once_with_raw_bytes_inputs_and_selected_source_ids(self):
        result = self.run_capture(self.opener)
        self.assertEqual(result['status'], 'INITIAL2022_METADATA_CAPTURE_COMPLETE')
        self.assertEqual(self.calls, [c[2:] for c in self.codes])
        self.assertEqual(result['logical_attempts'], 12)
        self.assertEqual(len(list((self.base/capture.OUTPUT).rglob('body.bin'))), 12)
        self.assertTrue(result['all_inputs_unchanged'])
        self.assertFalse(result['investment_factor_admitted'])
        with self.assertRaisesRegex(ValueError, 'no retry/resume'):
            self.run_capture(self.opener)
        self.assertEqual(len(self.calls), 12)

    def test_three_consecutive_http_failures_stop_without_unregistered_requests(self):
        def fail(request, timeout):
            self.calls.append(request.full_url)
            return Response(b'original503body', status=503)
        with self.assertRaisesRegex(ValueError, 'three consecutive'):
            self.run_capture(fail)
        out = self.base / capture.OUTPUT
        terminal = capture.read(out / 'terminal.json')
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(terminal['logical_attempts'], 3)
        self.assertEqual(len(terminal['pending']), 9)
        self.assertEqual(len(list(out.rglob('body.bin'))), 3)
        self.assertFalse((out / 'summary.json').exists())

    def test_interruption_keeps_first_error_and_rehashes_source_and_request(self):
        original = KeyboardInterrupt('original source interruption')
        def interrupt(request, timeout):
            self.raw.unlink()
            self.request_file.write_text('{}')
            raise original
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_capture(interrupt)
        self.assertIs(caught.exception, original)
        out = self.base / capture.OUTPUT
        terminal = capture.read(out/'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual(terminal['logical_attempts'], 1)
        self.assertEqual({m['input'] for m in terminal['postcheck']['mismatches']},
                         {'source/old-source.json', 'frozen_source_request'})
        self.assertEqual(len(list(out.rglob('reservation.json'))), 1)
        self.assertFalse((out/'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
