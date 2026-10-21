import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.capture_price_delay_raw_pre2026 import load_clipped_reuse


class PriceDelayRawSourceTests(unittest.TestCase):
    def packet(self):
        bar = {'date': '2025-12-31', 'code': 'sh.600000', 'open': '10', 'high': '11',
               'low': '9', 'close': '10', 'preclose': '10', 'volume': '1000',
               'amount': '10000', 'adjustflag': '3', 'tradestatus': '1', 'isST': '0'}
        return dict(instrument='SH600000', window=['2023-12-29', '2025-12-31'],
                    bars=[bar], distributions=[], adjustments=[], quarantine=[])

    def load(self, packet, digest=None):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/'source.json'; path.write_text(json.dumps(packet))
            before = path.read_bytes()
            result = load_clipped_reuse(path, 'SH600000', digest or hashlib.sha256(before).hexdigest(),
                                        ['2025-12-31'], 'pre2026-fixture')
            self.assertEqual(path.read_bytes(), before)
            return result

    def test_future_bar_in_pre2026_labeled_packet_is_rejected_not_silently_clipped(self):
        packet = self.packet()
        packet['bars'].append(packet['bars'][0] | {'date': '2026-01-05'})
        with self.assertRaises(ValueError): self.load(packet)

    def test_authentic_pre2026_packet_preserves_core_and_source(self):
        packet = self.packet(); saved, diagnostic = self.load(packet)
        self.assertEqual(saved['bars'], packet['bars'])
        self.assertTrue(diagnostic['full_explicit_calendar_covered'])
        self.assertFalse(saved['provenance']['source_contains_later_bytes'])

    def test_future_window_wrong_identity_or_hash_is_rejected(self):
        for change in ({'window': ['2023-12-29', '2026-10-20']}, {'instrument': 'SH600001'}):
            with self.assertRaises(ValueError): self.load(self.packet() | change)
        with self.assertRaises(ValueError): self.load(self.packet(), digest='0'*64)
