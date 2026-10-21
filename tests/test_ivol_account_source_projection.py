"""Synthetic source projection authentication; no real packets or compilation."""
import copy
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stock_rsi.data import digest


class IvolSourceProjectionTests(unittest.TestCase):
    def api(self):
        return importlib.import_module('scripts.prepare_ivol_account_sources_pre2026')

    def fixture(self):
        row={'code':'sh.600001','dividPlanDate':'2024-06-07','dividRegistDate':'2024-06-13',
             'dividOperateDate':'2024-06-14','dividPayDate':'2024-06-14','dividStockMarketDate':'2024-06-14',
             'dividCashPsBeforeTax':'.2','dividStocksPs':'0','dividReserveToStockPs':'.1'}
        proof={'verified_exempt':True,'source_file':'a.pdf','source_sha256':'a'*64,
               'evidence':'limited original literal'}
        doc={'instrument':'SH600001','day':'2024-06-07','file':'a.pdf','sha256':'a'*64}
        manifest={'documents':[doc],'capital_tax':{'SH600001|2024-06-14':proof}}
        candidate={'event_key':'SH600001|2024-06-14','proof_type':'capital_tax',
                   'reviewed_manifest':'/cache/one/reviewed-manifest.json','reviewed_manifest_sha256':'b'*64,
                   'proof_literal':copy.deepcopy(proof),'pdf_path':'/cache/one/a.pdf','pdf_sha256':'a'*64}
        inventory={'proof_candidates':[candidate],'lifecycle_candidates':[]}
        proposal={'documents':[],'primary_event_component_contract':'PRIMARY_EVENT_COMPONENT_COMPLETION_V1',
                  'primary_event_components':{},'supplementary_distributions':[],
                  'capital_tax':{},'stock_dividend_tax_bases':{},'cash_overrides':{}}
        packets={'SH600001':{'instrument':'SH600001','distributions':[row]}}
        seen=[]
        def authenticate(path,h):seen.append((str(path),h))
        def read(path):return copy.deepcopy(manifest)
        return inventory,proposal,packets,read,authenticate,seen

    def test_first_registered_proof_literal_preserved_all_aliases(self):
        m=self.api();i,p,raw,read,auth,seen=self.fixture();alias=copy.deepcopy(i['proof_candidates'][0])
        alias['reviewed_manifest']='/cache/two/reviewed-manifest.json';alias['pdf_path']='/cache/two/a.pdf'
        i['proof_candidates'].append(alias);before=copy.deepcopy((i,p,raw))
        result,receipts=m.build_effective_proofs(i,p,raw,read,auth)
        self.assertEqual(result['capital_tax']['SH600001|2024-06-14'],i['proof_candidates'][0]['proof_literal'])
        self.assertEqual(len(receipts[0]['aliases']),2);self.assertEqual(receipts[0]['chosen_inventory_index'],0)
        self.assertEqual((i,p,raw),before);self.assertEqual(len(seen),4)

    def test_cached_literal_mutation_and_conflicting_alias_rejected(self):
        m=self.api()
        for change in ('literal','economics'):
            i,p,raw,read,auth,seen=self.fixture()
            if change=='literal':i['proof_candidates'][0]['proof_literal']['evidence']='rewritten'
            else:
                alias=copy.deepcopy(i['proof_candidates'][0]);alias['proof_literal']['verified_exempt']=False
                i['proof_candidates'].append(alias)
            with self.subTest(change=change),self.assertRaises(ValueError):m.build_effective_proofs(i,p,raw,read,auth)

    def test_supplement_alias_decimal_format_equivalent_not_literal_rewrite(self):
        m=self.api();a={'instrument':'SZ002508','record':{'code':'sz.002508','dividPlanDate':'2024-01-03',
          'dividRegistDate':'2024-01-09','dividOperateDate':'2024-01-10','dividPayDate':'2024-01-10',
          'dividStockMarketDate':'','dividCashPsBeforeTax':'0.5','dividStocksPs':'0','dividReserveToStockPs':'0'}}
        b=copy.deepcopy(a);b['record']['dividCashPsBeforeTax']='0.50';b['record']['dividCashStock']='other metadata'
        self.assertEqual(m.proof_economics('primary_cash_supplement',a),m.proof_economics('primary_cash_supplement',b))
        b['record']['dividCashPsBeforeTax']='0.497403'
        self.assertNotEqual(m.proof_economics('primary_cash_supplement',a),m.proof_economics('primary_cash_supplement',b))

    def test_document_filename_collision_and_issuer_mismatch_rejected(self):
        m=self.api();docs={};m.add_document(docs,{'file':'a.pdf','sha256':'a'*64,'instrument':'SH600001','day':'2024-06-07'})
        for field,value in [('sha256','b'*64),('instrument','SH600002'),('day','2024-06-08'),('file','../a.pdf')]:
            d={'file':'a.pdf','sha256':'a'*64,'instrument':'SH600001','day':'2024-06-07'};d[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.add_document(docs,d)

    def test_primary_new_tax_upgrade_and_vendor_supplement_duplicate_rejected(self):
        m=self.api();i,p,raw,read,auth,seen=self.fixture();p['capital_tax']={'SH600001|2024-06-14':{'verified_exempt':True}}
        with self.assertRaises(ValueError):m.build_effective_proofs(i,p,raw,read,auth)
        p['capital_tax']={};p['supplementary_distributions']=[{'instrument':'SH600001','record':raw['SH600001']['distributions'][0]}]
        with self.assertRaises(ValueError):m.build_effective_proofs(i,p,raw,read,auth)

    def test_tracked_hash_recheck_uses_actual_bytes_and_refuses_traversal(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a').write_text('original');watched={};h=m.file_sha(root/'a')
            m.authenticate(root/'a',h,watched);(root/'a').write_text('changed')
            with self.assertRaises(ValueError):m.recheck_inputs(watched)
            with self.assertRaises(ValueError):m.bound_path(root,'../outside')

    def test_preflight_never_calls_compiler_or_creates_output(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'load_inputs',return_value={'input_sha256':{}}),patch.object(m,'compile_inputs',side_effect=AssertionError('must not compile')):
            out=Path(temp)/m.OUTPUT
            self.assertEqual(m.main(['--source-root',temp,'--request','dummy','--expected-request-sha256','a'*64,'--source-preflight-only']),0)
            self.assertFalse(out.exists())

    def test_existing_or_wrong_output_refused_before_load(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'load_inputs',side_effect=AssertionError('must not load')):
            root=Path(temp);out=root/m.OUTPUT;out.mkdir()
            args=['--source-root',temp,'--request','dummy','--expected-request-sha256','a'*64]
            with self.assertRaises(ValueError):m.main(args)
            with self.assertRaises(ValueError):m.main(args+['--output-dir',str(root/'wrong')])

    def test_compiled_tax_unknown_set_and_receipt_pairing_rejected(self):
        m=self.api()
        with self.assertRaises(ValueError):m.validate_compiled([],[],{},expected_count=1,expected_unknown=set())

    def test_initial_listing_anchor_only_removed_from_coverage_copy(self):
        m=self.api();a={'code':'sh.600001','dividOperateDate':'2024-01-02','foreAdjustFactor':'.9','backAdjustFactor':'1','adjustFactor':'1'}
        raw={'SH600001':{'bars':[{'date':'2024-01-02','close':'10','preclose':'10'}],'adjustments':[a],'distributions':[],'quarantine':[]}}
        initial=[{'instrument':'SH600001','effective_date':'2024-01-02','source_adjustment':copy.deepcopy(a),'primary_document_sha256':'a'*64,'classification':'INITIAL_LISTING_NORMALIZATION_NOT_DISTRIBUTION','factor_used_to_infer_cash_or_shares':False}]
        life={'SH600001':{'kind':'LISTING_BEGIN','effective_date':'2024-01-02','verified_primary_boundary':True,'primary_document_sha256':'a'*64}}
        before=copy.deepcopy(raw);view=m.coverage_view(raw,[],initial,life)
        self.assertEqual(view['SH600001']['adjustments'],[]);self.assertEqual(raw,before)
        initial[0]['source_adjustment']['backAdjustFactor']='2'
        with self.assertRaises(ValueError):m.coverage_view(raw,[],initial,life)

if __name__=='__main__':unittest.main()
