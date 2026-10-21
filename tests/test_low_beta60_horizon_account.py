import copy
from datetime import date
from decimal import Decimal
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_tape import aggregate_minutes
from stock_rsi.stock_distribution_account import StockDistribution
from scripts.fundamental_query_journal import file_sha
from scripts.tdx_history_checks import minute_labels


class HorizonAccountTests(unittest.TestCase):
    def api(self):
        try: return importlib.import_module('scripts.run_low_beta60_horizon_account')
        except ModuleNotFoundError: self.fail('fixed continuous Oct20 account entry is absent')

    # Annual reinitialization or rounded threshold comparison would falsely accept this boundary.
    def test_returns_use_previous_year_end_equity_and_unrounded_ten_percent_boundary(self):
        api = self.api()
        rows = [{'day': '2023-12-29', 'equity': Decimal('100')}, {'day': '2024-12-31', 'equity': Decimal('110')},
                {'day': '2025-12-31', 'equity': Decimal('121')}, {'day': '2026-10-20', 'equity': Decimal('133.1')}]
        result = api.fixed_interval_returns(rows, '100')
        self.assertEqual(10, result['2024_return_pct']); self.assertEqual(10, result['2025_return_pct']); self.assertEqual(10, result['2026_through_2026-10-20_return_pct'])
        self.assertTrue(result['three_numeric_conditions_met_at_interim_cutoff'])
        rows[-1]['equity'] = Decimal('133.099999999')
        self.assertFalse(api.fixed_interval_returns(rows, '100')['three_numeric_conditions_met_at_interim_cutoff'])

    # A legitimate Dec31 decision for next January must not hide a changed pre2026 fill or financial row.
    def test_financial_prefix_requires_all_seven_artifacts_and_filters_intents_by_execution_day(self):
        api = self.api()
        reference = {'days': [{'day': '2025-12-31', 'equity': '100'}], 'intents': [{'execution_session': '2025-12-01', 'snapshot_sha256': 'old'}],
            'parent_instructions': [{'eligible_at': '2025-12-01T01:30:00+00:00', 'quantity': 100}],
            'orders': [{'submitted_at': '2025-12-01T01:35:00+00:00', 'quantity': 100}],
            'fills': [{'execution_at': '2025-12-01T01:40:00+00:00', 'quantity': 100}],
            'corporate_ledger': [{'day': '2025-06-01', 'quantity': 100}], 'ownership': {'2025-12-31': {'SH600008': 100}}}
        case = copy.deepcopy(reference); case['intents'].append({'execution_session': '2026-01-05', 'as_of': '2025-12-31T07:05:00+00:00'})
        api.verify_financial_prefix(case, reference)
        for key in ('days', 'intents', 'parent_instructions', 'orders', 'fills', 'corporate_ledger', 'ownership'):
            with self.subTest(key=key):
                changed = copy.deepcopy(case)
                if key == 'ownership': changed[key]['2025-12-31']['SH600008'] = 999
                else: changed[key][0] = {**changed[key][0], 'tampered': True}
                with self.assertRaises(ValueError): api.verify_financial_prefix(changed, reference)

    def tape(self, code, day):
        return {'exchange': 'sh', 'market_id': 1, 'code': code[2:], 'trading_date': day,
            'points': [{'index': i, 'time_label': s, 'time': day + 'T' + s + ':00+08:00', 'price_milli': 10000, 'price': 10, 'volume': 50000}
                       for i, s in enumerate(minute_labels())]}

    # Genuine positive ownership must stop all six profiles before noncash credits and preserve its proof.
    def test_owned_unknown_capital_tax_stops_each_real_account_and_preserves_entitlements_without_roi(self):
        api = self.api(); code = 'SH600008'; days = ['2025-12-31', '2026-01-05', '2026-06-16', '2026-06-17']; cal = TradingCalendar(days)
        bars = {code: {d: {'code': 'sh.600008', 'date': d, 'tradestatus': '1', 'isST': '0', 'open': '10', 'high': '10', 'low': '10', 'close': '10', 'preclose': '10', 'volume': '1200000000'} for d in days}}
        payload = self.tape(code, '2026-01-05')
        windows = aggregate_minutes(code, date(2026, 1, 5), payload['points'])
        class Bank:
            index = {(code, '2026-01-05'): None}; accessed = set()
            def __call__(self, security, day): self.accessed.add((security, day.isoformat())); return windows
        event = StockDistribution('unknown', code, date(2026, 1, 2), date(2026, 6, 16), date(2026, 6, 17), date(2026, 6, 17), date(2026, 6, 17), Decimal('.1'), Decimal('.1'), False)
        targets = {'2026-01-05': {'as_of': '2025-12-31', 'weights': {code: '.95'}}}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            results = api.run_profiles(out, cal, bars, [event], targets, Bank(), {})
            self.assertEqual({f'{p}/{cost}' for p in (100, 500, 1000) for cost in (20, 40)}, set(results))
            for profile, result in results.items():
                self.assertEqual('INVALID_SOURCE_OR_ACCOUNT', result['status']); self.assertIn('capital transfer tax', result['error'])
                self.assertFalse(result['portfolio_returns_computed']); self.assertNotIn('2026_through_2026-10-20_return_pct', result)
                state = json.loads((out / profile / 'failed_account_state.json').read_text())
                self.assertGreater(state['entitlements']['unknown'], 0); self.assertEqual(state['entitlements']['unknown'], state['owned_shares'][code])
                self.assertFalse(any(r['kind'] == 'EX_DATE_ENTITLEMENT' for r in state['corporate_ledger']))
                self.assertGreater(len(state['fills']), 0)
                for name, h in result['failure_artifact_sha256'].items(): self.assertEqual(h, file_sha(out / profile / name))

    # The second cached tape access must still reject changed source bytes.
    def test_minute_bank_rechecks_cached_bytes_and_merges_disjoint_years(self):
        api = self.api(); code = 'SH600008'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); dirs = []; bars = {code: {}}
            for label, day in (('old', '2025-12-01'), ('new', '2026-01-05')):
                cap = root / label; (cap / 'sessions').mkdir(parents=True); dirs.append(cap); (cap / 'plan.json').write_text('{}\n')
                f = cap / 'sessions' / (code + '-' + day + '.json'); f.write_text(json.dumps({'instrument': code, 'requested_day': day, 'status': 'RESPONSE_CAPTURED', 'response': self.tape(code, day)}) + '\n')
                (cap / 'manifest.json').write_text(json.dumps({'complete_capture': True, 'plan_sha256': file_sha(cap / 'plan.json'), 'per_session_sha256': {f.name: file_sha(f)}}) + '\n')
                bars[code][day] = {'code': 'sh.600008', 'date': day, 'open': '10', 'high': '10', 'low': '10', 'close': '10',
                    'preclose': '10', 'volume': '1200000000', 'amount': '12000000000', 'adjustflag': '3', 'tradestatus': '1', 'isST': '0'}
            bank = api.ContinuousTapeBank(*dirs, bars); self.assertEqual(2, len(bank.index)); self.assertEqual(48, len(bank(code, date(2026, 1, 5))))
            f = next((dirs[1] / 'sessions').iterdir()); f.write_bytes(f.read_bytes() + b' ')
            with self.assertRaises(ValueError): bank(code, date(2026, 1, 5))

    def test_wrong_frozen_plan_checksum_creates_no_replay_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'plan.json'; p.write_text('{}\n'); out = Path(d) / 'out'
            with self.assertRaises(ValueError): api.main(['--plan', str(p), '--expected-plan-sha256', '0' * 64, '--source-root', d, '--output-dir', str(out)])
            self.assertFalse(out.exists())

    # A plan cannot silently omit the source/evidence bindings and trust internally consistent replacement files.
    def test_loader_rejects_missing_binding_scope_before_reading_any_account_source(self):
        api = self.api(); self.assertTrue(hasattr(api, 'LOCAL_FILES') and hasattr(api, 'PUBLIC_FILES'), 'mandatory input binding scope is absent')
        for field, names in (('method_code_sha256', api.METHOD_FILES), ('local_source_sha256', api.LOCAL_FILES), ('public_evidence_sha256', api.PUBLIC_FILES)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                plan = {'method_code_sha256': dict.fromkeys(api.METHOD_FILES, '0' * 64),
                        'local_source_sha256': dict.fromkeys(api.LOCAL_FILES, '0' * 64),
                        'public_evidence_sha256': dict.fromkeys(api.PUBLIC_FILES, '0' * 64)}
                del plan[field][names[0]]
                try: api.load_inputs(Path(d), Path(d), plan)
                except Exception as exc: self.assertIsInstance(exc, ValueError)
                else: self.fail('missing bound input scope accepted')


if __name__ == '__main__': unittest.main()
