import copy
import importlib.util
from pathlib import Path
import unittest


class AssetExpansionSeparateSourceAuditTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-asset-expansion-raw-source-audit.py'
        s=importlib.util.spec_from_file_location('separate_asset_raw_QA',p)
        self.module=importlib.util.module_from_spec(s);s.loader.exec_module(self.module)
        self.payload={'fields':['provider_response'],'rows':[{'initial_error_code':'0','final_error_code':'0',
            'iteration_error_type':None,'iteration_error':None,'fields':['date','code'],'rows':[['2025-12-31','sh.603712']]}]}

    def test_only_complete_successful_rectangular_sdk_rows_are_decoded(self):
        self.assertEqual(self.module.envelope(self.payload,('date','code')),[{'date':'2025-12-31','code':'sh.603712'}])
        for key,value in [('initial_error_code','1'),('final_error_code','1'),('iteration_error_type','TimeoutError'),
                          ('fields',['date','wrong']),('rows',[['2025-12-31']]),('rows',[['2025-12-31',603712]])]:
            p=copy.deepcopy(self.payload);p['rows'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.module.envelope(p,('date','code'))

    def test_duplicate_response_envelopes_do_not_become_success(self):
        p=copy.deepcopy(self.payload);p['rows'].append(p['rows'][0])
        with self.assertRaises(ValueError):self.module.envelope(p,('date','code'))


if __name__=='__main__':unittest.main()
