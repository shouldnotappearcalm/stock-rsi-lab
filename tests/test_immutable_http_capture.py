from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from scripts.immutable_http_capture import ImmutableHttpCapture, digest, file_sha


class Response(BytesIO):
    def __init__(self, body=b'raw original', status=200, url='https://www.cninfo.com.cn/api', length=None):
        super().__init__(body)
        self.status, self.url = status, url
        self.headers = {'Content-Type': 'application/json'}
        if length is not None:
            self.headers['Content-Length'] = length


class ImmutableHttpCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = {'A': {'method': 'POST', 'url': 'https://www.cninfo.com.cn/api', 'payload': {'stock': 'A'}}}

    def journal(self, opener, cap=100):
        return ImmutableHttpCapture(self.root / 'http', self.resources, max_attempts=1, max_body_bytes=cap, opener=opener)

    def test_reservation_precedes_only_attempt_and_original_bytes_are_preserved(self):
        calls = []
        def opener(request, timeout):
            reservations = list(self.root.rglob('reservation.json'))
            self.assertEqual(len(reservations), 1)
            self.assertTrue(reservations[0].with_name('request.json').exists())
            self.assertEqual(timeout, 20)
            calls.append(request.full_url)
            body = b'{  "raw": true }\n'
            return Response(body, length=str(len(body)))
        journal = self.journal(opener)
        receipt, body = journal.fetch('A')
        self.assertEqual(body.read_bytes(), b'{  "raw": true }\n')
        self.assertEqual(file_sha(body), receipt['record']['body_sha256'])
        self.assertEqual(journal.attempts, 1)
        with self.assertRaisesRegex(ValueError, 'retry forbidden'):
            journal.fetch('A')
        self.assertEqual(len(calls), 1)

    def test_http_error_body_is_retained_without_retry_or_semantic_admission(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 503, 'temporary failure', {}, BytesIO(b'original failure page'))
        journal = self.journal(opener)
        receipt, body = journal.fetch('A')
        self.assertEqual(receipt['record']['http_status'], 503)
        self.assertEqual(body.read_bytes(), b'original failure page')
        self.assertEqual(receipt['record']['status'], 'RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED')

    def test_interrupted_outcome_consumes_reservation_and_cannot_refetch(self):
        original = KeyboardInterrupt('source interrupted')
        def opener(request, timeout):
            raise original
        journal = self.journal(opener)
        with self.assertRaises(KeyboardInterrupt) as caught:
            journal.fetch('A')
        self.assertIs(caught.exception, original)
        record = json.loads(next(self.root.rglob('response.json')).read_text())
        self.assertEqual(record['error_type'], 'KeyboardInterrupt')
        with self.assertRaisesRegex(ValueError, 'retry forbidden'):
            journal.fetch('A')
        self.assertEqual(journal.attempts, 1)

    def test_oversize_prefix_and_truncated_response_are_preserved_and_rejected(self):
        for body, length, cap, message in [(b'abcdef', None, 3, 'body cap'),
                                            (b'abc', '10', 100, 'incomplete declared')]:
            with self.subTest(message=message):
                root = self.root / message.replace(' ', '-')
                journal = ImmutableHttpCapture(root, self.resources, max_attempts=1, max_body_bytes=cap,
                    opener=lambda request, timeout: Response(body, length=length))
                with self.assertRaisesRegex(ValueError, message):
                    journal.fetch('A')
                saved = next(root.rglob('body.bin')).read_bytes()
                self.assertEqual(saved, body[:cap+1])
                self.assertFalse(json.loads(next(root.rglob('response.json')).read_text())['body_complete'])

    def test_unknown_resource_duplicate_identity_redirect_and_external_mutation_are_guarded(self):
        with self.assertRaisesRegex(ValueError, 'duplicate logical'):
            ImmutableHttpCapture(self.root / 'duplicate', {'A': self.resources['A'], 'B': self.resources['A']},
                                 max_attempts=2, max_body_bytes=100)
        journal = self.journal(lambda request, timeout: Response(url='https://example.org/api'))
        with self.assertRaisesRegex(ValueError, 'outside frozen HTTP scope'):
            journal.fetch('UNKNOWN')
        self.resources['A']['url'] = 'https://example.org/changed'
        with self.assertRaisesRegex(ValueError, 'outside frozen host'):
            journal.fetch('A')
        record = json.loads(next(self.root.rglob('request.json')).read_text())
        self.assertEqual(record['url'], 'https://www.cninfo.com.cn/api')
        self.assertTrue(next(self.root.rglob('body.bin')).exists())


if __name__ == '__main__':
    unittest.main()
