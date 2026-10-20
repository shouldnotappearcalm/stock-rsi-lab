"""Catch calendar expansion changing the frozen method or reading past formation."""
import json
import unittest
from datetime import date

from stock_rsi.low_beta60 import build_targets as original_targets

try:
    from stock_rsi.low_beta60_extension import build_targets, extend_targets
except ImportError:
    build_targets = extend_targets = None


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


class Source:
    def __init__(self):
        ends = [date(2018, 12, 28)] + [date(y, m, 28) for y in range(2019, 2026) for m in range(1, 13)]
        firsts = [date(y, m, 2) for y in (2024, 2025) for m in range(1, 13)]
        self.calendar = tuple(sorted(ends + firsts + [date(2026, 1, 5), date(2026, 2, 2)]))
        self.calls = []

    def value(self, code, field, day):
        self.calls.append(day)
        if day > '2025-12-28':
            raise AssertionError('execution-session or post-formation data read')
        if field in ('volume', 'factor'):
            return 1.
        d = date.fromisoformat(day)
        n = (d.year - 2018) * 12 + d.month - 12
        slope = 1. if code == 'SH000905' else (int(code[-3:]) + 1) / 100
        p = 100.
        for i in range(n):
            p *= 1 + .001 + slope * (-.02, 0., .02)[i % 3]
        return p


MEMBERS = {f'SH600{i:03d}': [('2010-01-01', '2026-12-31')] for i in range(200)}


class LowBeta60ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_targets, 'bounded extension not implemented')
        self.assertIsNotNone(extend_targets, 'prefix gate not implemented')

    def test_expansion_preserves_all_prior_targets_and_signed_beta_selection(self):
        source = Source()
        old_targets, old_receipts = original_targets(source, MEMBERS)
        targets, receipts = extend_targets(source, MEMBERS, encoded(old_targets), encoded(old_receipts),
                                           end='2026-01-05', permitted_end='2026-01-05')
        self.assertEqual(len(receipts), 25)
        self.assertEqual(receipts[-1]['formation_asof'], '2025-12-28')
        self.assertEqual(receipts[-1]['latest_factor_price_read'], '2025-12-28')
        self.assertEqual(receipts[-1]['return_months'][0], '2021-01')
        self.assertEqual(receipts[-1]['return_months'][-1], '2025-12')
        self.assertEqual(list(targets['low_beta60']['2026-01-05']['weights']),
                         [f'SH600{i:03d}' for i in range(20)])
        self.assertAlmostEqual(sum(targets['low_beta60']['2026-01-05']['weights'].values()), .95)
        self.assertEqual(encoded(receipts[:24]), encoded(old_receipts))
        for family in old_targets:
            self.assertEqual(encoded({k: v for k, v in targets[family].items() if k < '2026'}),
                             encoded(old_targets[family]))
        self.assertLessEqual(max(source.calls), '2025-12-28')

    def test_changed_pre2026_evidence_stops_before_any2026_extension(self):
        source = Source()
        old_targets, old_receipts = original_targets(source, MEMBERS)
        valid = encoded(old_targets), encoded(old_receipts)
        for corrupted in ((valid[0] + b' ', valid[1]), (valid[0], valid[1] + b' ')):
            with self.subTest(corrupted_target=corrupted[0] != valid[0]):
                source.calls.clear()
                with self.assertRaisesRegex(ValueError, 'pre2026.*bytes'):
                    extend_targets(source, MEMBERS, *corrupted,
                                   end='2026-01-05', permitted_end='2026-01-05')
                self.assertTrue(source.calls)
                self.assertLessEqual(max(source.calls), '2025-11-28')

    def test_missing_or_exceeded_explicit_cap_is_rejected_before_price_reads(self):
        source = Source()
        with self.assertRaises(TypeError):
            build_targets(source, MEMBERS, end='2026-01-05')
        for start, end, cap in [('2024-01-02', '2026-02-02', '2026-01-05'),
                                ('2023-12-28', '2026-01-05', '2026-01-05'),
                                ('2026-01-05', '2025-12-31', '2026-01-05'),
                                ('2024-01-02', '2026-1-5', '2026-01-05')]:
            with self.subTest(start=start, end=end, cap=cap):
                with self.assertRaises(ValueError):
                    build_targets(source, MEMBERS, start=start, end=end, permitted_end=cap)
        self.assertEqual(source.calls, [])
