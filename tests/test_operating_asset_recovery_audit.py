import ast
import copy
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from scripts import audit_operating_asset_recovery as audit
except ImportError:
    audit=None
from tests import test_operating_asset_recovery as fixtures
from stock_rsi.data import digest


def rehash(case):
    record=case['source_record'];asset=record['payload']['asset_bridge'];asset['record_id']=digest({k:v for k,v in asset.items() if k!='record_id'})
    case['asset_bridge']=copy.deepcopy(asset)
    record['record_id']=digest({k:v for k,v in record.items() if k!='record_id'});case['effective_record_id']=record['record_id']


class OperatingAssetRecoveryAuditTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(audit,'independent source recovery checker missing')
        self.harness=fixtures.OperatingAssetRecoveryTests();self.harness.setUp();self.addCleanup(self.harness.doCleanups)
        from scripts import recover_operating_assets as build
        self.build=build;self.doc=self.harness.docs[0]
        with patch.object(build,'extract_geometry',side_effect=self.harness.geometry_reader):self.case=build.inspect_one(str(self.harness.base),self.doc,build.geometry.NORMATIVE_BASIS)
        self.geometry=self.case.pop('geometry_pages');key=self.doc['capture_key']
        self.texts=build.read(self.harness.base/build.INITIAL_CACHE/(key+'.pages.json'))['pages']
        self.original={'operating':self.harness.original[key],'GP':build.read(self.harness.base/build.GP_OUTPUT/(key+'.json'))}

    def check(self,case=None,texts=None):return audit.check_case(texts or self.texts,self.geometry,self.doc,self.original,case or self.case)

    def test_all_source_cells_checked_and_new_producer_imports_are_forbidden(self):
        self.assertEqual(self.check(),15)
        for node in ast.walk(ast.parse(inspect.getsource(audit))):
            if isinstance(node,ast.ImportFrom):self.assertNotIn(node.module,('stock_rsi.asset_geometry','stock_rsi.operating_source_bridge','scripts.recover_operating_assets'))

    def test_rehashed_amount_date_adjustment_and_normative_forgeries_rejected(self):
        for mode in ('amount','date','adjustment','normative'):
            case=copy.deepcopy(self.case);asset=case['source_record']['payload']['asset_bridge']
            if mode=='amount':asset['prior']['value_CNY']=asset['columns_by_year']['2022'][0]['value_CNY']='900.00'
            elif mode=='date':asset['prior']['fiscal_end']=asset['columns_by_year']['2022'][0]['fiscal_end']='2021-12-31'
            elif mode=='adjustment':asset['prior']['adjustment']=asset['columns_by_year']['2022'][0]['adjustment']='AFTER_ADJUSTMENT'
            else:asset['normative_basis']['body_sha256']='f'*64
            rehash(case)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.check(case)

    def test_parent_unit_borrow_and_original_row_edit_are_not_hidden_by_rehash(self):
        texts=copy.deepcopy(self.texts);texts[4]+='单位：万元 币种：人民币\n';case=copy.deepcopy(self.case)
        cell=case['source_record']['payload']['income']['2023-12-31']['administrative_expenses']
        cell.update(unit='万元',unit_evidence_page=5,unit_evidence_literal='单位：万元 币种：人民币',multiplier_CNY='10000',value_CNY='-50000.00');rehash(case)
        with self.assertRaises(ValueError):self.check(case,texts)
        texts=copy.deepcopy(self.texts);texts[3]=texts[3].replace('管理费用 七、64 -5.00 2.00','管理费用 七、64 -50.00 2.00')
        with self.assertRaises(ValueError):self.check(texts=texts)

    def test_separate_coverage_check_preserves_original_selected_witnesses(self):
        original={'classifications':[{'instrument':'SH600001','annual_status':'NO_VISIBLE_ANNUAL_REPORT'},
            {'instrument':'SH600002','annual_status':'LATEST_OPERATING_SOURCE_SCHEMA_UNSUPPORTED','selected_capture_key':'x','selected_source_sha256':'a'*64}]}
        cases={'x':{'capture_key':'x','instrument':'SH600002','source_sha256':'a'*64,'effective_source_status':'STILL_UNSUPPORTED','effective_record_id':None}}
        new=copy.deepcopy(original);new.update(source_only_no_monetary_values_exposed=True,investment_factor_admitted=False,historical_arrival_verified=False,operating_ratios_or_portfolio_returns_computed=False)
        new['classifications'][0]['effective_source_status']='NO_VISIBLE_ANNUAL_REPORT';new['classifications'][1].update(effective_source_status='STILL_UNSUPPORTED',effective_record_id=None)
        self.assertEqual(audit.check_coverage(original,new,cases),2)
        new['classifications'][1]['selected_capture_key']='older'
        with self.assertRaises(ValueError):audit.check_coverage(original,new,cases)

    def test_rehashed_source_origin_and_original_failure_history_cannot_be_rewritten(self):
        for mode in ('asset_origin','income_origin','history'):
            case=copy.deepcopy(self.case)
            if mode=='history':case['original_error']=None
            else:case['source_record']['payload'][mode]='PARENT_OR_OTHER_SOURCE'
            rehash(case)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.check(case)

    def test_recovered_record_requires_nonnull_validated_asset_evidence(self):
        case=copy.deepcopy(self.case);case['asset_bridge']=case['source_record']['payload']['asset_bridge']=None
        record=case['source_record'];record['record_id']=digest({k:v for k,v in record.items() if k!='record_id'});case['effective_record_id']=record['record_id']
        with self.assertRaises(ValueError):self.check(case)

    def test_rehashed_evidence_boundary_flags_remain_false(self):
        for owner,flag in (('record','historical_arrival_verified'),('record','financial_cross_issuer_comparability_verified'),
                           ('asset','historical_arrival_verified'),('case','historical_arrival_verified'),('case','investment_factor_admitted')):
            case=copy.deepcopy(self.case)
            target=case['source_record'] if owner=='record' else case['source_record']['payload']['asset_bridge'] if owner=='asset' else case
            target[flag]=True;rehash(case)
            with self.subTest(owner=owner,flag=flag),self.assertRaises(ValueError):self.check(case)

    def test_coverage_cannot_claim_unproven_historical_arrival_or_investment(self):
        old={'classifications':[]}
        new={**old,'source_only_no_monetary_values_exposed':True,'investment_factor_admitted':False,
             'historical_arrival_verified':False,'operating_ratios_or_portfolio_returns_computed':False}
        self.assertEqual(audit.check_coverage(old,new,{}),0)
        for flag in ('historical_arrival_verified','investment_factor_admitted','operating_ratios_or_portfolio_returns_computed'):
            changed={**new,flag:True}
            with self.subTest(flag=flag),self.assertRaises(ValueError):audit.check_coverage(old,changed,{})

    def test_independent_request_scope_rejects_supported_subset_or_changed_budget(self):
        root=Path(__file__).resolve().parents[1]
        old=json.loads((root/'experiments/qlib/operating-corpus-source-request.json').read_text())
        inventory=json.loads((root/'experiments/qlib/operating-lagged-asset-date-inventory.json').read_text())
        keys={r['capture_key'] for r in inventory['rows']}
        originals={d['capture_key']:{'error':'same-edition explicitly dated prior December31 assets required' if d['capture_key'] in keys else None} for d in old['documents']}
        req={**old,'status':'FROZEN_BEFORE_COMPLETE_OPERATING_ASSET_SOURCE_RECOVERY','output_subdir':'operating-asset-recovery-source-v1-20261023',
            'target_count':339,'targets':[d['capture_key'] for d in old['documents'] if d['capture_key'] in keys],
            'runtime_python':'3.12.14','pdfplumber_version':'0.11.9','workers':4,'maximum_outstanding_documents':4,
            'geometry_pages_per_target':5,'geometry_pages_per_pass':1695,'cached_search_first_pages':20,'maximum_nonoverlapping_two_page_windows':2,
            'network_permitted':False,'factor_ratio_rank_or_return_permitted':False,'2026_financial_or_market_values_permitted':False,
            'normative_basis':self.build.geometry.basis()}
        audit.check_scope(req,old,originals,inventory)
        for mode in ('targets','documents','cohort','budget','ratio'):
            changed=copy.deepcopy(req)
            if mode in ('targets','documents','cohort'):changed[mode]=changed[mode][:-1]
            elif mode=='budget':changed['geometry_pages_per_target']=6
            else:changed['factor_ratio_rank_or_return_permitted']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):audit.check_scope(changed,old,originals,inventory)


if __name__=='__main__':unittest.main()
