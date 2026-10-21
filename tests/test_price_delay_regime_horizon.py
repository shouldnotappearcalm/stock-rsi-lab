import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import run_price_delay_regime_horizon as runner
from stock_rsi.calendar import TradingCalendar


class RegimeHorizonRunnerTests(unittest.TestCase):
    def fixture(self):
        return {'calendar': TradingCalendar(['2023-12-29', '2024-01-02']),
                'bars': {}, 'events': [], 'targets': {}, 'regime_evidence': {},
                'known_hashes': {}, 'old_codes': set(), 'boundary_codes': set()}

    def fake_simulator(self, calendar, bars, events, targets, cash, *, account_factory, **kwargs):
        account_factory(calendar, cash, events, tax_reserve_rate='.2')
        return {'days': [{'day': '2024-01-02', 'equity': Decimal(cash), 'exposure': Decimal('.95')}],
                'regime_audit': [], 'phase_audit': [], 'lifecycle_source_audit': [],
                'intents': [], 'fills': [], 'orders': [], 'ownership': {}, 'corporate_ledger': []}

    def test_fixed_plan_rejects_budgeted_allocator_permission_or_outcome_scope_changes(self):
        plan = copy.deepcopy(runner.PROFILE)
        for field, names in [('method_code_sha256', runner.METHOD_FILES),
                             ('public_evidence_sha256', runner.PUBLIC_FILES),
                             ('local_source_sha256', runner.LOCAL_FILES)]:
            plan[field] = dict.fromkeys(names, 'a' * 64)
        runner.require_plan(plan)
        for key, value in [('allocator', 'plan_budgeted_raw_targets'), ('candidate_budget', True),
                           ('risk_warning_buy_permission', True), ('extra_cost_bps', [20]),
                           ('window', ['2023-12-29', '2026-10-21']), ('investment_rule_changed', True),
                           ('all_profile_gates_before_any_returns', False), ('method_code_sha256', {})]:
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.require_plan(changed)

    def test_any_incomplete_case_or_failed_postcheck_prohibits_all_annual_scoring(self):
        for fail_case, fail_post in [(True, False), (False, True)]:
            inputs = self.fixture()
            simulator = Mock(side_effect=[ValueError('source refusal'), ValueError('source refusal')]) if fail_case else self.fake_simulator
            post = Mock(side_effect=ValueError('postcheck source changed')) if fail_post else Mock()
            scorer = Mock(side_effect=AssertionError('ROI must not run'))
            with self.subTest(fail_case=fail_case), tempfile.TemporaryDirectory() as tmp, patch.object(runner.old, 'write_case', return_value={}):
                results, check, scored, _ = runner.run_profiles(Path(tmp) / runner.OUTPUT, inputs,
                    check_sources=post, simulator=simulator, validator=lambda *a: {}, scorer=scorer)
                self.assertFalse(scored)
                if fail_case:
                    self.assertEqual(simulator.call_count, 2)
                scorer.assert_not_called()
                post.assert_called_once()
                self.assertTrue(all(r['portfolio_returns_computed'] is False for r in results.values()))
                self.assertEqual(check['completed'], not fail_post)

    def test_keyboard_interrupt_preserves_first_error_and_still_runs_both_postchecks(self):
        inputs = self.fixture()
        simulator = Mock(side_effect=KeyboardInterrupt('original interruption'))
        post = Mock(side_effect=ValueError('later source check failure'))
        scorer = Mock()
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'verify_hashes') as verify:
            out = Path(tmp) / runner.OUTPUT
            results, check, scored, interrupt = runner.run_profiles(out, inputs, check_sources=post,
                simulator=simulator, validator=lambda *a: {}, scorer=scorer)
            self.assertFalse(scored)
            self.assertEqual(interrupt['error_type'], 'KeyboardInterrupt')
            self.assertEqual(results['40']['status'], 'NOT_RUN_AFTER_INTERRUPTION')
            self.assertEqual(json.loads((out / 'first-error.json').read_text())['error_type'], 'KeyboardInterrupt')
            self.assertEqual(verify.call_count, 2)
            post.assert_called_once()
            scorer.assert_not_called()
            self.assertFalse(check['completed'])

    def test_only_two_complete_profiles_allow_scoring_and_second_score_failure_publishes_neither(self):
        results = {str(c): {'status': 'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED',
                           'portfolio_returns_computed': False} for c in (20, 40)}
        cases = {20: {'cost': 20}, 40: {'cost': 40}}
        first = copy.deepcopy(results)
        scorer = Mock(side_effect=[{'2026_test_marker': 1}, ValueError('second score invalid')])
        with self.assertRaises(ValueError):
            runner.finalize_returns(results, cases, True, scorer)
        self.assertEqual(results, first)
        scorer = Mock(side_effect=lambda case: {'test_cost': case['cost']})
        self.assertTrue(runner.finalize_returns(results, cases, True, scorer))
        self.assertEqual(scorer.call_count, 2)
        self.assertTrue(all(x['portfolio_returns_computed'] for x in results.values()))

    def test_error_record_or_terminal_write_failure_does_not_replace_original_interrupt(self):
        original_write, original_update = runner.write, runner.old.write_json
        for failed_name in ('first-error.json', 'case_results.json', 'input-postcheck.json'):
            def fail_selected(path, value):
                if Path(path).name == failed_name:
                    raise OSError('diagnostic unavailable')
                return original_write(path, value)
            def fail_selected_update(path, value):
                if Path(path).name == failed_name:
                    raise OSError('diagnostic unavailable')
                return original_update(path, value)
            with self.subTest(failed_name=failed_name), tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'write', side_effect=fail_selected), patch.object(runner.old, 'write_json', side_effect=fail_selected_update):
                scorer, post = Mock(), Mock()
                results, check, scored, interruption = runner.run_profiles(Path(tmp) / runner.OUTPUT,
                    self.fixture(), check_sources=post,
                    simulator=Mock(side_effect=KeyboardInterrupt('original simulation interruption')),
                    validator=lambda *a: {}, scorer=scorer)
                self.assertEqual(interruption['error_type'], 'KeyboardInterrupt')
                self.assertEqual(results['20']['error_type'], 'KeyboardInterrupt')
                self.assertEqual(results['40']['status'], 'NOT_RUN_AFTER_INTERRUPTION')
                self.assertFalse(scored)
                post.assert_called_once()
                scorer.assert_not_called()
                self.assertTrue(check['all_bound_inputs_unchanged'])
                self.assertTrue(check['persistence_errors'])

    def test_final_scored_result_write_failure_rolls_back_both_annual_payloads(self):
        original = runner.old.write_json
        writes = []
        def fail_final(path, value):
            if Path(path).name == 'case_results.json':
                writes.append(1)
                if len(writes) == 4:
                    raise OSError('scored result write unavailable')
            return original(path, value)
        scorer = Mock(return_value={'synthetic_annual_marker': 1})
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner.old, 'write_case', return_value={}), patch.object(runner.old, 'write_json', side_effect=fail_final):
            results, _, scored, interruption = runner.run_profiles(Path(tmp) / runner.OUTPUT, self.fixture(),
                check_sources=lambda: None, simulator=self.fake_simulator, validator=lambda *a: {}, scorer=scorer)
            self.assertEqual(scorer.call_count, 2)
            self.assertFalse(scored)
            self.assertEqual(interruption['error_type'], 'OSError')
            self.assertTrue(all(x['portfolio_returns_computed'] is False for x in results.values()))
            self.assertTrue(all('synthetic_annual_marker' not in x for x in results.values()))

    def test_source_view_keeps_original_issuer_and_only_declared_boundary_close_before2026(self):
        inputs = self.fixture()
        inputs.update(old_codes={'SH600001'}, boundary_codes={'SH600002'})
        bars = {c: {} for c in ('SH600001', 'SH600002', 'SH600003')}
        source, _ = runner.make_source_view(inputs)
        for day, expected in [('2025-12-30', {'SH600001'}),
                              ('2025-12-31', {'SH600001', 'SH600002'}),
                              ('2026-01-05', set(bars))]:
            with patch.object(runner, 'regime_source_rows_on', return_value=({}, [], {})) as guard:
                source(bars, __import__('datetime').date.fromisoformat(day), set(), {},
                       evidence={}, as_of=day + 'T15:05:00+08:00')
                self.assertEqual(set(guard.call_args.args[0]), expected)
        with patch.object(runner, 'regime_source_rows_on') as guard:
            with self.assertRaises(ValueError):
                source(bars, __import__('datetime').date(2025, 12, 30), {'SH600003'}, {},
                       evidence={}, as_of='2025-12-30T15:05:00+08:00')
            guard.assert_not_called()


if __name__ == '__main__':
    unittest.main()
