"""Synthetic bounded capture tests: no SDK dependency, network, or real prices."""
import copy
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS
from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file


class Response:
    def __init__(self, fields, rows, error='0'):
        self.fields, self.rows, self.error_code, self.error_msg = fields, rows, error, 'synthetic'
        self.index = -1
    def next(self):
        self.index += 1
        return self.index < len(self.rows)
    def get_row_data(self): return self.rows[self.index]


class SDK:
    def __init__(self, *, bad=False, login='0', logout='0', interrupt=False):
        self.bad, self.login_code, self.logout_code, self.interrupt = bad, login, logout, interrupt
        self.calls = []
    def login(self):
        self.calls.append(('login',))
        return SimpleNamespace(error_code=self.login_code, error_msg='synthetic login')
    def logout(self):
        self.calls.append(('logout',))
        return SimpleNamespace(error_code=self.logout_code, error_msg='synthetic logout')
    def query_history_k_data_plus(self, code, fields, **kw):
        self.calls.append(('daily', code, kw))
        if self.interrupt: raise KeyboardInterrupt('synthetic interruption')
        if self.bad: raise OSError('synthetic transport failure')
        return Response(BAR_FIELDS, [['2023-12-29', code, '10', '11', '9', '10', '10', '10000', '100000', '3', '1', '0']])
    def query_dividend_data(self, code, **kw):
        self.calls.append(('dividend', code, kw)); return Response(DIVIDEND_FIELDS, [])
    def query_adjust_factor(self, code, **kw):
        self.calls.append(('adjustments', code, kw)); return Response(ADJUST_FIELDS, [])


