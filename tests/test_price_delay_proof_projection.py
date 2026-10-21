from copy import deepcopy
import unittest

from scripts.prepare_price_delay_account_sources_pre2026 import project_proofs
from stock_rsi.distribution_event_compiler_v2 import CONTRACT


class PriceDelayProofProjectionTests(unittest.TestCase):
    def proposal(self):
        return {'cash_override_contract': CONTRACT, 'cash_overrides': {},
                'event_compilation_admitted': False, 'admitted_for_account_replay': False,
                'capital_tax': {'known': {'verified_exempt': True, 'evidence_kind': 'CONDITIONAL_INFERENCE'}},
                'unknown_capital_tax': ['unproved-event'], 'documents': []}

    def test_projection_keeps_unknown_and_inference_boundaries_without_mutating_proposal(self):
        proposal = self.proposal(); original = deepcopy(proposal)
        effective = project_proofs(proposal, 'a'*64)
        self.assertEqual(proposal, original)
        self.assertEqual(effective['capital_tax'], original['capital_tax'])
        self.assertEqual(effective['unknown_capital_tax'], ['unproved-event'])
        self.assertNotIn('unproved-event', effective['capital_tax'])
        self.assertFalse(effective['admitted_for_account_replay'])
        effective['capital_tax']['known']['verified_exempt'] = False
        self.assertEqual(proposal, original)

    def test_wrong_contract_or_pre_admitted_proof_is_rejected(self):
        for change in ({'cash_override_contract': 'unsupported'}, {'event_compilation_admitted': True},
                       {'admitted_for_account_replay': True}):
            with self.assertRaises(ValueError): project_proofs(self.proposal() | change, 'a'*64)
