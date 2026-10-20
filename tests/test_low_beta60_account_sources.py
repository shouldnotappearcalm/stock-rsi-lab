import copy
import unittest
try:
    from scripts.prepare_low_beta60_account_sources import verify_packet,project_proofs
except ImportError:
    verify_packet=project_proofs=None


class LowBeta60EventInputsTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(verify_packet);self.assertIsNotNone(project_proofs)

    def test_extra_future_missing_duplicate_or_wrong_instrument_rows_are_rejected(self):
        sessions=['2023-12-29','2024-01-02']
        packet={'instrument':'SH600001','window':['2023-12-29','2025-12-31'],
                'bars':[{'date':d} for d in sessions]}
        verify_packet('SH600001',packet,sessions)
        for dates in (sessions+['2026-01-05'],sessions[:1],[sessions[0],sessions[0]]):
            bad=copy.deepcopy(packet);bad['bars']=[{'date':d} for d in dates]
            with self.assertRaises(ValueError):verify_packet('SH600001',bad,sessions)
        with self.assertRaises(ValueError):verify_packet('SH600002',packet,sessions)

    def test_projection_adds_versioned_contract_but_preserves_original_proofs_and_denied_admission(self):
        source={'status':'SOURCE_REVIEW_PENDING_CONTRACT','cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1_PENDING_IMPLEMENTATION',
                'cash_overrides':{'x':{'effective_cash_per_share':'.2400974'}},
                'event_compilation_admitted':False,'admitted_for_account_replay':False}
        before=copy.deepcopy(source);projected=project_proofs(source,'a'*64)
        self.assertEqual(source,before)
        self.assertEqual(projected['cash_overrides'],source['cash_overrides'])
        self.assertEqual(projected['cash_override_contract'],'PRIMARY_NOTICE_CASH_PRECISION_V1')
        self.assertEqual(projected['source_reviewed_manifest_sha256'],'a'*64)
        self.assertFalse(projected['admitted_for_account_replay'])
        projected['cash_overrides']['x']['effective_cash_per_share']='0'
        self.assertEqual(source,before)
