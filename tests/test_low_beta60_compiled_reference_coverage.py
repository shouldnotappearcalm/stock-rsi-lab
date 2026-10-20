import copy
import unittest
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from scripts.run_low_risk_raw_share_validation import validate_source_coverage
from scripts import run_low_beta60_raw_development as runner


class CompiledReferenceCoverageTests(unittest.TestCase):
    def test_primary_supplement_explains_reference_without_editing_raw_packet(self):
        check = getattr(runner, 'validate_compiled_reference_coverage', None)
        self.assertIsNotNone(check, 'coverage must consume independently verified compiled dates')
        code = 'SH600167'
        sessions = ['2024-12-25', '2024-12-26', '2024-12-27']
        packets = {code: {'instrument': code, 'quarantine': [], 'distributions': [],
            'adjustments': [{'dividOperateDate': '2024-12-27'}],
            'bars': [{'date': d, 'close': '9.88' if d == sessions[-1] else '10.00',
                      'preclose': '9.88' if d == sessions[-1] else '10.00'} for d in sessions]}}
        row = {'code': 'sh.600167', 'dividPlanDate': '2024-12-20',
            'dividRegistDate': '2024-12-26', 'dividOperateDate': '2024-12-27',
            'dividPayDate': '2024-12-27', 'dividStockMarketDate': '',
            'dividCashPsBeforeTax': '.12', 'dividStocksPs': '0',
            'dividReserveToStockPs': '0', 'dividCashStock': '10派1.2元'}
        proofs = {'documents': [{'file': 'notice.pdf', 'sha256': 'a'*64,
            'instrument': code, 'day': '2024-12-20'}],
            'supplementary_distributions': [{'instrument': code, 'record': row,
                'source_file': 'notice.pdf', 'source_sha256': 'a'*64}]}
        before = copy.deepcopy(packets)
        events, _ = compile_distribution_events_v2(packets, proofs, TradingCalendar(sessions))
        with self.assertRaisesRegex(ValueError, 'unexplained raw reference change'):
            validate_source_coverage(packets)
        check(packets, events)
        self.assertEqual(packets, before)
        with self.assertRaisesRegex(ValueError, 'unexplained raw reference change'):
            check(packets, ())
        self.assertEqual(packets, before)
