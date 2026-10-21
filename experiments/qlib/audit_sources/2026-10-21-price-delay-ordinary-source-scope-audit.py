"""Independent local reconstruction of ordinary-only scope; no account/ROI.
Stdlib plus a published independent audit's pure arithmetic, no production import.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime
import copy,hashlib,importlib.util,json,subprocess
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
O=B/'price-delay-ordinary-source-scope-20261021';C=B/'price-delay-minutes-dev-20261021';F=B/'price-delay-minute-admission-20261021'
P=R/'experiments/qlib/price-delay-ordinary-source-scope-plan.json';REPORT=Path('/tmp/price-delay-ordinary-source-scope-independent-audit-20261021.json')
EXPECTED='03ae02284bdfb2a096c92c0084c5562223927ec9568af18d3941a4f0fdd726fc'
REF=R/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-minute-admission-audit.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(v,s):
    if not v:raise AssertionError(s)
def main():
    plan=read(P);summary=read(O/'summary.json');scope=read(O/'scope.json');freeze=subprocess.check_output(['git','rev-parse','404ff29'],cwd=R,text=True).strip()
    need(sha(P)==EXPECTED==summary['plan_sha256'] and hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(P.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen plan')
    ap=read(R/'experiments/qlib/price-delay-minute-admission-plan.json')
    extra={'scripts/prepare_price_delay_ordinary_scope_pre2026.py','scripts/run_low_beta60_intraday_development.py','scripts/run_low_risk_intraday_replay.py','src/stock_rsi/ordinary_source_scope.py','scripts/replay_ordinary_stock_distribution_targets.py'}
    need(set(plan['method_code_sha256'])==set(ap['method_code_sha256'])|extra and len(plan['method_code_sha256'])==17,'17complete method bindings')
    need(set(plan['local_source_sha256'])=={'price-delay-minute-admission-20261021/summary.json','price-delay-minute-admission-20261021/details.json','price-delay-minutes-dev-20261021/manifest.json'},'exact local scope')
    need(set(plan['public_evidence_sha256'])=={'experiments/qlib/price-delay-minute-admission-plan.json','experiments/qlib/price-delay-minute-admission-independent-audit.json','experiments/qlib/price-delay-minute-admission-summary.json','experiments/qlib/price-delay-minute-admission-verification.json','experiments/qlib/audit_sources/2026-10-21-price-delay-minute-admission-audit.py','experiments/qlib/price-delay-ordinary-scope-code-review.json','experiments/qlib/price-delay-ordinary-scope-preparation-verification.json','docs/research/price-delay-ordinary-source-admission-plan-2026-10-21.md'},'exact8publicscope')
    for boundplan in (plan,ap):
        for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
            for n,h in boundplan[field].items():
                need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(root/n)==h,'bound input '+n)
                if root==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen blob '+n)
    need(plan['status']=='FROZEN_PRICE_DELAY_ORDINARY_SOURCE_SCOPE' and plan['candidate']=='price_delay_d1' and plan['window']==['2024-01-02','2025-12-31'] and plan['ordinary_packets']==2490 and plan['rejected_packets']==12 and plan['nonordinary_daily_intervals']==241 and plan['nonexecuting_halt_intervals']==2 and plan['network_calls_permitted']==0 and plan['account_dependency_guard_required'] is True,'bounded profile')
    prior=read(R/'experiments/qlib/price-delay-minute-admission-independent-audit.json');failed=read(F/'summary.json');details=read(F/'details.json')
    need(prior['admission_summary_sha256']==sha(F/'summary.json') and prior['admission_details_sha256']==sha(F/'details.json') and prior['failed_admission_correctly_preserved'] is True and prior['all2502_details_and_entire_summary_reconstructed'] is True and prior['imports_project_code'] is False and prior['audit_code_sha256']==sha(R/'experiments/qlib/audit_sources/2026-10-21-price-delay-minute-admission-audit.py'),'reuse authenticated independent failure evidence')
    need(len(prior['semantic_negative_controls_rejected'])>=4 and all(v is True for v in prior['semantic_negative_controls_rejected'].values()),'prior semantic controls')
    need(failed['admitted_for_reconstructed_execution'] is False and failed['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':2490,'SOURCE_REJECTED':12} and failed['details_sha256']==sha(F/'details.json'),'strict failure remains false')
    cpfile=R/'experiments/qlib/price-delay-minute-capture-plan.json';rqfile=R/'experiments/qlib/price-delay-minute-gap-identities.json';cafile=R/'experiments/qlib/price-delay-minute-capture-independent-audit.json'
    cp=read(cpfile);request=read(rqfile);ca=read(cafile);manifest=read(C/'manifest.json');cleanup=read(C/'client_cleanup.json');cscope=read(C/'price-delay-scope.json')
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,h in cp[field].items():need(sha(root/n)==h,'capture bound source '+n)
    need(sha(cpfile)==sha(C/'plan.json')==ap['capture_plan_sha256']==ca['capture_plan_sha256'] and sha(rqfile)==sha(C/'request.json')==ap['request_sha256']==ca['request_sha256'],'capture plan/request')
    need(sha(C/'manifest.json')==ap['capture_manifest_sha256']==ca['capture_manifest_sha256'] and sha(C/'price-delay-scope.json')==ca['scope_sha256'],'capture manifest/scope')
    need(ca['capture_fully_recorded'] is True and ca['imports_project_code'] is False and cleanup=={'created_clients':1,'closed_clients':[{'entered':True,'close_called':True,'error':None}]} and cscope['cleanup_sha256']==sha(C/'client_cleanup.json'),'cleanup/complete chain')
    snap=C/('capture-snapshot-'+digest(manifest)+'.json');need(read(snap)==manifest and sha(snap)==ca['legacy_snapshot_sha256'],'immutable legacy snapshot')
    queryhashes={str(p.relative_to(C)):sha(p) for p in (C/'queries').rglob('*') if p.is_file()};need(queryhashes==ca['query_artifact_sha256']==prior['query_artifact_sha256'] and len(queryhashes)==2754,'all2754journal byte identities')
    fresh=request['uncached_requests'];reused=request['reused_session_provenance'];need(len(fresh)==918 and len(reused)==1584 and read(C/'capture_request.json')=={'reused':reused,'fresh':fresh},'frozen partition')
    projections={};qkeys=set()
    for code,day in fresh:
        identity={'method':'minutes.history','instrument':code,'requested_day':day,'host':cp['host'],'include_raw':True};key=digest(identity);qkeys.add(key);folder=C/'queries'/key
        need({p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'} and read(folder/'request.json')==identity,'exact one queryattempt')
        reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json');need(reserve['identity_sha256']==response['identity_sha256']==key and reserve['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json') and response['status']=='CAPTURED','reservation response link')
        payload=response['payload'];need(response['payload_sha256']==digest(payload) and payload['fields']==['response'] and len(payload['rows'])==1 and datetime.fromisoformat(reserve['reserved_at_utc'])<=datetime.fromisoformat(payload['captured_at_utc']),'payload chronology/checksum')
        projections[code+'-'+day+'.json']={'instrument':code,'requested_day':day,'status':'RESPONSE_CAPTURED','response':payload['rows'][0],'observed_at':payload['captured_at_utc'],'query_response_sha256':sha(folder/'response-1.json'),'query_reservation_sha256':sha(folder/'reserved-1.json')}
    need({p.name for p in (C/'queries').iterdir()}==qkeys,'918 exact queries')
    raw=B/'price-delay-raw-dev-20261021';rm=read(raw/'manifest.json');need(sha(raw/'manifest.json')==request['raw_manifest_sha256']==failed['raw_manifest_sha256'],'raw manifest')
    bars={};nonordinary=[]
    for code,h in sorted(rm['per_code_sha256'].items()):
        p=raw/'codes'/(code+'.json');need(sha(p)==h,'151raw packet identity');v=read(p);need(v['instrument']==code and v['window']==['2023-12-29','2025-12-31'],'rawpre2026window');bars[code]={r['date']:r for r in v['bars']}
        for day,r in sorted(bars[code].items()):
            need('2023-12-29'<=day<='2025-12-31' and type(r['isST']) is str and r['isST'] in ('0','1'),'explicit original state')
            if r['isST']=='1':nonordinary.append({'instrument':code,'day':day,'source_isST':'1','tradestatus':r['tradestatus'],'account_dependency_proven_absent':False})
    need(len(nonordinary)==241,'241rawnonordinarydays')
    target=B/'price-delay-pre2026-formations-20261021/targets.json';need(sha(target)==rm['target_sha256']==request['target_sha256']==failed['target_sha256'],'targets unchanged')
    need(sha(REF)==hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REF.relative_to(R))],cwd=R)).hexdigest(),'frozen arithmetic reference')
    spec=importlib.util.spec_from_file_location('independent_ordinary_scope_arithmetic',REF);ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
    need([[r['instrument'],r['day']] for r in details['sessions']]==request['active_requests'] and details['nonexecuting_source_intervals']==request['nonexecuting_source_intervals'],'all original failed identities retained')
    ordinary={};rejected={};windowsdigest=[];exceptions=[]
    for row in details['sessions']:
        code,day=row['instrument'],row['day'];need('2024-01-02'<=day<='2025-12-31','pre2026 minute identity');name=code+'-'+day+'.json';p=C/'sessions'/name;h=sha(p);need(h==row['source_sha256']==manifest['per_session_sha256'][name]==ca['all2502_packet_sha256'][name],'original minute packet SHA');packet=read(p)
        if name in reused:
            need(row['origin']==reused[name] and h==reused[name]['sha256'] and p.read_bytes()==(B/reused[name]['root']/'sessions'/name).read_bytes(),'original reusebytecopy')
        else:need(row['origin']=='FROZEN_FRESH_QUERY' and packet==projections[name],'original freshSDKprojection')
        daily=bars[code][day]
        if daily['isST']=='0':
            values,windows=ref.reconstruct(code,day,packet,daily);need(all(row[k]==v for k,v in values.items()),'ordinary arithmetic matches independent failed admission');ordinary[name]=h;windowsdigest.append(digest(windows))
        else:
            need(code=='SZ002092' and daily['isST']=='1' and daily['tradestatus']=='1' and row['status']=='SOURCE_REJECTED' and row['error_type']=='ValueError' and row['error']=='source security/date/ordinary active state changed','original ST refusal exact');rejected[name]=h;exceptions.append(row)
    need(len(ordinary)==2490 and len(rejected)==12 and set(ordinary).isdisjoint(rejected) and {**ordinary,**rejected}==manifest['per_session_sha256'] and exceptions==failed['exceptions'],'disjoint complete original source partition')
    halts=request['nonexecuting_source_intervals'];need(len(halts)==2 and all(bars[r['instrument']][r['day']]['tradestatus']=='0' and r['actual_inventory_proven_zero'] is False and r['synthetic_price_created'] is False for r in halts),'2original halted intervals')
    expected_scope={'ordinary_packet_sha256':ordinary,'rejected_packet_sha256':rejected,'nonordinary_source_intervals':nonordinary,'nonexecuting_halt_intervals':halts};need(scope==expected_scope,'complete scope JSON independently reconstructed')
    expected_summary={'status':'ORDINARY_SOURCE_SCOPE_PREPARED_ACCOUNT_PROOF_REQUIRED','plan_sha256':EXPECTED,'method_code_sha256':plan['method_code_sha256'],'scope_sha256':sha(O/'scope.json'),'ordinary_packets_content_verified':2490,'rejected_packets_retained':12,'nonordinary_daily_intervals':241,'original_strict_admission_remains_failed':True,'account_dependency_guard_required':True,'all_account_dependencies_ordinary_proven':False,'admitted_for_unconditional_execution':False,'new_2026_values_read':False,'portfolio_returns_computed':False,'objective_achieved':False};need(summary==expected_summary,'entire summary reconstructed')
    negatives={}
    for mode in ('ST_packet_promoted','rejection_erased','ordinary_hash_rewritten','ST_day_erased','ST_dependency_absence_forged','halt_erased','conditional_proof_upgraded'):
        x=copy.deepcopy(scope);expected=expected_scope
        if mode=='ST_packet_promoted':n=next(iter(rejected));x['ordinary_packet_sha256'][n]=x['rejected_packet_sha256'].pop(n)
        elif mode=='rejection_erased':x['rejected_packet_sha256'].pop(next(iter(rejected)))
        elif mode=='ordinary_hash_rewritten':x['ordinary_packet_sha256'][next(iter(ordinary))]='0'*64
        elif mode=='ST_day_erased':x['nonordinary_source_intervals'].pop()
        elif mode=='ST_dependency_absence_forged':x['nonordinary_source_intervals'][0]['account_dependency_proven_absent']=True
        elif mode=='halt_erased':x['nonexecuting_halt_intervals'].pop()
        else:x=copy.deepcopy(summary);expected=expected_summary;x['all_account_dependencies_ordinary_proven']=True;x['admitted_for_unconditional_execution']=True
        try:need(x==expected,'semantic source scope/output mismatch')
        except AssertionError:negatives[mode]=True
        else:raise AssertionError('unsafe scope mutation accepted '+mode)
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,h in plan[field].items():need(sha(root/n)==h,'bound inputs unchanged after audit')
    need(queryhashes=={str(p.relative_to(C)):sha(p) for p in (C/'queries').rglob('*') if p.is_file()},'journal immutable after audit')
    result={'status':'ORDINARY_SOURCE_SCOPE_INDEPENDENTLY_RECONSTRUCTED_ACCOUNT_DEPENDENCY_UNPROVEN','source_summary_sha256':sha(O/'summary.json'),'source_scope_sha256':sha(O/'scope.json'),'ordinary_scope_reconstructed':True,'ordinary_samples_reconstructed':2490,'nonordinary_intervals_reconstructed':241,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'semantic_negative_controls_rejected':negatives,'plan_sha256':EXPECTED,'freeze_commit':freeze,'method_code_sha256':plan['method_code_sha256'],'binding_counts':{'method':17,'public':8,'local':3},'rejected_samples_reconstructed':12,'halt_intervals_reconstructed':halts,'original_failed_admission_summary_sha256':sha(F/'summary.json'),'original_failed_admission_details_sha256':sha(F/'details.json'),'prior_independent_failed_admission_audit_sha256':sha(R/'experiments/qlib/price-delay-minute-admission-independent-audit.json'),'original_strict_admission_remains_failed':True,'ordinary_packet_sha256':ordinary,'rejected_packet_sha256':rejected,'all241_raw_ST_intervals':nonordinary,'all2490_window_arithmetic_rechecked':True,'reconstructed_windows_sha256':digest(windowsdigest),'query_artifact_sha256':queryhashes,'fresh_receipt_chains_authenticated':918,'original_reuse_bytes_authenticated':1584,'all151_raw_packets_unchanged':True,'target_sha256':sha(target),'published_independent_arithmetic_reference':{'file':str(REF.relative_to(R)),'sha256':sha(REF),'function':'reconstruct'},'conditional_account_dependency_proof':False,'all_account_dependencies_ordinary_proven':False,'admitted_for_unconditional_execution':False,'actual_inventory_zero_inferred':False,'account_replay_performed':False,'portfolio_returns_computed':False,'new_2026_values_read':False,'network_calls':0,'repository_modified':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Ordinary source partition only. Original2502sample strict admission remains failed and all12rejections/241nonordinarydays remain inspectable.','No conditional account dependency proof was performed or inferred from target absence. Owned/pending inventory, orders and decision-price dependencies still require the frozen fail-closed guard.','Reused independent pure arithmetic verifies local decoded source facts/windows; it does not certify historical arrival/PIT, SDK date echo, exact share precision, queue/impact or any portfolio outcome.']}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'script_sha256':result['audit_code_sha256'],'ordinary':2490,'rejects':12,'ST_days':241,'halts':2,'negative_controls':len(negatives),'conditional_account_dependency_proof':False}))
if __name__=='__main__':main()
