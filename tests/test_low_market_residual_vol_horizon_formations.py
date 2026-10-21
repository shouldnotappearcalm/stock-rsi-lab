import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_low_market_residual_vol_horizon_formations as runner


class HorizonAdmissionTests(unittest.TestCase):
    def test_unchanged_contract_rejects_skip_carry_parameter_horizon_and_boolean_budget(self):
        plan = copy.deepcopy(runner.PROFILE)
        for field, names in runner.BINDINGS:
            plan[field] = dict.fromkeys(names, 'a' * 64)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runner.validate_contract(plan, base, base / runner.OUTPUT)
            for key, value in [('candidate_budget', True), ('minimum_return_observations', 14),
                               ('on_inadmissible_month', 'CARRY'), ('window', ['2024-01-02', '2026-10-21']),
                               ('investment_rule_changes_permitted', True), ('controls_selectable', True),
                               ('portfolio_returns_to_compute', True), ('method_code_sha256', {})]:
                changed = copy.deepcopy(plan)
                changed[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    runner.validate_contract(changed, base, base / runner.OUTPUT)

    def test_complete_short_month_is_denied_without_any_quote_or_factor_call(self):
        # Explicit synthetic exchange table: no weekday calendar synthesis.
        days = [date(2025, 12, 31)] + [date(2026, 1, d) for d in range(5, 20)]
        days += [date(2026, 2, 2)]
        clock = runner.clock_admission(days, start='2026-02-02', end='2026-02-02')
        self.assertTrue(clock[0]['admitted'])
        short = [date(2025, 12, 31)] + [date(2026, 1, d) for d in range(5, 19)] + [date(2026, 2, 2)]
        denied = runner.clock_admission(short, start='2026-02-02', end='2026-02-02')
        self.assertEqual(denied[0]['n'], 14)
        self.assertFalse(denied[0]['admitted'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'QlibSnapshot', side_effect=AssertionError('future quote decoding')), patch.object(runner, 'build_targets', side_effect=AssertionError('factor called')):
            status, formed = runner.run_formations(Path('/unused'), {}, denied, Path(tmp))
            self.assertEqual(status, 2)
            self.assertIsNone(formed)
            saved = json.loads((Path(tmp) / 'failure.json').read_text())
            self.assertFalse(saved['new_2026_quote_values_decoded'])
            self.assertFalse(saved['portfolio_returns_computed'])
            self.assertFalse((Path(tmp) / 'targets.json').exists())

    def test_baseline_and_complete_preceding_month_are_required(self):
        january = [date(2026, 1, d) for d in range(5, 20)]
        missing_baseline = runner.clock_admission(january + [date(2026, 2, 2)], start='2026-02-02', end='2026-02-02')
        self.assertEqual(missing_baseline[0]['reason'], 'missing_preceding_month_baseline_close')
        missing_month = runner.clock_admission([date(2025, 12, 31), date(2026, 2, 2)], start='2026-02-02', end='2026-02-02')
        self.assertEqual(missing_month[0]['reason'], 'missing_preceding_complete_natural_month')
        for days in ([date(2026, 1, 5)] * 2, [date(2026, 1, 6), date(2026, 1, 5)]):
            with self.assertRaises(ValueError):
                runner.clock_admission(days)

    def test_original_formations_cannot_be_replaced_by_new_year(self):
        old = {runner.FAMILIES[0]: {'2024-01-02': {'weights': {'SZ000001': .95}}}}
        full = copy.deepcopy(old)
        full[runner.FAMILIES[0]]['2026-01-05'] = {'weights': {'SH600001': .95}}
        receipts = [{'execution_session': '2024-01-02', 'n': 20}]
        runner.require_original_prefix(full, receipts + [{'execution_session': '2026-01-05'}], old, receipts)
        full[runner.FAMILIES[0]]['2024-01-02']['weights']['SZ000001'] = .94
        with self.assertRaises(ValueError):
            runner.require_original_prefix(full, receipts, old, receipts)

    def test_interrupt_still_checks_all_sources_and_preserves_first_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            request = base / 'plan.json'
            request.write_text('{}')
            out = base / runner.OUTPUT
            clock = [{'admitted': False}]
            initial = {'/old/financial.json': 'a' * 64}
            args = ['--source-root', str(base), '--plan', str(request),
                    '--expected-plan-sha256', runner.sha(request), '--output-dir', str(out)]
            for post_fails in (False, True):
                if out.exists():
                    import shutil
                    shutil.rmtree(out)
                original = KeyboardInterrupt('original interruption')
                source_error = ValueError('source changed')
                effects = [(base / 'provider', {}, clock, dict(initial))]
                effects += [source_error if post_fails else (base / 'provider', {}, clock, dict(initial))]
                with self.subTest(post_fails=post_fails), patch.object(runner, 'load_inputs', side_effect=effects) as auth, patch.object(runner, 'run_formations', side_effect=original), patch.object(runner.development, 'verify_inputs') as verify:
                    with self.assertRaises(KeyboardInterrupt) as caught:
                        runner.main(args)
                    self.assertIs(caught.exception, original)
                    self.assertEqual(auth.call_count, 2)
                    verify.assert_called_once()
                terminal = json.loads((out / 'terminal-error.json').read_text())
                self.assertEqual(terminal['error_type'], 'KeyboardInterrupt')
                post = terminal['source_postcheck_after_original_error']
                self.assertEqual(post['completed'], not post_fails)
                self.assertTrue(post['all_bound_inputs_unchanged'])
                self.assertFalse((out / 'summary.json').exists())
                self.assertFalse(terminal['portfolio_returns_computed'])


if __name__ == '__main__':
    unittest.main()
