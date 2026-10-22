import copy
import importlib
import unittest


class AssetExpansionRawSourceTests(unittest.TestCase):
    def setUp(self):
        self.module=importlib.import_module('scripts.capture_asset_expansion_raw_pre2026')

    def packet(self):
        return {'instrument':'SH600066','window':['2023-12-29','2025-12-31'],
            'bars':[{'date':'2023-12-29','close':'10'}],
            'distributions':[{'dividOperateDate':'2024-06-01','dividCashPsBeforeTax':'0.1'}],
            'adjustments':[{'dividOperateDate':'2024-06-01','backAdjustFactor':'1.01'}],
            'quarantine':[],'provenance':{'ignored':'one'}}

    def test_source_equivalence_covers_distributions_and_adjustments_not_just_prices(self):
        original=self.packet();fingerprint=self.module.source_fingerprint(original)
        for field,key in [('distributions','dividCashPsBeforeTax'),('adjustments','backAdjustFactor')]:
            changed=copy.deepcopy(original);changed[field][0][key]='99'
            self.assertNotEqual(self.module.source_fingerprint(changed),fingerprint)
        changed=copy.deepcopy(original);changed['provenance']={'ignored':'two'}
        self.assertEqual(self.module.source_fingerprint(changed),fingerprint)

    def test_equivalence_rejects_future_window_and_future_rows(self):
        for field,key in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:
            changed=self.packet();changed[field][0][key]='2026-01-05'
            with self.subTest(field),self.assertRaises(ValueError):self.module.source_fingerprint(changed)
        changed=self.packet();changed['window'][1]='2026-10-20'
        with self.assertRaises(ValueError):self.module.source_fingerprint(changed)

    def test_source_comparison_ignores_row_order_but_preserves_duplicates(self):
        original=self.packet();other=copy.deepcopy(original)
        other['distributions'].append({'dividOperateDate':'2025-06-01','dividCashPsBeforeTax':'0.2'})
        reversed_rows=copy.deepcopy(other);reversed_rows['distributions'].reverse()
        self.assertEqual(self.module.source_fingerprint(other),self.module.source_fingerprint(reversed_rows))
        other['distributions'].append(other['distributions'][0])
        self.assertNotEqual(self.module.source_fingerprint(other),self.module.source_fingerprint(reversed_rows))

    def test_route_requires_unambiguous_authenticated_full_calendar(self):
        good={'directory':'a','packet_sha256':'1','fingerprint':'x','complete_calendar':True}
        other={**good,'directory':'b','packet_sha256':'2'}
        self.assertEqual(self.module.choose_route([good,other]),good)
        for bad in ([{**good,'complete_calendar':False}], [good,{**other,'fingerprint':'y'}]):
            with self.assertRaises(ValueError):self.module.choose_route(bad)
        self.assertIsNone(self.module.choose_route([]))


if __name__=='__main__':unittest.main()
