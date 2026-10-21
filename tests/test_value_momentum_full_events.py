import copy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2


class FullCompositeEventTests(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module('scripts.prepare_value_momentum_full_events')
        except ModuleNotFoundError:
            self.fail('full composite source-event compiler is absent')

    def fixture(self):
        original = json.loads((Path(__file__).parent/'fixtures/low_beta60_event_extension.json').read_text())['old_row']
        row2 = {**original, 'dividRegistDate': '2025-12-30', 'dividOperateDate': '2025-12-31',
                'dividPayDate': '2025-12-31', 'dividCashPsBeforeTax': '0.14'}
        old = {'SH600000': {'instrument': 'SH600000', 'bars': [], 'adjustments': [],
                           'quarantine': [], 'distributions': [original, row2]}}
        cal = TradingCalendar(['2025-12-29', '2025-12-30', '2025-12-31', '2026-01-05',
                               '2026-06-16', '2026-06-17', '2026-10-19', '2026-10-20'])
        oldcal = TradingCalendar(['2025-12-29', '2025-12-30', '2025-12-31'])
        events, receipts = compile_distribution_events_v2(old, {'documents': []}, oldcal)
        serialized = [{k: str(v) if isinstance(v, (date, Decimal)) else v
                       for k, v in asdict(e).items()} for e in events]
        full = copy.deepcopy(old)
        new = {**original, 'code': 'sz.000937', 'dividPlanDate': '2026-06-11',
               'dividRegistDate': '2026-06-16', 'dividOperateDate': '2026-06-17',
               'dividPayDate': '2026-06-17', 'dividStockMarketDate': '2026-06-17',
               'dividCashPsBeforeTax': '0.1', 'dividReserveToStockPs': '0.1', 'dividCashStock': '10转1派1元'}
        full['SZ000937'] = {'instrument': 'SZ000937', 'bars': [], 'adjustments': [],
                             'quarantine': [], 'distributions': [{**original, 'code': 'sz.000937'}, new]}
        proof = {'documents': [], 'unresolved_tax': {'SZ000937|2026-06-17': {'verified_exempt': False}}}
        return old, {'documents': []}, serialized, list(receipts), full, proof, cal

    def test_append_retains_order_ids_receipts_and_unknown_tax_guard_without_mutation(self):
        api = self.api(); args = self.fixture(); before = copy.deepcopy(args[:-1])
        events, receipts, stats = api.compile_full(*args)
        self.assertEqual(args[2], [api.serialize_event(e) for e in events[:2]])
        self.assertEqual(args[3], list(receipts[:2]))
        self.assertEqual(['SZ000937|2026-06-17'], stats['unverified_tax_event_keys'])
        self.assertFalse(events[-1].capital_tax_exempt_verified)
        self.assertTrue(receipts[-1]['requires_zero_record_ownership_if_tax_unverified'])
        self.assertEqual(1, stats['earlier_rows_of_future_only_names_ignored'])
        self.assertEqual(before, args[:-1])

    def test_prior_order_receipts_raw_prefix_and_tax_uncertainty_cannot_be_rewritten(self):
        api = self.api()
        for case in ('order', 'receipt', 'raw', 'marker', 'upgraded'):
            with self.subTest(case=case):
                args = list(self.fixture())
                if case == 'order': args[2].reverse(); args[3].reverse()
                if case == 'receipt': args[3][0]['source_row_sha256'] = '0'*64
                if case == 'raw': args[4]['SH600000']['distributions'][0]['dividCashPsBeforeTax'] = '99'
                if case == 'marker': args[5]['unresolved_tax'] = {}
                if case == 'upgraded': args[5]['capital_tax'] = copy.deepcopy(args[5]['unresolved_tax'])
                with self.assertRaises(ValueError): api.compile_full(*args)

    def test_coverage_ignores_future_only_old_history_but_keeps_Dec31_boundary(self):
        api = self.api()
        def bar(at, close, pre): return {'date': at, 'close': close, 'preclose': pre}
        old = {'SZ000001': {'instrument': 'SZ000001', 'bars': [bar('2025-12-31', '10', '10')],
                              'distributions': [], 'adjustments': [], 'quarantine': []}}
        full = copy.deepcopy(old)
        full['SZ000001']['bars'].append(bar('2026-01-05', '10', '10'))
        full['SZ000002'] = {'instrument': 'SZ000002', 'bars': [bar('2025-12-30', '9', '8'),
            bar('2025-12-31', '10', '9.5'), bar('2026-01-05', '10', '10')],
            'distributions': [], 'adjustments': [], 'quarantine': []}
        before = copy.deepcopy((old, full)); api.validate_full_coverage(old, full, [], {'documents': []})
        self.assertEqual(before, (old, full))
        full['SZ000002']['bars'][-1]['preclose'] = '9'
        with self.assertRaises(ValueError): api.validate_full_coverage(old, full, [], {'documents': []})

    def test_unknown_quarantine_cannot_be_erased_by_coverage_projection(self):
        api = self.api(); args = self.fixture(); args[0]['SH600000']['quarantine'] = [
            {'reason': 'MISSING_OPERATE_DATE', 'record': {'dividOperateDate': ''}}]
        with self.assertRaises(ValueError): api.validate_full_coverage(args[0], args[4], [], args[1])

    def test_loader_authenticates_all_artifacts_and_restores_dates_decimals(self):
        api = self.api(); args = self.fixture(); events, receipts, _ = api.compile_full(*args)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); artifacts = {'derived_events.json': [api.serialize_event(e) for e in events],
                'event_source_receipts.json': list(receipts), 'effective_2026_proofs.json': args[5], 'lifecycles.json': {}}
            for n, v in artifacts.items(): (root/n).write_text(json.dumps(v))
            summary = {'status': api.SUMMARY_STATUS, 'compiled_events': len(events),
                'all_original_events_and_receipts_reconstructed_unchanged': True,
                'unknown_tax_requires_zero_registered_ownership': True,
                'account_replay_admitted': False, 'portfolio_returns_computed': False,
                'artifact_sha256': {n: api.file_sha(root/n) for n in artifacts}}
            (root/'summary.json').write_text(json.dumps(summary)); h = api.file_sha(root/'summary.json')
            restored, life, result = api.load_full_events(root, h)
            self.assertEqual(events, restored); self.assertEqual({}, life); self.assertEqual(summary, result)
            self.assertIsInstance(restored[-1].ex_date, date)
            self.assertIsInstance(restored[-1].capital_per_share, Decimal)
            (root/'lifecycles.json').write_text('{"forged":true}')
            with self.assertRaises(ValueError): api.load_full_events(root, h)
            # A fresh manifest hash cannot turn the unresolved event into an
            # exempt event while keeping its zero-ownership receipt marker.
            (root/'lifecycles.json').write_text(json.dumps({}))
            changed = copy.deepcopy(artifacts['derived_events.json'])
            changed[-1]['capital_tax_exempt_verified'] = True
            (root/'derived_events.json').write_text(json.dumps(changed))
            summary['artifact_sha256'] = {n: api.file_sha(root/n) for n in artifacts}
            (root/'summary.json').write_text(json.dumps(summary))
            with self.assertRaises(ValueError): api.load_full_events(root, api.file_sha(root/'summary.json'))

    def test_wrong_plan_hash_stops_before_creating_any_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'plan.json').write_text('{}')
            with self.assertRaises(ValueError): api.main(['--source-root', d, '--plan', str(root/'plan.json'),
                '--expected-plan-sha256', '0'*64, '--output-dir', str(root/'out')])
            self.assertFalse((root/'out').exists())


if __name__ == '__main__': unittest.main()
