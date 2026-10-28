import csv
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from scripts.published_replay_float_comparison import compare_original, ulps


class FloatReplayTests(unittest.TestCase):
    def fixture(self, root, nav=1000000., quantity='100'):
        root.mkdir()
        for name, data in [('days.csv', [{'session': '2025-12-31', 'account_value': str(nav), 'cash': '50000'}]),
                           ('orders.csv', [{'session': '2025-12-31', 'quantity': quantity}]),
                           ('holdings.csv', [{'session': '2025-12-31', 'weight': '.95', 'quantity': '100'}])]:
            with (root / name).open('w') as f:
                w = csv.DictWriter(f, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
        row = {'execution_session': '2025-12-31', 'equity_at_decision': nav, 'orders': [{'quantity': 100}], 'histories': {'A': [['2025-12-30', 10]]}}
        raw = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        row['snapshot_sha256'] = hashlib.sha256(raw).hexdigest()
        (root / 'decision_intents.json').write_text(json.dumps([row]))

    def test_one_ulp_nav_reordering_does_not_change_orders_or_history(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / 'a', Path(t) / 'b'; self.fixture(a); self.fixture(b, math.nextafter(1000000., math.inf))
            result = compare_original(a, b)
            self.assertEqual(result['max_ulp_distance'], 1); self.assertTrue(result['all_orders_and_market_history_exact'])

    def test_nine_ulps_are_rejected_and_eight_is_an_absolute_machine_bound(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / 'a', Path(t) / 'b'; self.fixture(a); n = 1000000.
            for _ in range(9): n = math.nextafter(n, math.inf)
            self.assertEqual(ulps(n, 1000000.), 9); self.fixture(b, n)
            with self.assertRaisesRegex(ValueError, 'roundoff'): compare_original(a, b)

    def test_even_one_share_change_is_not_a_float_exception(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / 'a', Path(t) / 'b'; self.fixture(a); self.fixture(b, quantity='101')
            with self.assertRaisesRegex(ValueError, 'non-roundoff'): compare_original(a, b)

    def test_replay_snapshot_forgery_is_rejected_even_with_tiny_nav_change(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / 'a', Path(t) / 'b'; self.fixture(a); self.fixture(b)
            rows = json.loads((b / 'decision_intents.json').read_text()); rows[0]['histories']['A'][0][1] = 11
            (b / 'decision_intents.json').write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, 'authenticate'): compare_original(a, b)
