"""Independent review of preserved failed local admission, without ROI/network.
Reuses only a published independent audit's stdlib arithmetic pure function;
never imports production inspect/aggregate/simulate functions.
"""
from pathlib import Path
from datetime import datetime
from collections import Counter
import copy,hashlib,importlib.util,json,subprocess
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
O=B/'price-delay-minute-admission-20261021';C=B/'price-delay-minutes-dev-20261021'
P=R/'experiments/qlib/price-delay-minute-admission-plan.json'
REPORT=Path('/tmp/price-delay-minute-admission-independent-audit-20261021.json')
EXPECTED='cc70219562042601e1454398d28957411f756fe0417c1f11db72c0a4760ff1c2'
REF=R/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-minute-admission-audit.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(v,s):
    if not v:raise AssertionError(s)
def main():
    plan=read(P);actual=read(O/'summary.json');actualdetails=read(O/'details.json');freeze=subprocess.check_output(['git','rev-parse','1368705'],cwd=R,text=True).strip()
    need(sha(P)==EXPECTED==actual['plan_sha256'] and hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(P.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen admission plan')
    need(plan['status']=='FROZEN_PRICE_DELAY_PRE2026_MINUTE_SOURCE_ADMISSION' and plan['candidate']=='price_delay_d1' and plan['window']==['2024-01-02','2025-12-31'] and plan['network_calls_permitted']==0 and plan['required_active_sessions']==2502 and plan['fixed_reused_pairs']==1584 and plan['exact_fresh_reservations']==918,'bounded fixed scope')
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,h in plan[field].items():
            need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(root/n)==h,'bound input '+n)
            if root==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen blob '+n)
    cpfile=R/'experiments/qlib/price-delay-minute-capture-plan.json';rqfile=R/'experiments/qlib/price-delay-minute-gap-identities.json';afile=R/'experiments/qlib/price-delay-minute-capture-independent-audit.json'
    cp=read(cpfile);request=read(rqfile);captureaudit=read(afile);manifest=read(C/'manifest.json');scope=read(C/'price-delay-scope.json');cleanup=read(C/'client_cleanup.json')
    need(set(plan['method_code_sha256'])==set(cp['method_code_sha256'])|{'scripts/admit_price_delay_minutes_pre2026.py'},'complete12 methods')
    need(sha(cpfile)==plan['capture_plan_sha256']==sha(C/'plan.json')==captureaudit['capture_plan_sha256'] and sha(rqfile)==plan['request_sha256']==sha(C/'request.json')==captureaudit['request_sha256'],'capture plan/request bytes')
    need(sha(C/'manifest.json')==plan['capture_manifest_sha256']==captureaudit['capture_manifest_sha256'] and sha(C/'price-delay-scope.json')==captureaudit['scope_sha256'],'actual capture scope hash')
    need(captureaudit['imports_project_code'] is False and captureaudit['capture_fully_recorded'] is True and captureaudit['captured_packets']==2502 and manifest['complete_capture'] is True and manifest['abnormal_exit'] is None and manifest['stopped_after_consecutive_source_failures'] is False,'bound complete technical capture')
    need(cleanup=={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]} and scope['cleanup_sha256']==sha(C/'client_cleanup.json'),'complete cleanup')
    snapshot=C/('capture-snapshot-'+digest(manifest)+'.json');need(read(snapshot)==manifest and sha(snapshot)==captureaudit['legacy_snapshot_sha256'],'legacy immutable snapshot')
    queryhashes={str(p.relative_to(C)):sha(p) for p in (C/'queries').rglob('*') if p.is_file()};need(queryhashes==captureaudit['query_artifact_sha256'] and len(queryhashes)==2754,'all exact query bytes')
    reused=request['reused_session_provenance'];fresh=request['uncached_requests'];need(len(reused)==1584 and len(fresh)==918 and len(request['active_requests'])==2502 and read(C/'capture_request.json')=={'reused':reused,'fresh':fresh},'capture partition')
    projections={};expectedkeys={}
    for code,day in fresh:
        identity={'method':'minutes.history','instrument':code,'requested_day':day,'host':cp['host'],'include_raw':True};key=digest(identity);expectedkeys[key]=(code,day);q=C/'queries'/key
        need({p.name for p in q.iterdir()}=={'request.json','reserved-1.json','response-1.json'} and read(q/'request.json')==identity,'one full fresh attempt')
        reserved=read(q/'reserved-1.json');response=read(q/'response-1.json');need(reserved['identity_sha256']==response['identity_sha256']==key and reserved['attempt']==1 and response['reservation_sha256']==sha(q/'reserved-1.json') and response['status']=='CAPTURED','fresh reserve/response')
        v=response['payload'];need(response['payload_sha256']==digest(v) and v['fields']==['response'] and len(v['rows'])==1 and datetime.fromisoformat(reserved['reserved_at_utc'])<=datetime.fromisoformat(v['captured_at_utc']),'fresh SDKpayload/timing')
        projections[code+'-'+day+'.json']={'instrument':code,'requested_day':day,'status':'RESPONSE_CAPTURED','response':v['rows'][0],'observed_at':v['captured_at_utc'],'query_response_sha256':sha(q/'response-1.json'),'query_reservation_sha256':sha(q/'reserved-1.json')}
    need({p.name for p in (C/'queries').iterdir()}==set(expectedkeys),'all918queries only')
    raw=B/'price-delay-raw-dev-20261021';rm=read(raw/'manifest.json');need(sha(raw/'manifest.json')==request['raw_manifest_sha256']==actual['raw_manifest_sha256'],'raw source binding')
    bars={}
    for code,h in rm['per_code_sha256'].items():
        p=raw/'codes'/(code+'.json');need(sha(p)==h,'151source packet unchanged');v=read(p);need(v['instrument']==code and v['window']==['2023-12-29','2025-12-31'] and all(r['date']<='2025-12-31' for r in v['bars']),'physicalpre2026');bars[code]={r['date']:r for r in v['bars']}
    target=B/'price-delay-pre2026-formations-20261021/targets.json';need(sha(target)==request['target_sha256']==rm['target_sha256']==actual['target_sha256'],'targets unchanged');targets=read(target)['price_delay_d1']
    need(len(targets)==24 and len(bars)==151,'complete targets/source')
    need(sha(REF)==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REF.relative_to(R))],cwd=R)).hexdigest(),'published arithmetic reference frozen')
    spec=importlib.util.spec_from_file_location('independent_minute_arithmetic_reference',REF);reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    # The reference module contains stdlib only; invoke reconstruct, never its
    # unrelated workflow/preflight/main. Production inspectors are not imported.
    expectedrows=[];windows_hashes=[];evidenceids=[];rejections=[];exact=nearest=0;packets={};firstordinary=None
    for code,day in request['active_requests']:
        need('2024-01-02'<=day<='2025-12-31','pre2026 sample');name=code+'-'+day+'.json';p=C/'sessions'/name;h=manifest['per_session_sha256'][name];need(sha(p)==h==captureaudit['all2502_packet_sha256'][name],'packet SHA');packet=read(p);packets[name]=packet
        row={'instrument':code,'day':day,'source_sha256':h}
        if name in reused:
            origin=reused[name];need((B/origin['root']/'sessions'/name).read_bytes()==p.read_bytes() and h==origin['sha256'],'original1584bytes');row['origin']=origin
        else:need(packet==projections[name],'fresh projectionexact');row['origin']='FROZEN_FRESH_QUERY'
        d=bars[code][day]
        if d['isST']!='0':
            need(code=='SZ002092' and d['isST']=='1' and d['tradestatus']=='1' and packet['status']=='RESPONSE_CAPTURED','exact ST rejection cause')
            row.update(status='SOURCE_REJECTED',error_type='ValueError',error='source security/date/ordinary active state changed')
            rejections.append({'instrument':code,'day':day,'packet_status':'RESPONSE_CAPTURED','daily_tradestatus':d['tradestatus'],'daily_isST':d['isST'],'status':'SOURCE_REJECTED','same_month_target_includes_instrument':code in targets[day]['weights'],'same_month_target_weight':targets[day]['weights'].get(code),'actual_inventory_zero_inferred':False,'source_sha256':h})
        else:
            arithmetic,windows=reference.reconstruct(code,day,packet,d);row.update(arithmetic);need(len(windows)==48,'48 independent five-minute windows');windows_hashes.append(digest(windows));evidenceids.extend(w['evidence_id'] for w in windows)
            exact+=arithmetic['facts']['exact_total_shares_match'];nearest+=arithmetic['facts']['nearest_hand_daily_total_match_diagnostic_only']
            if firstordinary is None:firstordinary=(code,day,packet,d)
        expectedrows.append(row)
    expected={'sessions':expectedrows,'nonexecuting_source_intervals':request['nonexecuting_source_intervals']};need(actualdetails==expected,'all2502details independently reconstructed')
    counts=dict(Counter(r['status'] for r in expectedrows));need(counts=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':2490,'SOURCE_REJECTED':12},'2490+12 failure counts')
    need(len(evidenceids)==119520 and len(windows_hashes)==2490 and exact==215,'48windows/215exactmatches')
    rejected=[r for r in expectedrows if r['status']=='SOURCE_REJECTED'];need(actual['exceptions']==rejected and all(not r['same_month_target_includes_instrument'] for r in rejections),'12rejections retained/no target membership inference')
    expectedsummary={'status':'PRICE_DELAY_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE','plan_sha256':sha(P),'method_code_sha256':plan['method_code_sha256'],'capture_plan_sha256':sha(cpfile),'capture_manifest_sha256':sha(C/'manifest.json'),'request_sha256':sha(rqfile),'capture_scope_sha256':sha(C/'price-delay-scope.json'),'independent_capture_audit_sha256':sha(afile),'raw_manifest_sha256':sha(raw/'manifest.json'),'target_sha256':sha(target),'required_active_sessions':2502,'nonexecuting_source_intervals':2,'status_counts':counts,'fresh_reservations':918,'fresh_responses':918,'reused_packets':1584,'client_cleanup_passes':True,'admitted_for_reconstructed_execution':False,'details_sha256':sha(O/'details.json'),'exact_share_total_matches':exact,'exact_share_precision_certified':False,'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,'portfolio_returns_computed':False,'new_2026_market_values_queried':False,'candidate_promoted':False,'objective_achieved':False,'exceptions':rejected}
    need(actual==expectedsummary,'entire failed admission summary reconstructed')
    negative={};code,day,packet,daily=firstordinary
    for mode in ('missing_minute','wrong_security','lunch_timestamp','off_cent_price','oversized_lower_volume','wrong_close'):
        changed=copy.deepcopy(packet);v=reference.record(changed)['response']
        if mode=='missing_minute':v['points'].pop()
        elif mode=='wrong_security':changed['instrument']='SZ000001'
        elif mode=='lunch_timestamp':v['points'][120]['time']=day+'T12:01:00+08:00'
        elif mode=='off_cent_price':v['points'][0].update(price_milli=10001,price='10.001',volume=1)
        elif mode=='oversized_lower_volume':v['points'][0]['volume']=int(daily['volume'])//100+1000
        else:v['points'][-1].update(price_milli=0,price=0)
        try:reference.reconstruct(code,day,changed,daily)
        except (AssertionError,ValueError,KeyError):negative[mode]=True
        else:raise AssertionError('source mutation accepted '+mode)
    for mode in ('ST_error_erased','ST_falsely_admitted','forged_overall_pass'):
        if mode=='forged_overall_pass':changed=copy.deepcopy(actual);changed['admitted_for_reconstructed_execution']=True;correct=expectedsummary
        else:
            changed=copy.deepcopy(actualdetails);i=next(i for i,r in enumerate(changed['sessions']) if r['status']=='SOURCE_REJECTED')
            if mode=='ST_error_erased':changed['sessions'][i].pop('error')
            else:changed['sessions'][i]['status']='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE'
            correct=expected
        try:need(changed==correct,'preserved failure mismatch')
        except AssertionError:negative[mode]=True
        else:raise AssertionError('failure mutation accepted '+mode)
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,h in plan[field].items():need(sha(root/n)==h,'inputs unchanged after audit')
    need(queryhashes=={str(p.relative_to(C)):sha(p) for p in (C/'queries').rglob('*') if p.is_file()},'journal unchanged')
    memberships=[{'execution_session':d,'weight':t['weights']['SZ002092']} for d,t in targets.items() if 'SZ002092' in t['weights']]
    result={'status':'FAILED_ADMISSION_CORRECTLY_PRESERVED_INDEPENDENTLY_RECONSTRUCTED','admission_plan_sha256':EXPECTED,'freeze_commit':freeze,'admission_summary_sha256':sha(O/'summary.json'),'admission_details_sha256':sha(O/'details.json'),'audit_code_sha256':sha(Path(__file__)),'capture_manifest_sha256':sha(C/'manifest.json'),'capture_plan_sha256':sha(cpfile),'request_sha256':sha(rqfile),'scope_sha256':sha(C/'price-delay-scope.json'),'capture_audit_sha256':sha(afile),'method_code_sha256':plan['method_code_sha256'],'query_artifact_sha256':queryhashes,'imports_project_code':False,'published_independent_pure_arithmetic_reused':{'file':str(REF.relative_to(R)),'sha256':sha(REF),'functions_called':['reconstruct','record'],'authorship':'Existing published independent audit arithmetic; this script independently executes and reviews price-delay failure outputs.'},'all2502_details_and_entire_summary_reconstructed':True,'ordinary_samples_reconstructed':2490,'ordinary_protocol_points':2490*240,'five_minute_windows_reconstructed':len(evidenceids),'window_evidence_IDs_sha256':digest(evidenceids),'reconstructed_windows_sha256':digest(windows_hashes),'exact_total_share_matches_diagnostic_only':exact,'nearest_hand_matches_diagnostic_only':nearest,'source_rejected_samples':rejections,'frozen_SZ002092_target_memberships':memberships,'target_check_is_not_actual_ownership_proof':True,'reused_bytes_authenticated':1584,'fresh_receipt_chains_authenticated':918,'journal_files_authenticated':2754,'semantic_negative_controls_rejected':negative,'failed_admission_correctly_preserved':True,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'account_replay_performed':False,'new_2026_values_read':False,'network_calls':0,'repository_or_source_outputs_modified':False,'candidate_promoted':False,'objective_achieved':False,'critical_or_important_output_correctness_findings':[],'limitations':['This audit confirms preserved formal admission failure; it does not grant execution admission or remove rejected identities.','SZ002092 is a frozen target only on2024-01-02. All12rejected monthly samples are absent from that month target; this cannot establish zero actual holdings or justify a revised rule.','Independent arithmetic reconstructs48five-minute windows per ordinary sample and documented hand-volume lowerbounds; it does not certify exact minute share precision, SDK date echo, historical arrival, PIT, queue or impact.','No account replay, ROI computation, production inspect/sim import or2026market read was performed.']}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'script_sha256':result['audit_code_sha256'],'ordinary':2490,'rejected':12,'windows':len(evidenceids),'negative_controls':len(negative),'admission_passes':False,'SZ002092_frozen_target_memberships':memberships}))
if __name__=='__main__':main()
