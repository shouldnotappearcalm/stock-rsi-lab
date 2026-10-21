import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from stock_rsi.calendar import TradingCalendar


class HorizonEventTests(unittest.TestCase):
    def api(self):
        try: return importlib.import_module('scripts.prepare_low_beta60_horizon_events')
        except ModuleNotFoundError: self.fail('Oct20 append-only event entry is absent')

    def inputs(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/low_beta60_event_extension.json').read_text())
        old = {'SH600000': {'instrument': 'SH600000', 'bars': [], 'adjustments': [], 'quarantine': [],
                           'distributions': [fixture['old_row']]}}
        horizon = copy.deepcopy(old)
        horizon['SH600000']['distributions'].append({**fixture['old_row'], 'dividPlanDate': '2026-10-09',
            'dividRegistDate': '2026-10-13', 'dividOperateDate': '2026-10-14', 'dividPayDate': '2026-10-14',
            'dividCashPsBeforeTax': '0.27', 'dividCashStock': '10派2.7元'})
        cal = TradingCalendar(['2025-12-29', '2025-12-30', '2025-12-31', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-19', '2026-10-20'])
        return [old, {'documents': []}, [fixture['old_event']], [fixture['old_receipt']],
                copy.deepcopy([fixture['old_event']]), copy.deepcopy([fixture['old_receipt']]),
                horizon, {'documents': [], 'unresolved_tax': {}}, cal]

    # Reordering or changing any old event/receipt must not be hidden by recompiling the enlarged source.
    def test_old_event_objects_and_receipts_are_retained_before_late_cash_append(self):
        api = self.api(); args = self.inputs(); before = copy.deepcopy(args[:-1])
        events, receipts, stats = api.compile_horizon(*args)
        self.assertEqual(args[4][0], api.serialize_event(events[0])); self.assertEqual(args[5][0], receipts[0])
        self.assertEqual('0.27', str(events[1].cash_per_share)); self.assertEqual('2026-10-13', events[1].recorded.isoformat())
        self.assertEqual('2026-10-14', events[1].ex_date.isoformat()); self.assertEqual(1, stats['new_post_Oct13_events'])
        self.assertEqual(before, args[:-1])

    # A changed prior receipt, duplicate prior identity or newly inserted earlier event must fail closed.
    def test_prior_economics_and_prior_cutoff_cannot_be_rewritten(self):
        api = self.api()
        for mode in ('cash', 'receipt', 'duplicate', 'missing', 'earlier'):
            with self.subTest(mode=mode):
                args = self.inputs()
                if mode == 'cash': args[4][0]['cash_per_share'] = '999'
                if mode == 'receipt': args[5][0]['source_row_sha256'] = '0' * 64
                if mode == 'duplicate': args[4].append(copy.deepcopy(args[4][0])); args[5].append(copy.deepcopy(args[5][0]))
                if mode == 'missing': args[4] = []; args[5] = []
                if mode == 'earlier':
                    args[6]['SH600000']['distributions'][1].update(dividRegistDate='2026-10-09', dividOperateDate='2026-10-13', dividPayDate='2026-10-13')
                with self.assertRaises(ValueError): api.compile_horizon(*args)

    def test_wrong_external_plan_checksum_does_not_create_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'request.json'; p.write_text('{}\n'); out = Path(d) / 'out'
            with self.assertRaises(ValueError): api.main(['--plan', str(p), '--expected-plan-sha256', '0' * 64, '--source-root', d, '--output-dir', str(out)])
            self.assertFalse(out.exists())

    # Excluding ten unowned old histories must never exclude their Dec31-to-first2026 reference check.
    def test_coverage_checks_old_owned_history_and_first_new_year_boundary_without_rewriting_sources(self):
        api = self.api(); self.assertTrue(callable(getattr(api, 'validate_horizon_coverage', None)), 'explicit coverage guard is absent')
        args = self.inputs(); events, _, _ = api.compile_horizon(*args)
        def bar(day, close, reference): return {'date': day, 'close': close, 'preclose': reference}
        old = copy.deepcopy(args[0]); old['SH600000']['bars'] = [bar('2025-12-29', '10', '10'), bar('2025-12-30', '9.88', '9.88'), bar('2025-12-31', '10', '9.88')]
        packets = copy.deepcopy(old); packets['SH600000']['bars'] += [bar('2026-01-05', '10', '10'), bar('2026-10-13', '10', '10'), bar('2026-10-14', '9.73', '9.73')]
        packets['SH600001'] = {'instrument': 'SH600001', 'distributions': [], 'adjustments': [], 'quarantine': [],
            'bars': [bar('2025-12-30', '11', '11'), bar('2025-12-31', '10', '10'), bar('2026-01-05', '10', '10')]}
        before = copy.deepcopy((old, packets)); api.validate_horizon_coverage(old, packets, events)
        self.assertEqual(before, (old, packets))
        with self.assertRaises(ValueError): api.validate_horizon_coverage(old, packets, events[:1])
        bad = copy.deepcopy(packets); bad['SH600001']['bars'][-1]['preclose'] = '8'
        with self.assertRaises(ValueError): api.validate_horizon_coverage(old, bad, events)
        badold = copy.deepcopy(old); badold['SH600000']['bars'][-1]['preclose'] = '8'
        with self.assertRaises(ValueError): api.validate_horizon_coverage(badold, packets, events)


if __name__ == '__main__': unittest.main()
