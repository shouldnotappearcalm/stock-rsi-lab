import copy
import unittest

try:
    from scripts.run_reversal_intraday_development import confirmation_passes
except ImportError:confirmation_passes=None


class ReversalConfirmationTests(unittest.TestCase):
    def test_requires_every_registered_reference_profile_and_rejects_nonfinite_or_low_exposure(self):
        self.assertIsNotNone(confirmation_passes,'reversal intraday runner missing')
        row={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED','2024_return_pct':2.,'2025_return_pct':3.,
             'average_exposure_pct':92.,'zero_entitlements_verified':True}
        results={f'{p}/40/1000000':copy.deepcopy(row) for p in (100,500,1000)}
        self.assertTrue(confirmation_passes(results))
        for field,value in [('2024_return_pct',-1),('2025_return_pct',float('nan')),
                            ('average_exposure_pct',89),('zero_entitlements_verified',False)]:
            bad=copy.deepcopy(results);bad['500/40/1000000'][field]=value
            self.assertFalse(confirmation_passes(bad))
        results.pop('100/40/1000000');self.assertFalse(confirmation_passes(results))
