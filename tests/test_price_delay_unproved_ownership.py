from datetime import date
from types import SimpleNamespace
import unittest

import scripts.run_price_delay_raw_pre2026 as replay


class UnprovedTaxOwnershipTests(unittest.TestCase):
    def helper(self):
        if not hasattr(replay, 'verify_unproved_record_ownership'):
            self.fail('actual unproved-event record-ownership gate has no isolated verifier')
        return replay.verify_unproved_record_ownership

    def event(self):
        return SimpleNamespace(event_id='unproved', instrument='SH603596',
                               ex_date=date(2024, 5, 20), capital_tax_exempt_verified=False)

    def record(self, quantity):
        return {'kind': 'RECORD_DATE_OWNERSHIP', 'event_id': 'unproved', 'quantity': quantity}

    def test_actual_zero_record_is_retained_with_no_new_tax_exemption(self):
        event = self.event(); ledger = [self.record(0)]
        self.assertEqual(self.helper()([event], ledger), ledger)
        self.assertFalse(event.capital_tax_exempt_verified)

    def test_positive_or_missing_actual_record_fails_even_if_a_target_would_be_zero(self):
        for ledger in ([self.record(100)], []):
            with self.assertRaises(ValueError): self.helper()([self.event()], ledger)

    def test_wrong_identity_duplicate_record_or_promoted_exemption_cannot_bypass_gate(self):
        for ledger in ([self.record(0) | {'event_id': 'other'}], [self.record(0), self.record(0)]):
            with self.assertRaises(ValueError): self.helper()([self.event()], ledger)
        event = self.event(); event.capital_tax_exempt_verified = True
        with self.assertRaises(ValueError): self.helper()([event], [self.record(0)])
