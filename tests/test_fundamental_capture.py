"""Synthetic responses test provenance boundaries before network capture."""
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

try:
    from scripts.capture_fundamental_pilot_pre2026 import (
        DAILY_FIELDS, PROFIT_FIELDS, QUARTERS, validate_daily, validate_profit, capture_sources,
    )
except ImportError:
    DAILY_FIELDS = PROFIT_FIELDS = QUARTERS = validate_daily = validate_profit = None


class FundamentalCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(validate_profit, 'fundamental pilot implementation missing')

    def daily(self, **changes):
        row = dict(zip(DAILY_FIELDS, ['2024-01-02', 'sh.600166', '10', '100', '1000', '.1',
                       '-10', '2', '1', '-8', '1', '0', '3']))
        row.update(changes)
        return [row[k] for k in DAILY_FIELDS]

    def profit(self, **changes):
        row = dict(zip(PROFIT_FIELDS, ['sh.600166', '2024-04-20', '2023-12-31', '.1', '.2',
                       '.3', '-100000000', '-.25', '1000000000', '400000000', '300000000']))
        row.update(changes)
        return [row[k] for k in PROFIT_FIELDS]

    def test_negative_earnings_and_units_are_preserved_not_silently_scaled(self):
        d = validate_daily('SH600166', DAILY_FIELDS, [self.daily()], ['2024-01-02'])
        self.assertEqual(d[0]['peTTM'], '-10')
        p, quarantine = validate_profit('SH600166', 2023, 4, PROFIT_FIELDS, [self.profit()])
        self.assertEqual(p[0]['netProfit'], '-100000000')
        self.assertEqual(p[0]['totalShare'], '400000000')
        self.assertFalse(quarantine)

    def test_later_publication_is_quarantined_not_backdated_to_statdate(self):
        accepted, quarantine = validate_profit('SH600166', 2023, 4, PROFIT_FIELDS,
                                              [self.profit(pubDate='2026-01-05')])
        self.assertFalse(accepted)
        self.assertEqual(quarantine[0]['reason'], 'PUBLICATION_AFTER_DEVELOPMENT_CUTOFF')
        with self.assertRaises(ValueError):
            validate_profit('SH600166', 2025, 4, PROFIT_FIELDS, [])
        self.assertNotIn((2025, 4), QUARTERS)

    def test_schema_identity_date_and_nonfinite_values_fail_closed(self):
        for row in [self.daily(code='sz.000825'), self.daily(date='2026-01-05'),
                    self.daily(peTTM='NaN'), self.daily(volume='-1')]:
            with self.assertRaises(ValueError): validate_daily('SH600166', DAILY_FIELDS, [row], ['2024-01-02'])
        with self.assertRaises(ValueError): validate_daily('SH600166', DAILY_FIELDS, [], ['2024-01-02'])
        with self.assertRaises(ValueError):
            validate_profit('SH600166', 2023, 4, PROFIT_FIELDS, [self.profit(statDate='2023-09-30')])
        with self.assertRaises(ValueError):
            validate_profit('SH600166', 2023, 4, PROFIT_FIELDS, [self.profit(), self.profit()])

    def test_unregistered_existing_packet_fails_before_any_network_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'codes').mkdir()
            (root/'progress.json').write_text('{}')
            packet = root/'codes/SH600166.json'; packet.write_text('{"raw":"original"}')
            before = packet.read_bytes()
            with patch('scripts.capture_fundamental_pilot_pre2026.socket.setdefaulttimeout') as network:
                with self.assertRaisesRegex(ValueError, 'unregistered existing source packet'):
                    capture_sources(root, ['SH600166'], [], {}, 'request')
                network.assert_not_called()
            self.assertEqual(packet.read_bytes(), before)
            self.assertEqual(json.loads((root/'progress.json').read_text()), {})
