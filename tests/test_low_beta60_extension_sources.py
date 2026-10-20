import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS

try:
    from scripts.low_beta60_extension_sources import assemble_packet, fetch_packet, capture_packets
except ImportError:
    assemble_packet = fetch_packet = capture_packets = None


SESSIONS = ['2023-12-29', '2025-12-31', '2026-01-05', '2026-10-13']


def packet(code, days):
    rows = [{'date': d, 'code': code[:2].lower() + '.' + code[2:], 'open': '10.0000',
             'high': '10.0000', 'low': '10.0000', 'close': '10.0000', 'preclose': '10.0000',
             'volume': '1000000', 'amount': '10000000', 'adjustflag': '3', 'tradestatus': '1', 'isST': '0'}
            for d in days]
    return {'instrument': code, 'window': [days[0], days[-1]], 'bars': rows,
            'distributions': [], 'adjustments': [], 'quarantine': []}


def vendor_envelope(fields, rows):
    return ['provider_response'], [{'initial_error_code': '0', 'initial_error_msg': '', 'fields': list(fields),
            'rows': rows, 'iteration_error_type': None, 'iteration_error': None,
            'final_error_code': '0', 'final_error_msg': ''}]


class ExtensionRawSourcesTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(assemble_packet, 'raw-source extension missing')

    def test_assembled_cache_preserves_exact_old_rows_and_clips_later_bytes(self):
        code = 'SH600153'
        old = packet(code, SESSIONS[:2])
        src = packet(code, SESSIONS + ['2026-10-14'])
        before = copy.deepcopy(old)
        result = assemble_packet(code, src, old, SESSIONS)
        self.assertEqual(result['bars'][:2], old['bars'])
        self.assertEqual(result['bars'][2:], src['bars'][2:4])
        self.assertEqual(result['window'], ['2023-12-29', '2026-10-13'])
        self.assertEqual(old, before)
        self.assertEqual(len(src['bars']), 5)

    def test_changed_old_cache_or_incomplete_calendar_is_not_silently_repaired(self):
        code = 'SH600153'
        old = packet(code, SESSIONS[:2])
        for kind in ('old_price', 'old_distribution', 'missing2026', 'outside_calendar'):
            src = packet(code, SESSIONS)
            if kind == 'old_price':
                src['bars'][0]['close'] = '9.00'
                src['bars'][0]['low'] = '9.00'
            elif kind == 'old_distribution':
                src['distributions'] = [{'dividOperateDate': '2025-03-05'}]
            elif kind == 'missing2026':
                src['bars'].pop()
            else:
                src['bars'].insert(3, {**src['bars'][2], 'date': '2026-01-06'})
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                assemble_packet(code, src, old, SESSIONS)

    def test_successful_capture_queries_only_missing_intervals_and_never_resumes(self):
        oldcode, newcode, cachecode = 'SH600153', 'SH601808', 'SZ000001'
        originals = {oldcode: packet(oldcode, SESSIONS[:2]), cachecode: packet(cachecode, SESSIONS[:2])}
        cached = {cachecode: packet(cachecode, SESSIONS)}
        calls = []

        def fetch(code, component, parameters):
            calls.append((code, component, parameters))
            if component == 'daily':
                days = SESSIONS[2:] if code == oldcode else SESSIONS
                raw = packet(code, days)['bars']
                return vendor_envelope(BAR_FIELDS, [[r[k] for k in BAR_FIELDS] for r in raw])
            return vendor_envelope(DIVIDEND_FIELDS if component.startswith('dividend') else ADJUST_FIELDS, [])

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'capture'
            manifest = capture_packets(out, [oldcode, newcode, cachecode], SESSIONS, originals, cached, 'a' * 64, fetch)
            self.assertEqual(manifest['names'], 3)
            self.assertEqual(manifest['query_reservations_consumed'], 8)
            self.assertEqual(len(calls), 8)
            self.assertFalse(any(c == cachecode for c, _, _ in calls))
            oldcalls = [(kind, params) for c, kind, params in calls if c == oldcode]
            self.assertEqual([kind for kind, _ in oldcalls], ['daily', 'dividend2026', 'adjustments'])
            self.assertEqual(oldcalls[0][1], {'start_date': '2026-01-01', 'end_date': '2026-10-13',
                                            'frequency': 'd', 'adjustflag': '3'})
            self.assertEqual([kind for c, kind, _ in calls if c == newcode],
                             ['daily', 'dividend2024', 'dividend2025', 'dividend2026', 'adjustments'])
            for code in originals:
                saved = json.loads((out / 'codes' / (code + '.json')).read_text())
                self.assertEqual(saved['bars'][:2], originals[code]['bars'])
            with self.assertRaisesRegex(ValueError, 'preserve'):
                capture_packets(out, [oldcode, newcode, cachecode], SESSIONS, originals, cached, 'a' * 64, fetch)
            self.assertEqual(len(calls), 8)

    def test_three_failed_sources_preserve_journal_errors_pending_and_budget(self):
        def failure(*args):
            raise OSError('synthetic source failure')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'capture'
            codes = ['SH600001', 'SH600002', 'SH600003', 'SH600004']
            manifest = capture_packets(out, codes, SESSIONS, {}, {}, 'a' * 64, failure)
            self.assertEqual(manifest['names'], 0)
            self.assertEqual(manifest['pending_codes'], ['SH600004'])
            self.assertEqual(set(manifest['errors_sha256']), set(codes[:3]))
            self.assertEqual(manifest['query_reservations_consumed'], 3)
            self.assertEqual(len(list(out.rglob('response-1.json'))), 3)
            self.assertTrue((out / 'stopped.json').exists())
            self.assertFalse(manifest['admitted_for_account_replay'])
            self.assertFalse(manifest['portfolio_returns_computed'])

    def test_oversized_budget_rejected_before_output_or_source_access(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'capture'
            with self.assertRaisesRegex(ValueError, '76'):
                capture_packets(out, [f'SH600{i:03d}' for i in range(16)], SESSIONS, {}, {}, 'a' * 64,
                                lambda *args: self.fail('source called before budget check'))
            self.assertFalse(out.exists())
