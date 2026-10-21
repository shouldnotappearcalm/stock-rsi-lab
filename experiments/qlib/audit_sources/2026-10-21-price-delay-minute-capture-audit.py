"""Independent local stdlib capture audit; no project imports, SDK/network/ROI.
Based on the published composite provenance audit contract, adapted independently
for price-delay scope and reconstructed using frozen inputs and observed journals.
"""
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal as D
from datetime import date,datetime
import ast,copy,hashlib,json,re,subprocess
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
O=B/'price-delay-minutes-dev-20261021'
REPORT=Path('/tmp/price-delay-minute-capture-independent-audit-20261021.json')
PLAN=R/'experiments/qlib/price-delay-minute-capture-plan.json'
REQUEST=R/'experiments/qlib/price-delay-minute-gap-identities.json'
EXPECTED='82468c0329f042eee6b8152dcb53f1d573a21f4b32843cf8e9d73d1bcd500904'
ROOTS=['illiquidity-minutes-dev-20261021','low-beta60-minutes-dev-20261021','szse-value-momentum-minutes-dev-20261021','return-family-minutes-dev-20261017','szse-value-minutes-dev-20261017']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(v,s):
    if not v:raise AssertionError(s)
def pair(c,d):need(re.fullmatch('(SH|SZ)[0-9]{6}',c) is not None and date.fromisoformat(d).isoformat()==d and '2024-01-02'<=d<='2025-12-31','pre2026 instrument/session')
def record(p):return p.get('methods',{}).get('minutes.history',p)
def identity(c,d,host):pair(c,d);return {'method':'minutes.history','instrument':c,'requested_day':d,'host':host,'include_raw':True}
def quality(c,d,p,daily):
    pair(c,d);need(p['instrument']==c and p['requested_day']==d and daily['date']==d and daily['tradestatus']=='1' and daily['isST'] in ('0','1'),'source identity/status')
    r=record(p);need(r['status']=='RESPONSE_CAPTURED','captured status');v=r['response']
    need(v['exchange']==c[:2].lower() and type(v['market_id']) is int and v['market_id']==(1 if c.startswith('SH') else 0) and v['code']==c[2:] and v['trading_date']==d,'SDK identity')
    labels=[f'{h:02}:{m:02}' for h in range(16) for m in range(60) if '09:31'<=f'{h:02}:{m:02}'<='11:30' or '13:01'<=f'{h:02}:{m:02}'<='15:00'];need(len(v['points'])==len(labels)==240,'240 points')
    lower=0
    for n,(pt,label) in enumerate(zip(v['points'],labels)):
        need(type(pt['index']) is int and pt['index']==n and pt['time_label']==label and pt['time']==d+'T'+label+':00+08:00','point chronology')
        price,vol=pt['price_milli'],pt['volume'];need(type(price) is int and type(vol) is int and min(price,vol)>=0 and not isinstance(pt['price'],bool) and D(str(pt['price']))==D(price)/1000,'point numeric units')
        if vol:need(price>0 and price%10==0 and D(daily['low'])<=D(price)/1000<=D(daily['high']),'cent tick/daily price bounds')
        lower+=max(0,vol*100-100)
    need(D(v['points'][-1]['price_milli'])/1000==D(daily['close']) and lower<=D(daily['volume']),'close and lowerbound whole-day volume')
    need(daily['isST']=='0','ORDINARY_SECURITY_STATE_REQUIRED_BY_FROZEN_INSPECT_PACKET')
    return lower

