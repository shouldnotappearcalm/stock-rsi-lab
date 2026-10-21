import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import prepare_price_delay_ordinary_scope_pre2026 as scope
from scripts.fundamental_query_journal import file_sha


class PriceDelayOrdinarySourceScopeTests(unittest.TestCase):
    def test_plan_cannot_expand_window_scope_or_omit_anchors(self):
        p = dict(scope.PROFILE)
        for field, names in scope.BINDINGS:
            p[field] = dict.fromkeys(names, 'a' * 64)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            out = base / scope.OUTPUT
            scope.validate_plan(p, base, out)
            for field, value in [('window', ['2024-01-02', '2026-01-01']),
                                 ('ordinary_packets', 2491), ('rejected_packets', 11),
                                 ('nonordinary_daily_intervals', 240),
                                 ('account_dependency_guard_required', False),
                                 ('new_2026_values_read', True), ('network_calls_permitted', 1),
                                 ('output_relative', '../escape')]:
                changed = copy.deepcopy(p)
                changed[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    scope.validate_plan(changed, base, out)
            for field, _ in scope.BINDINGS:
                changed = copy.deepcopy(p)
                changed[field] = {}
                with self.subTest(field=field), self.assertRaises(ValueError):
                    scope.validate_plan(changed, base, out)
            with self.assertRaises(ValueError):
                scope.validate_plan(p, base, base / 'wrong')

    def test_rejected_ST_packet_never_enters_tape_index(self):
        with tempfile.TemporaryDirectory() as d:
            capture = Path(d)
            (capture / 'plan.json').write_text('{}')
            hashes = {'SZ000001-2024-06-03.json': 'a' * 64,
                      'SZ002092-2024-06-03.json': 'b' * 64}
            (capture / 'manifest.json').write_text(json.dumps({
                'complete_capture': True, 'plan_sha256': file_sha(capture / 'plan.json'),
                'per_session_sha256': hashes,
            }))
            bars = {'SZ000001': {'2024-06-03': {'isST': '0'}},
                    'SZ002092': {'2024-06-03': {'isST': '1'}}}
            source = {'ordinary_packet_sha256': {list(hashes)[0]: 'a' * 64},
                      'rejected_packet_sha256': {list(hashes)[1]: 'b' * 64}}
            bank = scope.OrdinaryScopeTapeBank(capture, bars, source)
            self.assertEqual(set(bank.index), {('SZ000001', '2024-06-03')})
            with self.assertRaises(ValueError):
                bank('SZ002092', date(2024, 6, 3))
            self.assertEqual(bank.accessed, set())
            changed = copy.deepcopy(source)
            changed['ordinary_packet_sha256'].update(changed['rejected_packet_sha256'])
            changed['rejected_packet_sha256'] = {}
            with self.assertRaises(ValueError):
                scope.OrdinaryScopeTapeBank(capture, bars, changed)
            changed = copy.deepcopy(source)
            changed['rejected_packet_sha256'] = {}
            with self.assertRaises(ValueError):
                scope.OrdinaryScopeTapeBank(capture, bars, changed)


if __name__ == '__main__':
    unittest.main()
