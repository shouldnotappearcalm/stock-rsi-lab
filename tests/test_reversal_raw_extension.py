import copy
import unittest

try:
    from scripts.capture_reversal_raw_extension import full_target_codes,assert_development_prefix,append_2026
except ImportError:full_target_codes=assert_development_prefix=append_2026=None


class ReversalRawExtensionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(append_2026,'raw extension capture missing')
        self.dev={'instrument':'SH600001','window':['2023-12-29','2025-12-31'],
                  'bars':[{'date':'2025-12-31','close':'10'}],
                  'distributions':[{'dividOperateDate':'2025-06-01'}],
                  'adjustments':[{'dividOperateDate':'2025-06-01'}],'quarantine':[]}
        self.suffix={'instrument':'SH600001','bars':[{'date':'2026-01-05','close':'11'}],
                     'distributions':[{'dividOperateDate':'2026-06-01'}],
                     'adjustments':[{'dividOperateDate':'2026-06-01'}],'quarantine':[]}

    def test_only_append_new_year_without_mutating_or_replacing_development_rows(self):
        original=copy.deepcopy(self.dev);extended=append_2026(self.dev,self.suffix)
        self.assertEqual(self.dev,original);assert_development_prefix(self.dev,extended)
        self.assertEqual([r['date'] for r in extended['bars']],['2025-12-31','2026-01-05'])
        altered=copy.deepcopy(extended);altered['bars'][0]['close']='999'
        with self.assertRaises(ValueError):assert_development_prefix(self.dev,altered)
        for key in ('distributions','adjustments'):
            altered=copy.deepcopy(extended);altered[key][0]['dividOperateDate']='2025-06-02'
            with self.assertRaises(ValueError):assert_development_prefix(self.dev,altered)

    def test_cannot_smuggle_old_rows_or_wrong_security_into_suffix(self):
        for changed in (self.suffix|{'instrument':'SH600002'},self.suffix|{'bars':[{'date':'2025-12-31'}]},
                        self.suffix|{'distributions':[{'dividOperateDate':'2025-06-01'}]}):
            with self.assertRaises(ValueError):append_2026(self.dev,changed)

    def test_full_target_dates_remain_within_frozen_account_cutoff(self):
        target={'as_of':'2026-09-30','weights':{'SH600001':.95}}
        self.assertEqual(full_target_codes({'2026-10-09':target}),['SH600001'])
        with self.assertRaises(ValueError):full_target_codes({'2026-11-02':target})
        with self.assertRaises(ValueError):full_target_codes({'2026-10-09':target|{'as_of':'2026-10-09'}})
        with self.assertRaises(ValueError):full_target_codes({'2026-10-09':target|{'weights':{'SH688001':.95}}})