class LowMarketResidualRawTests(unittest.TestCase):
    def api(self):
        try: return importlib.import_module('scripts.capture_low_market_residual_vol_raw_pre2026')
        except ModuleNotFoundError: self.fail('new bounded pre2026 capture wrapper is missing')
    def context(self, tmp, fresh=4):
        origin=Path(tmp)/'original.json';origin.write_text('{"immutable":"input"}\n')
        auth={'sessions':['2023-12-29','2024-01-02','2025-12-31'], 'reuse_routes':{},
              'known_hashes':{str(origin):sha256_file(origin)}}
        r={'codes':[f'SH600{n:03d}' for n in range(fresh)],'fresh_codes':[f'SH600{n:03d}' for n in range(fresh)],
           'maximum_new_query_reservations':4*fresh,'target_sha256':'a'*64}
        return r,auth,origin
    def run_capture(self, api, tmp, sdk, fresh=4):
        r,a,origin=self.context(tmp,fresh);out=Path(tmp)/api.OUTPUT
        with patch.object(api.socket,'setdefaulttimeout'):
            rc=api.capture(r,a,out,sdk,request_bytes=b'{}\n',request_sha='b'*64)
        return rc,out,r,a,origin
    def scope(self, api):
        codes=[f'SH{600000+n}' for n in range(361)]
        return {'status':'FROZEN_LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCE_REQUEST','candidate':'low_market_residual_vol_1m',
            'window':['2023-12-29','2025-12-31'],'codes':codes,'reuse_routes':dict.fromkeys(codes[:301],{}),
            'fresh_codes':codes[301:],'reuse_sources':[{'directory':n} for n in api.SOURCE_NAMES],
            'maximum_new_query_reservations':240,'max_attempts_per_query':1,'maximum_consecutive_failed_fresh_codes':3,
            'maximum_administrative_login_attempts':1,'socket_timeout_seconds':20,'baostock_version':'0.9.4',
            'target_sha256':api.TARGET_SHA,'protocol_file':api.PROTOCOL,'reference_calendar_file':api.REFERENCE_CALENDAR,
            'method_code_sha256':dict.fromkeys(api.METHOD_FILES,'a'*64),'screen_files_sha256':dict.fromkeys(api.SCREEN_FILES,'a'*64),
            'immutable_financial_sha256':dict.fromkeys(api.FINANCIAL_FILES,'a'*64)}
    def test_fixed_budget_and_binding_scope_cannot_widen_or_drop_old_financial_evidence(self):
        api=self.api();r=self.scope(api);api.check_scope(r)
        for key,value in [('maximum_new_query_reservations',241),('max_attempts_per_query',2),
                ('maximum_administrative_login_attempts',2),('maximum_consecutive_failed_fresh_codes',4),
                ('socket_timeout_seconds',21),('baostock_version','other'),('window',['2023-12-29','2026-01-01']),
                ('method_code_sha256',{}),('screen_files_sha256',{}),('immutable_financial_sha256',{})]:
            changed=copy.deepcopy(r);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):api.check_scope(changed)
    def auth_fixture(self, api, tmp):
        from datetime import date,timedelta
        repo=Path(tmp)/'repo';source=Path(tmp)/'source';repo.mkdir();source.mkdir();r=self.scope(api)
        def save(path,x):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,sort_keys=True)+'\n');return sha256_file(path)
        sessions=[(date(2023,12,29)+timedelta(days=n)).isoformat() for n in range(485)]+['2025-12-31']
        reference=source/api.REFERENCE_CALENDAR;reference.parent.mkdir(parents=True);reference.write_text('\n'.join(sessions)+'\n');r['reference_calendar_sha256']=sha256_file(reference)
        targets={f'{y}-{m:02d}-02':{'as_of':f'{y}-{m:02d}-01','weights':dict.fromkeys(r['codes'],.95/361)} for y in (2024,2025) for m in range(1,13)}
        targetpath=source/api.ACCOUNT/'targets.json';r['target_sha256']=save(targetpath,{api.CANDIDATE:targets})
        r['method_code_sha256']={n:save(repo/n,{'synthetic_method':n}) for n in api.METHOD_FILES}
        r['protocol_sha256']=save(repo/api.PROTOCOL,{'synthetic_protocol':True})
        r['immutable_financial_sha256']={n:save(source/api.ACCOUNT/n,{'synthetic_financial':n}) for n in api.FINANCIAL_FILES}
        results={}
        for n,h in r['immutable_financial_sha256'].items():
            label,file=n.rsplit('/',1);results.setdefault(label,{'artifact_sha256':{}})['artifact_sha256'][file]=h
        summary={'results_by_extra_bps_and_family':results,'selected_development_lead':api.CANDIDATE,'targets_sha256':r['target_sha256']}
        summaryhash=save(source/api.ACCOUNT/'summary.json',summary)
        audit={'status':'PASS_INDEPENDENT_BUDGETED_PRE2026_CSV_ACCOUNT_AUDIT','summary_sha256':summaryhash,'critical_or_important_audit_findings':[],
            'selected_development_lead':api.CANDIDATE,'2026_market_data_read':False,'financial_artifact_hashes_verified':r['immutable_financial_sha256']}
        ah=save(repo/api.SCREEN_FILES[1],audit)
        result={'actual_summary_sha256':summaryhash,'independent_audit_sha256':ah};rh=save(repo/api.SCREEN_FILES[0],result)
        verification={'result_sha256':rh,'independent_audit_sha256':ah,'status':'PRE2026_NORMALIZED_DAILY_GATE_PASS_REQUIRES_RAW_SHARE_CONFIRMATION'}
        vh=save(repo/api.SCREEN_FILES[2],verification);r['screen_files_sha256']=dict(zip(api.SCREEN_FILES,(rh,ah,vh)))
        routes={};sources=[]
        for j,name in enumerate(api.SOURCE_NAMES):
            d=source/name;ch=save(d/'calendar.json',{'sessions':sessions});ph={}
            if j==0:
                for c in r['codes'][:301]:
                    bars=[dict(zip(BAR_FIELDS,[day,c[:2].lower()+'.'+c[2:],'10','11','9','10','10','10000','100000','3','1','0'])) for day in sessions]
                    packet={'instrument':c,'window':r['window'],'bars':bars,'distributions':[],'adjustments':[],'quarantine':[]}
                    h=save(d/'codes'/(c+'.json'),packet);ph[c]=h
                    routes[c]={'directory':name,'file':name+'/codes/'+c+'.json','packet_sha256':h,'raw_core_sha256':api._core(packet)}
            mh=save(d/'manifest.json',{'window':r['window'],'calendar_sha256':ch,'per_code_sha256':ph})
            anchor='experiments/qlib/synthetic-source-audit-'+str(j)+'.json';anchorhash=save(repo/anchor,{'synthetic_source_audit':name})
            sources.append({'directory':name,'manifest_sha256':mh,'calendar_sha256':ch,'audit_anchor':{'file':anchor,'sha256':anchorhash}})
        r['reuse_sources']=[{k:v for k,v in item.items() if k!='audit_anchor'} for item in sources];r['reuse_routes']=routes
        inv={'target_sha256':r['target_sha256'],'target_union_names':361,'fully_covered_reuse_names':301,'cross_cache_normalized_raw_core_conflicts':[],
            'selected_reuse':routes,'missing_or_incomplete_instruments':r['fresh_codes'],'source_directories_checked':sources,'per_instrument':{c:{'all_registered_pre2026_cache_options':[dict(v,complete_486_session_calendar=True)]} for c,v in routes.items()}}
        r['inventory_sha256']=save(repo/api.INVENTORY,inv)
        r['mandatory_snapshot_inventory_sha256']=save(repo/api.MANDATORY,{'inventory_sha256':r['inventory_sha256'],'target_sha256':r['target_sha256'],
            'known_conflict_snapshots':0,'covered_snapshots':1478,'unknown_snapshots':362,'unknown_treated_as_pass':False})
        return source,repo,r,targetpath
    def test_authenticate_checks_actual301_packets_and42_audited_financial_bytes(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            source,repo,r,t=self.auth_fixture(api,d)
            with patch.object(api,'TARGET_SHA',r['target_sha256']),patch.object(api,'version',return_value='0.9.4'):
                auth=api.authenticate(source,repo,r,t);self.assertEqual(len(auth['reuse_routes']),301)
                anchor=repo/'experiments/qlib/synthetic-source-audit-0.json';before=anchor.read_bytes();anchor.write_text('changed audit')
                with self.assertRaises(ValueError):api.authenticate(source,repo,r,t)
                anchor.write_bytes(before)
                p=source/api.ACCOUNT/'40/low_market_residual_vol_1m/days.csv';p.write_text('tampered')
                with self.assertRaises(ValueError):api.authenticate(source,repo,r,t)
                with self.assertRaises(ValueError):api.verify_known_hashes(auth['known_hashes'])
    def test_existing_output_rejects_before_request_or_source_read(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/api.OUTPUT;out.mkdir()
            with self.assertRaisesRegex(ValueError,'existing'),patch.object(api,'authenticate',side_effect=AssertionError('source read')):
                api.main(['--request','absent','--expected-request-sha256','0'*64,'--targets','absent','--source-root',d,'--output-dir',str(out)])
    def test_external_checksum_and_source_preflight_do_not_create_or_connect(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'request.json';p.write_text('{}');out=Path(d)/api.OUTPUT
            args=['--request',str(p),'--expected-request-sha256','0'*64,'--targets','absent','--source-root',d,'--output-dir',str(out),'--source-preflight-only']
            with self.assertRaises(ValueError):api.main(args)
            self.assertFalse(out.exists())
            args[3]=sha256_file(p)
            with patch.object(api,'authenticate',return_value={'sessions':[],'reuse_routes':{},'known_hashes':{}}),patch.object(api,'version',return_value='0.9.4'),patch.object(api,'load_sdk',side_effect=AssertionError('SDK import')):
                self.assertEqual(api.main(args),0)
            self.assertFalse(out.exists())
    def test_partial_calendar_is_saved_with_four_receipts_but_not_admitted(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            sdk=SDK();rc,out,_,_,_=self.run_capture(api,d,sdk,fresh=1)
            self.assertEqual(rc,0);m=json.loads((out/'manifest.json').read_text());self.assertTrue(m['capture_complete']);self.assertFalse(m['all_source_calendars_complete']);self.assertFalse(m['admitted_for_account_replay'])
            self.assertEqual(m['query_reservations_consumed'],4);self.assertEqual(m['calendar_diagnostics']['SH600000']['missing_sessions'],['2024-01-02','2025-12-31'])
            packet=json.loads((out/'codes/SH600000.json').read_text());self.assertEqual(len(packet['source_query_receipts']),4);self.assertEqual([x[0] for x in sdk.calls],['login','daily','dividend','dividend','adjustments','logout'])
    def test_login_failure_records_terminal_partial_manifest_without_query_or_retry(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            sdk=SDK(login='1001');rc,out,_,_,_=self.run_capture(api,d,sdk)
            self.assertNotEqual(rc,0);m=json.loads((out/'manifest.json').read_text());self.assertFalse(m['capture_complete']);self.assertEqual(m['query_reservations_consumed'],0);self.assertEqual(len(m['pending_codes']),4)
            self.assertEqual(json.loads((out/'login-response-1.json').read_text())['error_code'],'1001');self.assertEqual([x[0] for x in sdk.calls],['login','logout']);self.assertTrue((out/'terminal-error.json').exists())
    def test_three_failed_codes_stop_with_consumed_reservations_and_no_retry(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            sdk=SDK(bad=True);rc,out,_,_,_=self.run_capture(api,d,sdk)
            m=json.loads((out/'manifest.json').read_text());self.assertNotEqual(rc,0);self.assertEqual(len(m['errors_sha256']),3);self.assertEqual(m['pending_codes'],['SH600003']);self.assertEqual(m['query_reservations_consumed'],3);self.assertTrue((out/'stopped.json').exists())
            self.assertEqual(len(list(out.glob('queries/*/response-1.json'))),3);self.assertFalse(list(out.glob('queries/*/reserved-2.json')))
    def test_interruption_preserves_unanswered_reservation_cleanup_and_terminal_manifest(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            sdk=SDK(interrupt=True);rc,out,_,_,_=self.run_capture(api,d,sdk)
            m=json.loads((out/'manifest.json').read_text());self.assertNotEqual(rc,0);self.assertEqual(m['query_reservations_consumed'],1);self.assertFalse(m['capture_complete']);self.assertTrue((out/'cleanup.json').exists());self.assertTrue((out/'terminal-error.json').exists());self.assertEqual(sdk.calls[-1][0],'logout')
    def test_logout_failure_and_postcheck_mutation_cannot_report_complete(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            rc,out,_,_,_=self.run_capture(api,d,SDK(logout='2001'),fresh=1)
            self.assertNotEqual(rc,0);self.assertFalse(json.loads((out/'manifest.json').read_text())['capture_complete'])
        with tempfile.TemporaryDirectory() as d:
            r,a,origin=self.context(d,1);sdk=SDK();old=sdk.logout
            def logout():origin.write_text('changed');return old()
            sdk.logout=logout
            with patch.object(api.socket,'setdefaulttimeout'):rc=api.capture(r,a,Path(d)/api.OUTPUT,sdk,request_bytes=b'{}',request_sha='b'*64)
            self.assertNotEqual(rc,0);self.assertFalse(json.loads((Path(d)/api.OUTPUT/'input-postcheck.json').read_text())['source_inputs_unchanged_after_capture'])
    def test_reuse_copy_preserves_exact_bytes_and_avoids_financial_queries(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            r,a,_=self.context(d,0);p=Path(d)/'reuse.json';packet={'instrument':'SH600000','window':['2023-12-29','2025-12-31'],'bars':[dict(zip(BAR_FIELDS,['2023-12-29','sh.600000','10','11','9','10','10','10000','100000','3','1','0']))],'distributions':[],'adjustments':[],'quarantine':[]};p.write_text(json.dumps(packet,indent=3)+'\n')
            r['codes']=['SH600000'];a['reuse_routes']={'SH600000':{'path':str(p),'packet_sha256':sha256_file(p)}};a['known_hashes'][str(p)]=sha256_file(p);sdk=SDK()
            with patch.object(api.socket,'setdefaulttimeout'):rc=api.capture(r,a,Path(d)/api.OUTPUT,sdk,request_bytes=b'{}',request_sha='b'*64)
            self.assertEqual(rc,0);self.assertEqual((Path(d)/api.OUTPUT/'codes/SH600000.json').read_bytes(),p.read_bytes());self.assertEqual(sdk.calls,[])

if __name__=='__main__':unittest.main()
