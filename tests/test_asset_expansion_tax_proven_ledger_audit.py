import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-proven-ledger-audit.py'
if P.exists():
    s=importlib.util.spec_from_file_location('tax_proven_ledger_audit',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
else:m=None

class TaxProvenLedgerTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(m,'independent ledger audit required')
    def test_separate_reference_has_only_enumerated_adaptations(self):
        ns,changes=m.ledger_namespace()
        self.assertEqual(changes,{'policy':2,'24':4,'179':2,'485':1,'486':1,'lifecycle_loop':1,'return_state':1})
        self.assertTrue(callable(ns['audit']))
    def test_exit_requires_no_actual_inventory_or_receivables(self):
        proof={'SH603056':{'effective_date':'2026-03-31'}};events={'e':{'instrument':'SH603056'}}
        for kind in ('owned','stock','cash','clear'):
            marks={'SH603056':10};owned={'SH603056':1} if kind=='owned' else {}
            stock={('e','CAPITAL_SHARES_LISTED'):('SH603056',1,'2026-04-01','2026-03-30')} if kind=='stock' else {}
            cash={'e':('2026-04-01',10)} if kind=='cash' else {}
            if kind=='clear':
                self.assertTrue(m.exit_guard('SH603056','2026-03-31',owned,stock,cash,marks,proof,events));self.assertEqual(marks,{})
            else:
                with self.subTest(kind),self.assertRaises(AssertionError):
                    m.exit_guard('SH603056','2026-03-31',owned,stock,cash,marks,proof,events)
    def test_remaining_marks_are_preserved_before_exit(self):
        marks={'SH603056':10}
        self.assertFalse(m.exit_guard('SH603056','2026-03-30',{'SH603056':1},{},{},marks,
            {'SH603056':{'effective_date':'2026-03-31'}},{}));self.assertEqual(marks,{'SH603056':10})

if __name__=='__main__':unittest.main()
