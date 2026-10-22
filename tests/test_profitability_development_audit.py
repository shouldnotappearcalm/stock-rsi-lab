import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


AUDIT=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-gross-profitability-development-audit.py'


class NativeProfitabilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(AUDIT.is_file(),'independent GP development audit missing')
        spec=importlib.util.spec_from_file_location('independent_gp_development_audit',AUDIT)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'calendars').mkdir();(self.root/'calendars/day.txt').write_text('2023-12-29\n2024-01-02\n2025-12-31\n')
        self.feature=self.root/'features/sz000001/close.day.bin';self.feature.parent.mkdir(parents=True)
        self.feature.write_bytes(struct.pack('<3f',1.,4.,float('nan')))

    def test_scalar_reader_uses_literal_offset_and_rejects_future_asof(self):
        reader=self.module.QuoteReader(self.root)
        self.assertIsNone(reader.value('SZ000001','close','2023-12-29'))
        self.assertEqual(reader.value('SZ000001','close','2024-01-02'),4.)
        self.assertIsNone(reader.value('SZ000001','close','2025-12-31'))
        with self.assertRaises(ValueError):reader.value('SZ000001','close','2024-01-02',as_of='2023-12-29')
        with self.assertRaises(ValueError):reader.value('SZ000001','close','2026-01-05')

    def test_fractional_offset_and_extra_future_tail_fail_instead_of_being_accepted(self):
        for payload in (struct.pack('<2f',1.5,4.),struct.pack('<4f',1.,4.,5.,6.)):
            self.feature.write_bytes(payload)
            with self.assertRaises(ValueError):self.module.QuoteReader(self.root).value('SZ000001','close','2024-01-02')

    def test_signed_sell_delta_and_engine_point1_raw_unit_rounding_are_explicit(self):
        for side,requested,filled in [('BUY',999.98,1000.),('SELL',-999.98,-1000.)]:
            result=self.module.order_fill_quantities({'side':side,'requested_normalized_units':str(requested),
                'filled_normalized_units':str(filled)},.5)
            self.assertEqual(result['signed_units'],filled)
            self.assertTrue(result['rounded_above_requested'])
            self.assertAlmostEqual(result['raw_unit_excess'],.01)

    def test_wrong_sign_and_excess_beyond_exact_backend_lot_rule_are_rejected(self):
        for side,requested,filled in [('SELL',200.,-200.),('BUY',-200.,200.),
                                      ('BUY',199.6,200.),('BUY',200.,202.)]:
            with self.subTest((side,requested,filled)),self.assertRaises(ValueError):
                self.module.order_fill_quantities({'side':side,'requested_normalized_units':str(requested),
                    'filled_normalized_units':str(filled)},.5)

    def test_partial_buy_lot_and_odd_full_sell_exit_preserve_signed_inventory(self):
        buy=self.module.order_fill_quantities({'side':'BUY','requested_normalized_units':'600',
            'filled_normalized_units':'400'},.5)
        sell=self.module.order_fill_quantities({'side':'SELL','requested_normalized_units':'-103',
            'filled_normalized_units':'-103'},.5)
        self.assertEqual(buy['signed_units'],400.)
        self.assertEqual(sell['signed_units'],-103.)
        self.assertFalse(sell['rounded_above_requested'])


if __name__=='__main__':unittest.main()
