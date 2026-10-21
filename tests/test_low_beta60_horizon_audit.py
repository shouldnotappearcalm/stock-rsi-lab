import copy
import importlib.util
from pathlib import Path
import unittest


class HorizonAuditTests(unittest.TestCase):
    def api(self):
        p = Path(__file__).resolve().parents[1] / 'experiments/qlib/audit_sources/2026-10-21-low-beta60-horizon-audit.py'
        self.assertTrue(p.exists(), 'independent append-only source auditor is absent')
        spec = importlib.util.spec_from_file_location('horizon_independent_audit', p)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def fixture(self):
        old = {'instrument': 'SH600000', 'window': ['2023-12-29', '2026-10-13'],
               'bars': [{'date': '2026-10-13', 'close': '10'}],
               'distributions': [{'dividOperateDate': '2025-06-01', 'cash': '0.3'}],
               'adjustments': [], 'quarantine': [{'reason': 'AFTER_EXTENSION_CUTOFF', 'record': {'dividOperateDate': '2026-10-15', 'cash': '0.2'}}]}
        div = [{'dividOperateDate': '2026-10-15', 'cash': '0.2'}]
        daily = [{'date': '2026-10-14', 'close': '11'}, {'date': '2026-10-15', 'close': '12'}]
        adj = [{'dividOperateDate': '2026-10-15', 'factor': '1.02'}]
        packet = {'instrument': 'SH600000', 'window': ['2023-12-29', '2026-10-20'],
                  'bars': old['bars'] + daily, 'distributions': old['distributions'] + div,
                  'adjustments': adj, 'quarantine': [], 'promoted_original_quarantine': old['quarantine']}
        return copy.deepcopy(packet), copy.deepcopy(old), {'bars': [], 'distributions': [], 'adjustments': []}, daily, div, [], adj, ['2026-10-13', '2026-10-14', '2026-10-15']

    # Independent reconstruction must reject semantic changes even when an output checksum is refreshed.
    def test_reconstructs_old_prefix_and_new_source_rows_without_project_imports(self):
        api = self.api(); args = self.fixture(); api.verify_assembly(*args)
        for mutate in ('oldbar', 'newcash', 'promotion', 'missingbar', 'adjustment'):
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(args)
                if mutate == 'oldbar': changed[0]['bars'][0]['close'] = '999'
                if mutate == 'newcash': changed[0]['distributions'][-1]['cash'] = '9'
                if mutate == 'promotion': changed[0]['promoted_original_quarantine'] = []
                if mutate == 'missingbar': changed[0]['bars'].pop()
                if mutate == 'adjustment': changed[0]['adjustments'] = []
                with self.assertRaises(AssertionError): api.verify_assembly(*changed)


if __name__ == '__main__': unittest.main()
