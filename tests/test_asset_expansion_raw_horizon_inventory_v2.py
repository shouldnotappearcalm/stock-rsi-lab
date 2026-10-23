import copy
import importlib
import json
from pathlib import Path

from tests import test_asset_expansion_raw_horizon_inventory as contracts


class RawHorizonInventoryV2Tests(contracts.RawHorizonInventoryTests):
    def setUp(self):
        super().setUp()
        self.m=importlib.import_module('scripts.inventory_asset_expansion_raw_horizon_v2')

    def runner_fixture(self,root):
        args=super().runner_fixture(root)
        request,_,repo,base,_=args
        v1=repo/self.m.V1_RESULT;v1.write_text(json.dumps({'status':'synthetic prior retained attempt'}))
        r=json.loads(request.read_text())
        r['status']='FROZEN_ASSET_EXPANSION_ALL47_RAW_OVERLAP_CHECK_V2'
        r['output_directory']='asset-expansion-raw-overlap-v2-20261023'
        r['public_evidence_sha256'][self.m.V1_RESULT]=self.m.sha(v1)
        request.write_text(json.dumps(r))
        return request,self.m.sha(request),repo,base,base/r['output_directory']

    def test_after_tax_alternatives_remain_literal_and_any_difference_is_a_conflict(self):
        original=self.packet();original['distributions'][0]['dividCashPsAfterTax']='0.09或0.1'
        self.m.validate_packet(original,self.code,self.days,original['window'])
        self.assertEqual(self.m.canonical(original['distributions'][0],'distributions')['dividCashPsAfterTax'],'0.09或0.1')
        self.assertEqual(self.m.compare_packets(original,copy.deepcopy(original)),[])
        changed=copy.deepcopy(original);changed['distributions'][0]['dividCashPsAfterTax']='0.090或0.1'
        self.assertEqual(self.m.compare_packets(original,changed)[0]['field'],'distributions')
        for field,key in [('distributions','dividCashPsBeforeTax'),('distributions','dividStocksPs'),
                          ('distributions','dividReserveToStockPs'),('adjustments','foreAdjustFactor')]:
            changed=copy.deepcopy(original);changed[field][0][key]='0.09或0.1'
            with self.subTest(field=field,key=key),self.assertRaises(ValueError):
                self.m.validate_packet(changed,self.code,self.days,changed['window'])

    def test_only_declared_schema_and_version_identity_changes(self):
        root=Path(__file__).resolve().parents[1]
        old=(root/'scripts/inventory_asset_expansion_raw_horizon.py').read_text()
        expected=old.replace('Read-only, bounded raw-source overlap gate; no policy, account or network.',
            'V2 preserves the optional after-tax source literal; no account or network.')
        expected=expected.replace("PLAN = 'docs/research/asset-expansion-2026-raw-overlap-plan-2026-10-23.md'",
            "PLAN = 'docs/research/asset-expansion-2026-raw-overlap-v2-plan-2026-10-23.md'\nV1_RESULT = 'experiments/qlib/asset-expansion-2026-raw-overlap-results-v1.json'")
        expected=expected.replace("'tests/test_asset_expansion_raw_horizon_inventory.py')",
            "'tests/test_asset_expansion_raw_horizon_inventory.py',\n           'scripts/inventory_asset_expansion_raw_horizon_v2.py',\n           'tests/test_asset_expansion_raw_horizon_inventory_v2.py')")
        expected=expected.replace("('dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividReserveToStockPs')",
            "('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs')")
        expected=expected.replace('FROZEN_ASSET_EXPANSION_ALL47_RAW_OVERLAP_CHECK','FROZEN_ASSET_EXPANSION_ALL47_RAW_OVERLAP_CHECK_V2')
        expected=expected.replace("'asset-expansion-raw-overlap-20261023'","'asset-expansion-raw-overlap-v2-20261023'")
        expected=expected.replace('{INVENTORY,TARGET,SUMMARY,AUDIT,PLAN}', '{INVENTORY,TARGET,SUMMARY,AUDIT,PLAN,V1_RESULT}')
        self.assertEqual((root/'scripts/inventory_asset_expansion_raw_horizon_v2.py').read_text(),expected)
