import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS
from scripts.fundamental_query_journal import file_sha
try:
    from scripts.capture_low_beta60_raw_pre2026 import load_clipped_reuse
except ImportError:
    load_clipped_reuse = None


def packet():
    bars = [dict(zip(BAR_FIELDS, [d, 'sh.600001', '10', '11', '9', '10', '10',
                                '10000', '100000', '3', '1', '0']))
            for d in ('2023-12-29', '2024-01-02', '2026-01-05')]
    distributions = []
    for d in ('2024-07-01', '2026-07-01'):
        row = dict.fromkeys(DIVIDEND_FIELDS, '')
        row.update(code='sh.600001', dividOperateDate=d, dividCashPsBeforeTax='0.1',
                   dividStocksPs='0', dividReserveToStockPs='0')
        distributions.append(row)
    return {'instrument': 'SH600001', 'window': ['2023-12-29', '2026-10-16'],
            'bars': bars, 'distributions': distributions, 'adjustments': [], 'quarantine': [],
            'provenance': {'kind': 'ORIGINAL', 'original_sha256': 'parent-hash'},
            'source_query_receipts': {'daily': {'response_sha256': 'ancestor-response'}}}


class LowBeta60SourceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(load_clipped_reuse)

    def test_clip_excludes_future_records_preserves_original_and_nested_lineage(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'source.json'; path.write_text(json.dumps(packet()))
            before = path.read_bytes(); expected = file_sha(path)
            result, diagnostic = load_clipped_reuse(path, 'SH600001', expected,
                ['2023-12-29', '2024-01-02'], 'frozen-source')
            self.assertEqual([r['date'] for r in result['bars']], ['2023-12-29', '2024-01-02'])
            self.assertEqual([r['dividOperateDate'] for r in result['distributions']], ['2024-07-01'])
            self.assertEqual(result['window'], ['2023-12-29', '2025-12-31'])
            lineage = result['provenance']
            self.assertEqual(lineage['original_sha256'], expected)
            self.assertEqual(lineage['original_source_directory'], 'frozen-source')
            self.assertEqual(lineage['original_provenance']['original_sha256'], 'parent-hash')
            self.assertEqual(lineage['original_source_query_receipts']['daily']['response_sha256'], 'ancestor-response')
            self.assertTrue(lineage['source_contains_later_bytes'])
            self.assertFalse(lineage['historical_arrival_verified'])
            self.assertTrue(diagnostic['full_explicit_calendar_covered'])
            self.assertEqual(path.read_bytes(), before)

    def test_changed_original_hash_or_instrument_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'source.json'; path.write_text(json.dumps(packet()))
            old = file_sha(path); data = packet(); data['bars'][0]['close'] = '10.5'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_clipped_reuse(path, 'SH600001', old, ['2023-12-29'], 'source')
            with self.assertRaisesRegex(ValueError, 'identity'):
                load_clipped_reuse(path, 'SH600002', file_sha(path), ['2023-12-29'], 'source')

    def test_missing_sessions_remain_visible_and_no_source_rows_are_synthesized(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'source.json'; data = copy.deepcopy(packet()); data['bars'] = data['bars'][:1]
            path.write_text(json.dumps(data))
            result, diagnostic = load_clipped_reuse(path, 'SH600001', file_sha(path),
                ['2023-12-29', '2024-01-02'], 'source')
            self.assertEqual(len(result['bars']), 1)
            self.assertEqual(diagnostic['missing_sessions'], ['2024-01-02'])
            self.assertFalse(diagnostic['missing_sessions_classified_as_prelisting'])
            self.assertEqual(diagnostic['synthetic_source_rows_created'], 0)
