import copy
from datetime import date
from decimal import Decimal as D
from functools import partial
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_illiquidity_source_scenario_development as replay
from scripts.replay_stock_distribution_targets import simulate_fixed_targets
from scripts.tdx_history_checks import minute_labels
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.intraday_tape import aggregate_minutes
from stock_rsi.stock_distribution_account import StockDistribution, StockDistributionAccount


class FailureCaptureTests(unittest.TestCase):
    def setUp(self):
        self.calendar = TradingCalendar(['2024-04-30', '2024-05-06', '2024-05-07', '2024-05-08', '2024-05-09'])
        self.bars = {'A': {str(day): {'date': str(day), 'tradestatus': '1', 'isST': '0',
                     'open': '14.10', 'close': '14.10', 'preclose': '14.10', 'volume': '1000000'}
                           for day in self.calendar.days}}
        self.targets = {'2024-05-06': {'as_of': '2024-04-30', 'weights': {'A': '.95'}}}
        self.accessed = set()
        class Access:
            pass
        self.bank = Access()
        self.bank.accessed = self.accessed
        self.accounts = []

    def tape(self, code, day):
        self.accessed.add((code, str(day)))
        points = [{'time': str(day) + 'T' + label + ':00+08:00', 'volume': 10000, 'price_milli': 14100}
                  for label in minute_labels()]
        return aggregate_minutes(code, day, points)

    def factory(self, calendar, cash, events, **kwargs):
        account = StockDistributionAccount(calendar, cash, events,
            broker_factory=partial(IntradayBroker, participation_bps=500, extra_cost_bps=40,
                                   tape_provider=self.tape), **kwargs)
        self.accounts.append(account)
        return account

    def caught(self, events=(), lifecycles=None):
        try:
            simulate_fixed_targets(self.calendar, self.bars, events, self.targets, '20000',
                lifecycles={} if lifecycles is None else lifecycles, account_factory=self.factory)
        except ValueError as exc:
            self.error = exc
            return replay.failure_context(exc, self.accounts[0], self.bank)
        self.fail('fixture should have failed')

    def test_fractional_guard_preserves_exact_prefix_and_unmutated_failure_day(self):
        event = StockDistribution('e', 'A', date(2024, 4, 29), date(2024, 5, 7), date(2024, 5, 8),
                                  date(2024, 5, 8), date(2024, 5, 9), D('.1'), D('.333'), True)
        state, case, trace = self.caught([event])
        self.assertIn('fractional corporate entitlement', trace['error'])
        self.assertEqual(trace['attempted_day'], '2024-05-08')
        self.assertEqual(trace['last_completed_day'], '2024-05-07')
        self.assertEqual(state['last_account_clock'], ['2024-05-07', 1])
        self.assertEqual(state['entitlements'], {'e': 1300})
        self.assertEqual(len(case['days']), 3)
        self.assertEqual(len(case['intents']), 1)
        self.assertEqual(case['ownership']['2024-05-07'], {'A': 1300})
        self.assertFalse(any(r['day'] == '2024-05-08' for r in state['corporate_ledger']))
        self.assertFalse(trace['complete_simulation_returned'])
        self.assertIn('account.start_day(day)', trace['frame_context']['original_replay_source_line'])

    def test_lifecycle_failure_before_account_start_has_actual_attempted_day(self):
        proof = {'A': {'kind': 'DELISTING_END', 'effective_date': '2024-05-08',
                      'verified_primary_boundary': True, 'primary_document_sha256': 'a' * 64}}
        state, case, trace = self.caught(lifecycles=proof)
        self.assertEqual(trace['attempted_day'], '2024-05-08')
        self.assertEqual(trace['last_completed_day'], '2024-05-07')
        self.assertEqual(state['last_account_clock'], ['2024-05-07', 1])
        self.assertEqual(state['owned_shares'], {'A': 1300})
        self.assertIn('source_rows_on', trace['frame_context']['original_replay_source_line'])
        self.assertNotIn('2024-05-08', case['ownership'])

    def test_broker_source_error_preserves_start_phase_and_prior_visible_intent(self):
        def unavailable(code, day):
            self.accessed.add((code, str(day)))
            raise ValueError('synthetic unavailable minute tape')
        self.tape = unavailable
        state, case, trace = self.caught()
        self.assertEqual(trace['attempted_day'], '2024-05-06')
        self.assertEqual(state['last_account_clock'], ['2024-05-06', 0])
        self.assertEqual(trace['last_completed_day'], '2024-04-30')
        self.assertEqual(len(case['intents']), 1)
        self.assertEqual(len(state['fills']), 0)
        self.assertEqual(trace['tape_accessed_pairs'], [['A', '2024-05-06']])


class FrozenDevelopmentPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method = self.root / 'method.py'
        self.method.write_text('frozen method\n')
        self.raw = self.root / 'raw.json'
        self.raw.write_text('frozen source\n')
        self.paths = {'repo/method.py': self.method, 'source/raw.json': self.raw}
        self.plan = {'status': replay.STATUS, 'strategy': 'amihud22', 'phase': 'dev', 'end': '2025-12-31',
            'participation_bps': list(replay.PARTICIPATION), 'extra_bps': list(replay.EXTRA_BPS),
            'capitals': list(replay.CAPITALS), 'profiles': list(replay.PROFILES),
            'source_contract': replay.source.CONTRACT, 'source_scenario_dir': replay.SOURCE_DIR,
            'source_request_sha256': replay.SOURCE_REQUEST_SHA, 'original_source_admission_overridden': False,
            'conditional_engineering_only': True, '2026_evaluation_permitted': False,
            'method_code_sha256': {'method.py': replay.file_sha(self.method)},
            'input_sha256': {n: replay.file_sha(p) for n, p in self.paths.items()}}
        self.plan_file = self.root / 'plan.json'

    def verify(self, changed=None, expected=None):
        self.plan_file.write_text(json.dumps(self.plan if changed is None else changed))
        expected = replay.file_sha(self.plan_file) if expected is None else expected
        with patch.object(replay, 'METHOD_FILES', ('method.py',)), patch.object(
                replay, 'required_input_paths', return_value=self.paths):
            return replay.verify_plan(self.root, self.root, self.plan_file, expected)

    def test_frozen_complete60matrix_is_accepted(self):
        plan, paths = self.verify()
        self.assertEqual(len(plan['profiles']), 60)
        self.assertEqual(paths, self.paths)

    def test_profile_selection_future_or_gate_override_is_rejected(self):
        for key, value in [('profiles', self.plan['profiles'][:-1]), ('extra_bps', [0, 5, 10, 20]),
                           ('end', '2026-10-20'), ('2026_evaluation_permitted', True),
                           ('original_source_admission_overridden', True), ('conditional_engineering_only', False)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify({**self.plan, key: value})

    def test_omitted_source_changed_method_or_changed_plan_is_rejected(self):
        changed = copy.deepcopy(self.plan)
        del changed['input_sha256']['source/raw.json']
        with self.assertRaises(ValueError):
            self.verify(changed)
        with self.assertRaises(ValueError):
            self.verify(expected='0' * 64)
        self.method.write_text('mutated method')
        with self.assertRaisesRegex(ValueError, 'account method changed'):
            self.verify()

    def test_all60diagnostics_required_and_all3references_must_pass(self):
        passed = {'status': 'NESTED_EXECUTION_ACCOUNT_RECONCILED', 'zero_entitlements_verified': True,
                  'actual_delisting_exit_verified': True, '2024_return_pct': 1, '2025_return_pct': 1,
                  'average_exposure_pct': 95}
        results = {p: passed.copy() for p in replay.PROFILES}
        self.assertTrue(replay.complete_confirmation_passes(results))
        changed = copy.deepcopy(results)
        changed['100/40/1000000']['2025_return_pct'] = 0
        self.assertFalse(replay.complete_confirmation_passes(changed))
        del results['100/0/100000']
        self.assertFalse(replay.complete_confirmation_passes(results))

    def test_interrupted_run_preserves_primary_and_rechecks_request_and_inputs(self):
        self.plan_file.write_text(json.dumps(self.plan))
        expected = replay.file_sha(self.plan_file)
        original = KeyboardInterrupt('synthetic account interruption')
        def interrupt(*args):
            args[-1]['100/0/100000'] = {'status': 'INVALID_SOURCE_OR_ACCOUNT', 'error': 'synthetic interruption'}
            self.raw.unlink()
            self.plan_file.write_text('{}')
            raise original
        out = self.root / 'output'
        with patch.object(replay, 'verify_plan', return_value=(self.plan, self.paths)), patch.object(
                replay, 'load_inputs', return_value={'events': [], 'receipts': []}), patch.object(
                replay, 'run_profiles', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt) as caught:
                replay.run(self.root, self.root, self.plan_file, expected, out)
        self.assertIs(caught.exception, original)
        terminal = replay.read(out / 'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual(terminal['completed_profiles'], 1)
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
                         {'source/raw.json', 'frozen_account_plan'})
        self.assertFalse((out / 'summary.json').exists())

    def dummy_context(self):
        class Bank:
            accessed = set()
        return {'calendar': object(), 'bank': Bank(), 'receipts': [], 'bars': {},
                'events': [], 'targets': {}, 'lifecycles': {}}

    def test_all60failed_profiles_are_preserved_without_ROI(self):
        context, results = self.dummy_context(), {}
        out = self.root / 'all-failures'
        out.mkdir()
        with patch.object(replay, 'simulate_fixed_targets', side_effect=ValueError('synthetic account guard')) as called:
            replay.run_profiles(context, out, results)
        self.assertEqual(called.call_count, 60)
        self.assertEqual(set(results), set(replay.PROFILES))
        self.assertFalse(replay.complete_confirmation_passes(results))
        for label, row in results.items():
            self.assertEqual(row['status'], 'INVALID_SOURCE_OR_ACCOUNT')
            self.assertNotIn('2024_return_pct', row)
            self.assertEqual(set(row['failure_artifact_sha256']),
                {'failed_account_state.json', 'partial_case.json', 'failure_trace.json', 'error.json', 'tape_accessed_pairs.json'})
            self.assertTrue((out / label / 'error.json').is_file())

    def test_failed_case_write_errors_keep_original_and_try_remaining_evidence(self):
        original = KeyboardInterrupt('original account interruption')
        real_write = replay.write
        out = self.root / 'write-failure'
        out.mkdir()
        def failing_write(path, value):
            if Path(path).name in ('failed_account_state.json', 'case_results.json'):
                raise OSError('synthetic failed persistence')
            return real_write(path, value)
        results = {}
        with patch.object(replay, 'simulate_fixed_targets', side_effect=original), patch.object(
                replay, 'write', side_effect=failing_write):
            with self.assertRaises(KeyboardInterrupt) as caught:
                replay.run_profiles(self.dummy_context(), out, results)
        self.assertIs(caught.exception, original)
        self.assertTrue((out / replay.PROFILES[0] / 'failure_trace.json').exists())
        self.assertTrue((out / replay.PROFILES[0] / 'error.json').exists())
        self.assertIn('failed_account_state.json:OSError', str(original.__notes__))
        self.assertIn('Case-result persistence error: OSError', str(original.__notes__))


if __name__ == '__main__':
    unittest.main()
