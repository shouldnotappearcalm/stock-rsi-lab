import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.fundamental_query_journal import QueryJournal
from scripts.tdx_history_checks import minute_labels

try:
    from scripts.low_beta60_2026_minute_sources import (
        capture_extension, query_packet, inspect_packet, verify_receipt,
    )
except ImportError:
    capture_extension = query_packet = inspect_packet = verify_receipt = None


CODE, DAY = 'SH600153', '2026-01-05'


def payload(code=CODE, day=DAY):
    return {'exchange': code[:2].lower(), 'market_id': 1 if code.startswith('SH') else 0,
            'code': code[2:], 'trading_date': day,
            'points': [{'index': i, 'time_label': label, 'time': day + 'T' + label + ':00+08:00',
                       'price_milli': 10000, 'price': 10, 'volume': 500}
                       for i, label in enumerate(minute_labels())]}


def plan(budget):
    return {'max_fresh_query_reservations': budget, 'max_attempts_per_request': 1,
            'stop_after_consecutive_source_failures': 3, 'inter_query_delay_seconds': 0,
            'host': '116.205.183.150:7709'}


class LowBeta2026MinuteTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(capture_extension, '2026 minute source extension missing')

    def test_date_cap_rejects_past_future_noncanonical_and_wrong_security_before_query(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = QueryJournal(directory, max_queries=1, max_attempts=1)
            for code, day in [(CODE, '2025-12-31'), (CODE, '2026-10-14'), (CODE, '2026-1-5'),
                              ('sh.600153', DAY), (CODE, True)]:
                with self.subTest(code=code, day=day), self.assertRaises(ValueError):
                    query_packet(journal, code, day, '116.205.183.150:7709', lambda: self.fail('source called'))
            self.assertFalse(list(Path(directory).rglob('reserved-*.json')))

    def test_receipt_binds_exact_source_payload_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = QueryJournal(directory, max_queries=1, max_attempts=1)
            saved = query_packet(journal, CODE, DAY, '116.205.183.150:7709', payload)
            verify_receipt(Path(directory), CODE, DAY, saved, '116.205.183.150:7709')
            saved['response']['points'][0]['price_milli'] = 9990
            with self.assertRaises(ValueError):
                verify_receipt(Path(directory), CODE, DAY, saved, '116.205.183.150:7709')

    def test_query_request_byte_mutation_is_rejected_even_when_json_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = QueryJournal(root, max_queries=1, max_attempts=1)
            saved = query_packet(journal, CODE, DAY, '116.205.183.150:7709', payload)
            path = next(root.rglob('request.json'))
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(ValueError):
                verify_receipt(root, CODE, DAY, saved, '116.205.183.150:7709')

    def test_capture_snapshot_bytes_are_bound_to_external_manifest_sha(self):
        import scripts.low_beta60_2026_minute_sources as module
        check = getattr(module, 'verify_snapshot', None)
        self.assertIsNotNone(check, 'external snapshot byte guard missing')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            out = base / 'out'
            m = capture_extension(base, out, {}, [[CODE, DAY]], plan(1), lambda *x: payload())
            expected = hashlib.sha256((out / 'manifest.json').read_bytes()).hexdigest()
            check(out, m, expected)
            path = next(out.glob('capture-snapshot-*.json'))
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(ValueError):
                check(out, m, expected)

    def test_capture_copies_source_bytes_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'origin/sessions' / (CODE + '-' + DAY + '.json')
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'instrument': CODE, 'requested_day': DAY,
                'status': 'RESPONSE_CAPTURED', 'response': payload()}, separators=(',', ':')) + '\n\n')
            reused = {path.name: {'root': 'origin', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
            calls = []
            def fetch(code, day):
                calls.append((code, day))
                return payload(code, day)
            out = base / 'out'
            m = capture_extension(base, out, reused, [['SH600312', DAY]], plan(1), fetch)
            self.assertTrue(m['complete_capture'])
            self.assertEqual((out / 'sessions' / path.name).read_bytes(), path.read_bytes())
            self.assertEqual(m['fresh_query_reservations'], 1)
            self.assertEqual(calls, [('SH600312', DAY)])
            with self.assertRaisesRegex(ValueError, 'preserve'):
                capture_extension(base, out, reused, [['SH600312', DAY]], plan(1), fetch)
            self.assertEqual(len(calls), 1)
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                capture_extension(base, base / 'new-attempt', reused, [['SH600312', DAY]], plan(1), fetch)
            self.assertFalse((base / 'new-attempt').exists())

    def test_three_source_failures_keep_all_responses_and_stop_with_pending_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fresh = [[f'SH600{i:03d}', DAY] for i in range(1, 5)]
            def fail(*args):
                raise OSError('synthetic source unavailable')
            out = base / 'out'
            m = capture_extension(base, out, {}, fresh, plan(4), fail)
            self.assertFalse(m['complete_capture'])
            self.assertTrue(m['stopped_after_consecutive_source_failures'])
            self.assertEqual(m['response_status_counts'], {'REQUEST_FAILED': 3})
            self.assertEqual(m['fresh_query_reservations'], 3)
            self.assertEqual(m['pending_fresh_requests'], [['SH600004', DAY]])
            self.assertEqual(len(list(out.rglob('response-1.json'))), 3)
            for f in (out / 'sessions').glob('*.json'):
                record = json.loads(f.read_text())
                verify_receipt(out, record['instrument'], DAY, record, '116.205.183.150:7709')

    def test_absolute247_budget_and_duplicate_identities_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for p, fresh in [(plan(248), [[f'SH600{i:03d}', DAY] for i in range(248)]),
                             (plan(True), [[CODE, DAY]]), (plan(2), [[CODE, DAY], [CODE, DAY]])]:
                with self.assertRaises(ValueError):
                    capture_extension(base, base / 'out', {}, fresh, p, lambda *x: self.fail('source called'))
                self.assertFalse((base / 'out').exists())

    def test_reconstructed_admission_rejects_bad_price_clock_or_capacity(self):
        daily = {'date': DAY, 'tradestatus': '1', 'isST': '0', 'low': '10', 'high': '10',
                 'close': '10', 'volume': '12000000'}
        packet = {'instrument': CODE, 'requested_day': DAY, 'status': 'RESPONSE_CAPTURED', 'response': payload()}
        r = inspect_packet(CODE, DAY, packet, daily)
        self.assertEqual(r['status'], 'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE')
        self.assertEqual(r['windows'], 48)
        for kind in ('clock', 'price', 'capacity', 'none_point', 'bad_clock_type'):
            altered = copy.deepcopy(packet)
            row = dict(daily)
            if kind == 'clock':
                altered['response']['points'][0]['time'] = DAY + 'T09:32:00+08:00'
            elif kind == 'price':
                altered['response']['points'][0].update(price_milli=10010, price=10.01)
            elif kind == 'capacity':
                row['volume'] = '100'
            elif kind == 'none_point':
                altered['response']['points'][0] = None
            else:
                altered['response']['points'][0]['time'] = True
            with self.subTest(kind=kind):
                try:
                    inspect_packet(CODE, DAY, altered, row)
                except ValueError:
                    pass
                except Exception as exc:
                    self.fail('malformed source escaped per-row rejection: ' + type(exc).__name__)
                else:
                    self.fail('invalid source accepted')
