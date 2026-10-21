import copy
import importlib.util
from pathlib import Path
import unittest


class HorizonEventAuditTests(unittest.TestCase):
    def api(self):
        path = Path(__file__).resolve().parents[1] / 'experiments/qlib/audit_sources/2026-10-21-low-beta60-horizon-event-audit.py'
        self.assertTrue(path.exists(), 'independent three-event append auditor is absent')
        spec = importlib.util.spec_from_file_location('horizon_event_independent_audit', path)
        api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api); return api

    # Refreshing output hashes must not conceal an old rewrite, late cash change, missing event or lost guard.
    def test_old_prefix_and_new_source_projections_reject_semantic_mutations(self):
        api = self.api()
        old = [{'event_id': 'old', 'cash_per_share': '.1', 'capital_tax_exempt_verified': False}]
        prior = [{'event_id': 'old', 'requires_zero_record_ownership_if_tax_unverified': True}]
        extra = [{'event_id': 'new', 'cash_per_share': '.27'}]; evidence = [{'event_id': 'new', 'source_kind': 'VENDOR_DISTRIBUTION'}]
        args = [copy.deepcopy(old), copy.deepcopy(prior), copy.deepcopy(old + extra), copy.deepcopy(prior + evidence), copy.deepcopy(extra), copy.deepcopy(evidence)]
        api.verify_increment(*args)
        for mode in ('prefix', 'cash', 'missing', 'receipt', 'guard'):
            with self.subTest(mode=mode):
                changed = copy.deepcopy(args)
                if mode == 'prefix': changed[2][0]['cash_per_share'] = '9'
                if mode == 'cash': changed[2][1]['cash_per_share'] = '9'
                if mode == 'missing': changed[2].pop(); changed[3].pop()
                if mode == 'receipt': changed[3][1]['source_kind'] = 'PRICE_GAP_INFERENCE'
                if mode == 'guard': changed[3][0]['requires_zero_record_ownership_if_tax_unverified'] = False
                with self.assertRaises(AssertionError): api.verify_increment(*changed)


if __name__ == '__main__': unittest.main()
