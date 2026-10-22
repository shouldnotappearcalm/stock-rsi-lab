import importlib.util
from pathlib import Path
import unittest


class AssetSeparateLedgerTests(unittest.TestCase):
    def test_only_functions_and_stdlib_imports_are_loaded_from_pinned_prior_checker(self):
        path=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-asset-expansion-raw-account-audit.py'
        spec=importlib.util.spec_from_file_location('separate_asset_physical_ledger',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ns,counts=module.ledger_namespace(79)
        self.assertEqual(counts,{'policy':2,'event_count':2})
        self.assertTrue(all(name not in ns for name in ('planfile','summary','base','p','a')))
        self.assertEqual(ns['fee'](ns['D']('10000'),'BUY',40),ns['D']('45.00'))
        self.assertEqual(ns['fee'](ns['D']('10000'),'SELL',40),ns['D']('55.00'))
        self.assertEqual(ns['fee'](ns['D']('100'),'BUY',20),ns['D']('5.20'))


if __name__=='__main__':unittest.main()
