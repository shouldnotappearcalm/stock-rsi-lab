import importlib
import importlib.util
import unittest


class ClockBoundaryTests(unittest.TestCase):
    def helper(self):
        name = 'scripts.prepare_price_delay_clock_pre2026'
        if importlib.util.find_spec(name) is None:
            self.fail('separate clock-boundary preparation has not been implemented')
        return importlib.import_module(name).clock_calendar

    def test_uses_actual_first_next_session_not_weekday_or_holiday(self):
        build = self.helper()
        capped = '2025-12-30\n2025-12-31\n'
        source = capped+'2026-01-05\n2026-01-06\n'
        self.assertEqual(build(capped, source), capped+'2026-01-05\n')

    def test_missing_boundary_or_different_prefix_fails(self):
        build = self.helper()
        capped = '2025-12-30\n2025-12-31\n'
        for source in (capped, '2025-12-29\n2025-12-31\n2026-01-05\n',
                       capped+'2025-12-31\n2026-01-05\n'):
            with self.assertRaises(ValueError): build(capped, source)

    def test_later_calendar_changes_cannot_change_boundary(self):
        build = self.helper()
        capped = '2025-12-31\n'
        self.assertEqual(build(capped, capped+'2026-01-05\n2026-01-06\n'),
                         build(capped, capped+'2026-01-05\n2026-12-31\n'))

    def test_noncanonical_or_wrong_cap_fails(self):
        build = self.helper()
        for capped in ('2025-12-30\n', '2025-12-31', '2025-12-31\n\n'):
            with self.assertRaises(ValueError): build(capped, '2025-12-31\n2026-01-05\n')
