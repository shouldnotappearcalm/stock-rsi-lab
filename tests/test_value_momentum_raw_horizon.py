import unittest
from datetime import date
from decimal import Decimal

from scripts.run_value_momentum_raw_horizon import (CheckpointAccount, interval_returns, verify_prefix,
    require_exact_bindings, METHOD_FILES, LOCAL_FILES, PUBLIC_FILES)
from stock_rsi.calendar import TradingCalendar


class FullDailyBoundaryTests(unittest.TestCase):
    def test_omitted_binding_or_financial_identity_is_rejected(self):
        plan = {'method_code_sha256': dict.fromkeys(METHOD_FILES, 'hash'),
            'local_source_sha256': dict.fromkeys(LOCAL_FILES, 'hash'),
            'public_evidence_sha256': dict.fromkeys(PUBLIC_FILES, 'hash'),
            'immutable_financial_sha256': {'reference': 'hash'}}
        require_exact_bindings(plan, {'reference': 'hash'})
        for key in plan:
            bad = {**plan, key: {}}
            with self.assertRaises(ValueError):
                require_exact_bindings(bad, {'reference': 'hash'})

    def test_continuous_year_denominators_and_exact_cutoff(self):
        rows = [{'day': d, 'equity': v} for d, v in (
            ('2024-12-31', '110'), ('2025-12-31', '132'), ('2026-10-20', '145.2'))]
        result = interval_returns(rows, '100')
        self.assertEqual(result['2024_return_pct'], 10)
        self.assertEqual(result['2025_return_pct'], 20)
        self.assertEqual(result['2026_through_2026-10-20_return_pct'], 10)
        self.assertTrue(result['three_numeric_conditions_met_at_interim_cutoff'])
        with self.assertRaises(ValueError):
            interval_returns(rows[:-1], '100')

    def test_checkpoint_cannot_be_rewritten_by_later_order_state(self):
        account = CheckpointAccount(TradingCalendar(['2025-12-31', '2026-01-02']), '100')
        account.broker.orders.append({'order_id': 'prior', 'status': 'PENDING'})
        account.end_day(date(2025, 12, 31))
        account.broker.orders[0]['status'] = 'FILLED'
        account.broker.orders.append({'order_id': 'new-january', 'status': 'PENDING'})
        self.assertEqual(account.pre2026_checkpoint['orders'], [{'order_id': 'prior', 'status': 'PENDING'}])

    def test_prefix_includes_snapshots_and_uses_boundary_not_future_order_state(self):
        original = {'days': [{'day': '2025-12-31', 'equity': '100'}],
            'intents': [{'execution_session': '2025-12-01', 'snapshot_sha256': 'old'}],
            'orders': [{'status': 'PENDING'}], 'fills': [], 'corporate_ledger': [],
            'ownership': {'2025-12-31': {'SZ000001': 100}}}
        case = {**original, 'days': [{'day': '2025-12-31', 'equity': Decimal('100')}],
            'orders': [{'status': 'FILLED'}],
            'intents': original['intents'] + [{'execution_session': '2026-01-02'}]}
        checkpoint = {k: original[k] for k in ('orders', 'fills', 'corporate_ledger')}
        verify_prefix(case, checkpoint, original)
        case['intents'][0] = {'execution_session': '2025-12-01', 'snapshot_sha256': 'changed'}
        with self.assertRaises(ValueError):
            verify_prefix(case, checkpoint, original)


if __name__ == '__main__':
    unittest.main()
