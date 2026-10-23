import copy
import importlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import date
from tests import test_asset_expansion_raw_extension as fixtures


class AssetReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.m=importlib.import_module('scripts.reconstruct_asset_expansion_raw_horizon')
        self.f=fixtures.AssetExtensionTests();self.f.setUp()
        self.proof={'kind':'DELISTING_END','effective_date':'2026-10-21',
            'verified_primary_boundary':True,'primary_document_sha256':'a'*64}

    def test_full_source_reconstruction_is_unchanged(self):
        packet,receipt=self.m.reconstruct_packet(self.f.code,self.f.old(),self.f.days,self.f.data())
        self.assertEqual(packet['bars'],[self.f.bar(d) for d in self.f.days])
        self.assertEqual(receipt['post_exit_sessions_not_synthesized'],0)
        self.assertEqual(receipt['active_source_sessions'],4)

    def test_verified_exit_preserves_all_actual_rows_and_classifies_only_post_exit(self):
        old=self.f.old();d=self.f.data();d['daily']['rows']=[]
        packet,receipt=self.m.reconstruct_packet(self.f.code,old,self.f.days,d,self.proof)
        self.assertEqual(packet,old)
        self.assertEqual(receipt['active_source_sessions'],3)
        self.assertEqual(receipt['post_exit_sessions_not_synthesized'],1)
        self.assertEqual(receipt['active_end'],'2026-10-20')
        bars={self.f.code:{r['date']:r for r in packet['bars']}}
        from stock_rsi.lifecycle_source_rows import source_rows_on
        rows,exceptions=source_rows_on(bars,date(2026,10,21),[],{self.f.code:self.proof})
        self.assertEqual(rows,{})
        self.assertFalse(exceptions[0]['synthetic_price_created'])
        with self.assertRaises(ValueError):source_rows_on(bars,date(2026,10,21),[self.f.code],{self.f.code:self.proof})

    def test_no_proof_unverified_boundary_or_actual_gap_never_waives_coverage(self):
        d=self.f.data();d['daily']['rows']=[]
        for proof in (None,{**self.proof,'verified_primary_boundary':False},
                      {**self.proof,'primary_document_sha256':'bad'},
                      {**self.proof,'effective_date':'2026-10-22'}):
            with self.subTest(proof=proof),self.assertRaises(ValueError):
                self.m.reconstruct_packet(self.f.code,self.f.old(),self.f.days,d,proof)
        old=self.f.old();old['bars'].pop(1)
        with self.assertRaises(ValueError):self.m.reconstruct_packet(self.f.code,old,self.f.days,d,self.proof)

    def test_post_exit_bar_or_event_is_not_dropped_or_converted_to_cash(self):
        d=self.f.data()
        with self.assertRaises(ValueError):self.m.reconstruct_packet(self.f.code,self.f.old(),self.f.days,d,self.proof)
        for component in ('dividend2026','adjustments'):
            d=self.f.data();d['daily']['rows']=[]
            if component=='dividend2026':d[component]['rows'].append([self.f.dividend('2026-10-21')[k] for k in self.f.m.DIVIDEND_FIELDS])
            else:d[component]['rows']=[['sh.600066','2026-10-21','1','1','1']]
            with self.subTest(component=component),self.assertRaises(ValueError):
                self.m.reconstruct_packet(self.f.code,self.f.old(),self.f.days,d,self.proof)

    def test_original_actions_and_literal_annual_overlap_remain_required(self):
        d=self.f.data();d['daily']['rows']=[]
        for index,value in ((9,'9'),(10,'0.090或0.1')):
            bad=copy.deepcopy(d);bad['dividend2026']['rows'][0][index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):
                self.m.reconstruct_packet(self.f.code,self.f.old(),self.f.days,bad,self.proof)

    def test_journal_chain_and_original_partial_sdk_error_cannot_be_relabelled(self):
        from scripts.fundamental_query_journal import QueryJournal,digest
        identity={'source':'BaoStock','instrument':self.f.code,'component':'daily','parameters':{'fixed':'fixture'}}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            payload,_=QueryJournal(root,max_queries=1,max_attempts=1).query(identity,lambda:self.f.envelope(self.f.data()['daily']))
            data,receipt=self.m.read_query(root,identity)
            self.assertEqual(data,self.f.data()['daily'])
            path=root/'queries'/digest(identity)/'response-1.json';r=json.loads(path.read_text())
            r['payload']['rows'][0]['iteration_error_type']='KeyboardInterrupt'
            r['payload_sha256']=digest(r['payload']);path.write_text(json.dumps(r))
            with self.assertRaises(KeyboardInterrupt):self.m.read_query(root,identity)


    def test_runner_preserves_interrupted_journal_and_original_error_through_finalization(self):
        from scripts.fundamental_query_journal import QueryJournal
        for failure in (None,'inputs-after.json','manifest.json'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as td:
                base=Path(td);raw=base/self.m.RAW;raw.mkdir();request=base/'request.json';request.write_bytes(b'fixture')
                sourcefile=base/'original';sourcefile.write_text('unchanged')
                q={'instrument':self.f.code,'component':'daily','parameters':{'fixed':'fixture'}}
                identity={'source':'BaoStock',**q,'asset_expansion_extension_request_sha256':'a'*64}
                fields,rows=self.f.envelope(self.f.data()['daily'])
                rows[0]['iteration_error_type']='KeyboardInterrupt';rows[0]['iteration_error']='fixture interrupted source'
                QueryJournal(raw,max_queries=1,max_attempts=1).query(identity,lambda:(fields,rows))
                for i in range(141):(raw/'queries'/('unused-'+str(i))).mkdir()
                r={'codes':['SH'+str(600001+i) for i in range(47)]}
                values=(r,{'query_whitelist':[q]},{'request_sha256':'a'*64},{str(sourcefile):self.m.sha(sourcefile)})
                out=base/self.m.OUTPUT;real_save=self.m.save
                def fail_one(path,value):
                    if path.name==failure:
                        path.write_text('{partial');raise OSError('fixture disk write failure')
                    return real_save(path,value)
                with patch.object(self.m,'authenticate',return_value=values),patch.object(self.m,'save',side_effect=fail_one):
                    with self.assertRaisesRegex(KeyboardInterrupt,'fixture interrupted source'):
                        self.m.execute(request,'fixture',base,base,out)
                name='finalization-error.json' if failure=='manifest.json' else 'manifest.json'
                result=json.loads((out/name).read_text())
                self.assertFalse(result['reconstruction_complete'])
                self.assertEqual(result['original_error']['error_type'],'KeyboardInterrupt')
                self.assertEqual(len(result['pending_codes']),47)
                self.assertEqual(result['per_code_sha256'],{})
                if failure:self.assertEqual(result['persistence_errors'][0]['file'],failure)
                with self.assertRaises(ValueError):self.m.execute(request,'fixture',base,base,out)


if __name__=='__main__':unittest.main()