def main():
    plan=read(PLAN);request=read(REQUEST);manifest=read(O/'manifest.json')
    need(sha(PLAN)==EXPECTED==sha(O/'plan.json')==manifest['plan_sha256'],'plan bytes')
    need(sha(REQUEST)==plan['request_sha256']==sha(O/'request.json'),'request bytes')
    freeze=subprocess.check_output(['git','log','-1','--format=%H','--',str(PLAN.relative_to(R))],cwd=R,text=True).strip()
    need(sha(PLAN)==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(PLAN.relative_to(R))],cwd=R)).hexdigest(),'frozen plan')
    tree=ast.parse((R/'scripts/capture_price_delay_minutes_pre2026.py').read_text());const={}
    def literal(n):
        if isinstance(n,ast.Constant):return n.value
        if isinstance(n,ast.Name):return const[n.id]
        if isinstance(n,ast.Tuple):return tuple(literal(x) for x in n.elts)
        if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add):return literal(n.left)+literal(n.right)
        raise AssertionError('unsupported constant AST')
    for n in tree.body:
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ['RAW','TARGET','SOURCE','INVENTORY','METHOD_FILES','PUBLIC_FILES','LOCAL_FILES']:const[n.targets[0].id]=literal(n.value)
    for field,parent,key in [('method_code_sha256',R,'METHOD_FILES'),('public_evidence_sha256',R,'PUBLIC_FILES'),('local_source_sha256',B,'LOCAL_FILES')]:
        need(set(plan[field])==set(const[key]),'exact binding scope')
        for n,h in plan[field].items():
            need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(parent/n)==h,'frozen input '+n)
            if parent==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen blob '+n)
    need(plan['status']=='FROZEN_PRICE_DELAY_PRE2026_MINUTE_SOURCE_CAPTURE' and plan['candidate']=='price_delay_d1' and plan['window']==['2024-01-02','2025-12-31'],'plan scope')
    for k,v in {'required_source_pairs':2502,'existing_source_pairs_to_reuse':1584,'max_fresh_query_reservations':918,'max_attempts_per_request':1,'timeout_seconds':3,'pool_size':1,'server_count':1,'connections_per_server':1,'stop_after_consecutive_source_failures':3}.items():need(type(plan[k]) is int and plan[k]==v,'plan '+k)
    need(plan['host']=='116.205.183.150:7709' and plan['package_version']=='3.2.3' and plan['heartbeat_interval'] is None and plan['probe_hosts'] is False and plan['inter_query_delay_seconds']==.05,'single endpoint settings')
    for k in ['investment_rule_changed','portfolio_returns_to_compute','new_2026_queries_allowed','objective_achieved']:need(plan[k] is False,'bounded plan flags')
    need(request['source_precedence']==ROOTS and set(request['source_manifest_sha256'])==set(ROOTS) and not request['conflicting_cached_requests'] and not request['invalid_cached_requests'],'cache source scope/no conflicts')
    inv=B/'price-delay-minute-inventory-20261021';need(sha(inv/'details.json')==request['local_details_sha256'] and sha(inv/'summary.json')==request['inventory_summary_sha256'],'inventory bindings')
    raw=B/'price-delay-raw-dev-20261021';rm=read(raw/'manifest.json');need(sha(raw/'manifest.json')==request['raw_manifest_sha256'] and rm['window']==['2023-12-29','2025-12-31'] and sha(raw/'calendar.json')==rm['calendar_sha256'],'raw manifest calendar')
    sessions=read(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==rm['window'],'486sessions')
    bars={};inputs={}
    for c,h in rm['per_code_sha256'].items():
        p=raw/'codes'/(c+'.json');need(sha(p)==h,'original packet');v=read(p);need(v['instrument']==c and v['window']==rm['window'] and [r['date'] for r in v['bars']]==sessions,'raw issuer/date');bars[c]={r['date']:r for r in v['bars']};inputs[str(p)]=h
    target=B/'price-delay-pre2026-formations-20261021/targets.json';need(sha(target)==request['target_sha256']==rm['target_sha256'],'targets');targets=read(target)['price_delay_d1'];need(len(targets)==24 and len(bars)==151 and {c for t in targets.values() for c in t['weights']}==set(bars),'24targets151names')
    src=B/'price-delay-account-source-events-20261021';ss=read(src/'summary.json');need(sha(src/'summary.json')==request['source_projection_summary_sha256'] and sha(src/'effective_proofs.json')==ss['artifact_sha256']['effective_proofs.json'],'source projection');lifecycles=read(src/'effective_proofs.json')['lifecycles'];need(lifecycles=={},'no lifecycle exceptions in price-delay')
    active=[];skipped=[];seen=set()
    for d,t in sorted(targets.items()):
        pair('SZ000001',d);need(sessions[sessions.index(d)-1]==t['as_of'] and d[:7]!=t['as_of'][:7],'monthly priorclose');seen.update(t['weights'])
        for c in sorted(seen):
            r=bars[c][d];need(r['date']==d and r['isST'] in ('0','1'),'explicit historical source state')
            if r['tradestatus']=='0':skipped.append({'instrument':c,'day':d,'reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False})
            else:need(r['tradestatus']=='1','known source state');active.append([c,d])
    need(active==request['active_requests'] and skipped==request['nonexecuting_source_intervals'] and len(active)==2502 and len(skipped)==2,'complete active and halt identities')
    index=defaultdict(list)
    for root in ROOTS:
        mf=B/root/'manifest.json';need(sha(mf)==request['source_manifest_sha256'][root],'cache manifest')
        for fn,h in read(mf)['per_session_sha256'].items():need(Path(fn).name==fn,'safe source filename');index[fn].append({'root':root,'sha256':h})
    reused={};fresh=[];references=0
    for c,d in active:
        fn=c+'-'+d+'.json';origins=index[fn]
        if not origins:fresh.append([c,d]);continue
        signatures=set()
        for origin in origins:
            p=B/origin['root']/'sessions'/fn;need(sha(p)==origin['sha256'],'cache reference');v=read(p);need(v['instrument']==c and v['requested_day']==d,'reference identity');r=record(v);signatures.add(digest({'status':r['status'],'response':r.get('response')}));references+=1;inputs[str(p)]=origin['sha256']
        need(len(signatures)==1,'all cached raw response signatures agree');reused[fn]=origins[0]
    need(reused==request['reused_session_provenance']==manifest['reused_session_provenance'] and fresh==request['uncached_requests'] and len(reused)==1584 and len(fresh)==918 and references==2261,'exact partition and all2261references')
    need(read(O/'capture_request.json')=={'reused':reused,'fresh':fresh} and sha(O/'capture_request.json')==manifest['capture_request_sha256'],'helper capture request')
    expectedkeys={digest(identity(c,d,plan['host'])):(c,d) for c,d in fresh};folders={f.name:f for f in (O/'queries').iterdir()};need(set(folders)==set(expectedkeys),'all918 unique queries only')
    queryhashes={};projection={};queryoutcomes=[]
    for key,folder in folders.items():
        c,d=expectedkeys[key];need({p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'},'exact one complete attempt')
        need(read(folder/'request.json')==identity(c,d,plan['host']),'exact fixed endpoint/identity/include_raw')
        reservation=read(folder/'reserved-1.json');r=read(folder/'response-1.json');need(reservation['identity_sha256']==key and reservation['attempt']==1,'reservation identity');need(r['identity_sha256']==key and r['reservation_sha256']==sha(folder/'reserved-1.json') and r['status']=='CAPTURED','successful response link')
        payload=r['payload'];need(r['payload_sha256']==digest(payload) and payload['fields']==['response'] and len(payload['rows'])==1,'SDK payload checksum/schema');need(datetime.fromisoformat(reservation['reserved_at_utc'])<=datetime.fromisoformat(payload['captured_at_utc']) and datetime.fromisoformat(payload['captured_at_utc']).utcoffset().total_seconds()==0,'capture time ordering')
        fn=c+'-'+d+'.json';projection[fn]={'instrument':c,'requested_day':d,'status':'RESPONSE_CAPTURED','response':payload['rows'][0],'observed_at':payload['captured_at_utc'],'query_response_sha256':sha(folder/'response-1.json'),'query_reservation_sha256':sha(folder/'reserved-1.json')}
        queryoutcomes.append({'instrument':c,'day':d,'journal_status':'CAPTURED','response_sha256':sha(folder/'response-1.json')})
        for p in folder.iterdir():queryhashes[str(p.relative_to(O))]=sha(p)
    need(len(queryhashes)==2754 and queryhashes=={str(p.relative_to(O)):sha(p) for p in (O/'queries').rglob('*') if p.is_file()},'exact recursive2754journal file hashes')
    expectednames={c+'-'+d+'.json' for c,d in active};need(set(manifest['per_session_sha256'])==expectednames=={p.name for p in (O/'sessions').iterdir()},'exact2502session files')
    qualityquestions=[];counts=Counter();all2502={}
    for fn,h in manifest['per_session_sha256'].items():
        p=O/'sessions'/fn;need(sha(p)==h,'captured packet SHA');v=read(p);c,d=fn[:-5].split('-',1);pair(c,d);need(v['instrument']==c and v['requested_day']==d,'captured packet identity');counts[record(v)['status']]+=1;all2502[fn]=h
        if fn in reused:
            origin=reused[fn];need(h==origin['sha256'] and p.read_bytes()==(B/origin['root']/'sessions'/fn).read_bytes(),'1584exact original bytes')
        else:need(v==projection[fn],'918exact SDK journal projections')
        try:quality(c,d,v,bars[c][d])
        except (AssertionError,ValueError,KeyError,TypeError,ArithmeticError) as exc:qualityquestions.append({'file':fn,'instrument':c,'day':d,'sha256':h,'packet_status':record(v)['status'],'daily_tradestatus':bars[c][d]['tradestatus'],'daily_isST':bars[c][d]['isST'],'error_type':type(exc).__name__,'error':str(exc),'admission':'SEPARATE_SOURCE_REVIEW_REQUIRED','automatically_excluded':False,'actual_inventory_zero_inferred':False})
    need(dict(counts)==manifest['response_status_counts']=={'RESPONSE_CAPTURED':2502},'complete successful captured counts')
    rebuilt={'status':'LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED','plan_sha256':sha(O/'plan.json'),'capture_request_sha256':sha(O/'capture_request.json'),'requested':2502,'captured':2502,'per_session_sha256':dict(sorted(all2502.items())),'reused_session_provenance':reused,'active_reused_packets_authenticated_upfront':1584,'fresh_query_reservations':918,'fresh_query_responses_preserved':918,'response_status_counts':dict(counts),'stopped_after_consecutive_source_failures':False,'abnormal_exit':None,'complete_capture':True,'new_2026_queries':False,'historical_arrival_verified':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
    need(rebuilt==manifest,'entire legacy helper manifest reconstruction');snaps=list(O.glob('capture-snapshot-*.json'));need(len(snaps)==1 and snaps[0].name=='capture-snapshot-'+digest(manifest)+'.json' and read(snaps[0])==manifest,'legacy immutable snapshot')
    cleanup=read(O/'client_cleanup.json');need(cleanup=={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]},'one successful client close')
    scope=read(O/'price-delay-scope.json');need(scope=={'status':'PRICE_DELAY_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'price_delay_d1','capture_plan_sha256':sha(PLAN),'request_sha256':sha(REQUEST),'legacy_helper_manifest_sha256':sha(O/'manifest.json'),'legacy_status_marker_preserved':True,'expected_active_pairs':2502,'fixed_reused_pairs':1584,'maximum_fresh_logical_reservations':918,'complete_capture':True,'cleanup_sha256':sha(O/'client_cleanup.json'),'new_2026_queries':False,'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False},'complete separate scope binding')
    for p,h in inputs.items():need(sha(Path(p))==h,'inputs immutable after audit')
    for field,parent in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,h in plan[field].items():need(sha(parent/n)==h,'frozen identities after audit')
    need(sha(PLAN)==EXPECTED and sha(REQUEST)==plan['request_sha256'],'plan/request immutable')
    result={'status':'PASS_INDEPENDENT_PRICE_DELAY_MINUTE_CAPTURE_TECHNICAL_AUDIT_ADMISSION_SEPARATE','capture_manifest_sha256':sha(O/'manifest.json'),'capture_plan_sha256':sha(PLAN),'request_sha256':sha(REQUEST),'scope_sha256':sha(O/'price-delay-scope.json'),'imports_project_code':False,'query_artifact_sha256':queryhashes,'legacy_snapshot_sha256':sha(snaps[0]),'capture_fully_recorded':True,'audit_script_sha256':sha(Path(__file__)),'freeze_commit':freeze,'method_code_sha256':plan['method_code_sha256'],'binding_counts':{'method':len(plan['method_code_sha256']),'public':len(plan['public_evidence_sha256']),'local':len(plan['local_source_sha256'])},'captured_packets':2502,'captured_status_counts':dict(counts),'all2502_packet_sha256':all2502,'selected1584_reuse_bytes_unchanged':True,'matching_cache_references_authenticated':2261,'five_source_manifests_authenticated':True,'required_active_identities_reconstructed':2502,'nonexecuting_source_intervals':skipped,'fresh_logical_reservations':918,'fresh_responses':918,'journal_files':2754,'all918_SDK_projection_records_exact':True,'fresh_query_outcomes':queryoutcomes,'source_errors':[],'unanswered_attempts':[],'unmanifested_packets':[],'legacy_helper_status_and_snapshot_preserved':True,'client_cleanup':cleanup,'client_cleanup_verified':True,'all_bound_inputs_rechecked_unchanged':True,'source_quality_questions_for_separate_admission':qualityquestions,'source_quality_questions_count':len(qualityquestions),'account_replay_performed':False,'portfolio_returns_computed':False,'new_2026_values_read':False,'new_2026_queries':False,'source_queries_performed_by_auditor':0,'SDK_client_imported_by_auditor':False,'admitted_for_reconstructed_execution':False,'historical_arrival_certified':False,'SDK_date_echo_authenticated':False,'exact_share_precision_certified':False,'transport_packet_count_certified':False,'queue_and_impact_calibrated':False,'repository_modified':False,'objective_achieved':False,'critical_or_important_technical_capture_findings':[],'limitations':['Complete capture authenticates saved response packets, raw SDK projection and logical reservations, not source execution admission.','918is the logical minutes.history query count with one journal attempt per identity; underlying TCP/protocol packet or SDK-internal attempt completeness is not certified.','All date-indexed source identities are2024–2025; capture timestamps are2026 and no historical arrival/PIT seal is claimed.','240point chronology, cent ticks, dailyOHLC/close and conservative rounded-volume bounds are local content prechecks. Exact share precision, actual SDK date echo and market depth/queue/impact are not certified.','No account replay, return calculation, production-code import or source query was performed; separate local admission remains required.']}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'script_sha256':result['audit_script_sha256'],'packets':2502,'reuse':1584,'fresh':918,'journal_files':len(queryhashes),'quality_questions':len(qualityquestions),'capture_fully_recorded':True}))
if __name__=='__main__':main()
