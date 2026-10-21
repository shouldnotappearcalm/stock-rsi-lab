"""Independent stdlib audit of frozen price-delay PRE2026 raw capture.
No runtime validation imports, SDK calls, replay, or uncapped packet reads.
"""
from pathlib import Path
from decimal import Decimal as D
from datetime import date,datetime
from collections import Counter
import hashlib,json,subprocess
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
O=B/'price-delay-raw-dev-20261021'
REQ=R/'experiments/qlib/price-delay-pre2026-raw-source-request.json'
OUT=Path('/tmp/price-delay-raw-source-independent-audit-20261021.json')
EXPECTED='de427db69c3a5f0deb3823e0dfa7527a8fb8b97721f3de4696a5b6ea59b506b5'
START,END='2023-12-29','2025-12-31'
ALLOWED={'budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020','low-beta60-raw-dev-20261021','szse-value-momentum-raw-dev-20261021','return-families-raw-dev-20261017','szse-value-raw-dev-20261017'}
BF=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DF=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
AF=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(p):return json.loads(p.read_bytes())
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(ok,label):
    if not ok:raise AssertionError(label)
def day(d):return date.fromisoformat(d).isoformat()==d and START<=d<=END
def core(p):
    rows=[[r['date'],r['code'],*[str(D(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']] for r in p['bars']]
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
def projection(rows,fields):
    need(len(fields)==len(set(fields)) and all(len(r)==len(fields) for r in rows),'schema/columns')
    return [dict(zip(fields,r)) for r in rows]
def main():
    req=obj(REQ);m=obj(O/'manifest.json');freeze=subprocess.check_output(['git','rev-parse','600d45d'],cwd=R,text=True).strip()
    need(sha(REQ)==EXPECTED==sha(O/'request.json')==m['request_sha256'],'request binding')
    need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REQ.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'request freeze')
    for n,h in req['method_code_sha256'].items():
        need(sha(R/n)==h,'current method '+n);need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozen method '+n)
    for n,h in req['screen_files_sha256'].items():need(sha(R/n)==h,'screen evidence '+n)
    need(sha(R/req['protocol_file'])==req['protocol_sha256'],'protocol')
    inventory=obj(R/'experiments/qlib/price-delay-pre2026-raw-source-inventory.json')
    need(set(inventory['source_manifests_sha256'])==ALLOWED,'registered physically pre2026 source scope')
    manifests={}
    for n,h in inventory['source_manifests_sha256'].items():
        need(sha(B/n/'manifest.json')==h,'original manifest '+n);sm=obj(B/n/'manifest.json');need(sm['window']==[START,END],'physical pre2026 source manifest');manifests[n]=sm
    cal=obj(O/'calendar.json');sessions=cal['sessions'];cp=B/req['reference_calendar_file']
    need(sha(cp)==req['reference_calendar_sha256']==cal['origin_sha256'],'reference calendar')
    need(sessions==[d for d in cp.read_text().splitlines() if START<=d<=END] and len(sessions)==486 and sessions==sorted(set(sessions)) and sessions[0]==START and sessions[-1]==END,'486 source calendar')
    need(sha(O/'calendar.json')==m['calendar_sha256'],'output calendar')
    targets=B/'price-delay-pre2026-formations-20261021/targets.json';need(sha(targets)==req['target_sha256']==m['target_sha256'],'targets unchanged')
    names=sorted({c for v in obj(targets)['price_delay_d1'].values() for c in v['weights']})
    need(names==req['codes'] and len(names)==151 and set(m['per_code_sha256'])==set(names),'151 universe')
    need(obj(O/'progress.json')==m['per_code_sha256'] and obj(O/'errors.json')==m['errors_sha256']=={} and m['pending_codes']==[],'no error/pending')
    need(set(p.name for p in (O/'codes').iterdir())=={c+'.json' for c in names},'exact packet files')
    routes=req['reuse_routes'];fresh=req['fresh_codes'];need(len(routes)==129 and len(fresh)==22 and set(routes).isdisjoint(fresh) and sorted(set(routes)|set(fresh))==names and m['reuse_routes']==routes and m['fresh_codes']==fresh,'route scope')
    need(req['maximum_new_query_reservations']==88 and req['max_attempts_per_query']==1 and req['socket_timeout_seconds']==20 and req['baostock_version']=='0.9.4','query budget')
    query_files={};packets={};totals=Counter();reuse=[];noncash=[];without=[]
    for c in names:
        p=O/'codes'/(c+'.json');need(sha(p)==m['per_code_sha256'][c],'packet SHA '+c);v=obj(p);packets[c]=v;sym=c[:2].lower()+'.'+c[2:]
        need(v['instrument']==c and v['window']==[START,END],'issuer/window')
        need([r['date'] for r in v['bars']]==sessions,'exact bar coverage '+c)
        for r in v['bars']:
            need(set(r)==set(BF) and r['code']==sym and day(r['date']) and r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1'),'bar identity/state')
            for k in ('open','high','low','close','preclose','volume','amount'):
                need(not r[k] or D(r[k]).is_finite() and D(r[k])>=0,'finite nonnegative bar')
            if r['tradestatus']=='1':
                need(all(r[k] and D(r[k])>0 for k in ('open','high','low','close','preclose','volume')),'trading positive')
                need(D(r['high'])>=max(D(r['open']),D(r['close']))>=D(r['low']) and D(r['high'])>=min(D(r['open']),D(r['close']))>=D(r['low']),'OHLC bounds')
                need(D(r['volume'])==D(r['volume']).to_integral_value(),'shares integer volume')
        need(len(v['distributions'])==len({json.dumps(x,sort_keys=True) for x in v['distributions']}),'duplicate dividend row')
        for r in v['distributions']:
            need(set(r)==set(DF) and r['code']==sym and day(r['dividOperateDate']) and r['dividOperateDate'][:4] in ('2024','2025'),'distribution identity/date')
            for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):need(not r[k] or D(r[k]).is_finite() and D(r[k])>=0,'distribution numeric')
            if D(r['dividStocksPs'] or '0')>0 or D(r['dividReserveToStockPs'] or '0')>0:noncash.append({'instrument':c,'ex_date':r['dividOperateDate'],'source_record':r,'packet_sha256':sha(p)})
        for r in v['adjustments']:
            need(set(r)==set(AF) and r['code']==sym and day(r['dividOperateDate']),'adjustment identity/date')
            need(all(D(r[k]).is_finite() and D(r[k])>0 for k in ('foreAdjustFactor','backAdjustFactor','adjustFactor')),'positive adjustment factor')
            if not any(d['dividOperateDate']==r['dividOperateDate'] for d in v['distributions']):without.append({'instrument':c,'ex_date':r['dividOperateDate'],'adjustment_record':r,'packet_sha256':sha(p)})
        for key,field in [('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')]:totals[key]+=len(v[field])
        need(not v['quarantine'],'actual no quarantined rows')
        if c in routes:
            rt=routes[c];n=rt['directory'];need(n in ALLOWED and manifests[n]['per_code_sha256'][c]==rt['packet_sha256'],'reuse manifest identity')
            original=B/n/'codes'/(c+'.json');need(sha(original)==rt['packet_sha256'],'reused original bytes');old=obj(original);need(old['window']==[START,END] and old['instrument']==c,'physically pre2026 original')
            for field,clock in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:need(v[field]==[x for x in old[field] if START<=x[clock]<=END],'unchanged clipped economic source '+c)
            need(core(v)==core(old)==rt['pre2026_raw_core_sha256'],'normalized raw core')
            pr=v['provenance'];need(pr['kind']=='AUTHENTICATED_CLIPPED_REUSE' and pr['original_sha256']==rt['packet_sha256'] and pr['original_source_directory']==n and pr['original_window']==[START,END] and pr['source_contains_later_bytes'] is False and pr['original_provenance']==old.get('provenance') and pr['original_source_query_receipts']==old.get('source_query_receipts'),'reuse provenance')
            reuse.append({'instrument':c,'directory':n,'original_sha256':sha(original),'pre2026_raw_core_sha256':core(v)})
        else:
            receipts=v['source_query_receipts'];need(set(receipts)=={'daily','dividend2024','dividend2025','adjustments'},'four fresh receipts')
            projected={}
            for comp,receipt in receipts.items():
                expected_params=({'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'} if comp=='daily' else {'start_date':START,'end_date':END} if comp=='adjustments' else {'year':comp[-4:],'yearType':'operate'})
                paths={}
                for field in ('request','reserved','response'):
                    rel=receipt[field+'_file'];need(not Path(rel).is_absolute() and '..' not in Path(rel).parts,'receipt traversal');p1=O/rel;need(sha(p1)==receipt[field+'_sha256'],'receipt SHA');paths[field]=p1;query_files[rel]=sha(p1)
                identity=obj(paths['request']);key=canonical(identity)
                need(identity=={'source':'BaoStock','instrument':c,'component':comp,'parameters':expected_params,'raw_development_request_sha256':EXPECTED},'exact SDK request')
                need(paths['request'].parent==O/'queries'/key and paths['reserved'].name=='reserved-1.json' and paths['response'].name=='response-1.json','query directory/attempt1')
                reservation=obj(paths['reserved']);response=obj(paths['response']);need(reservation['identity_sha256']==key and reservation['attempt']==1,'unique reservation')
                need(response['status']=='CAPTURED' and response['identity_sha256']==key and response['reservation_sha256']==sha(paths['reserved']) and response['payload_sha256']==canonical(response['payload']),'response payload binding')
                need(datetime.fromisoformat(reservation['reserved_at_utc'])<=datetime.fromisoformat(response['payload']['captured_at_utc']),'reservation precedes capture')
                envelope=response['payload'];need(envelope['fields']==['provider_response'] and len(envelope['rows'])==1,'decoded SDK envelope');wire=envelope['rows'][0]
                need(wire['initial_error_code']=='0' and wire['final_error_code']=='0' and wire['iteration_error_type'] is None and wire['iteration_error'] is None,'SDK complete success')
                fields=BF if comp=='daily' else AF if comp=='adjustments' else DF;need(wire['fields']==fields,'source field schema');projected[comp]=projection(wire['rows'],fields)
                clock='date' if comp=='daily' else 'dividOperateDate'
                need(all(r['code']==sym and day(r[clock]) for r in projected[comp]),'no2026 response record')
                if comp.startswith('dividend'):need(all(r[clock][:4]==comp[-4:] for r in projected[comp]),'operate year query')
            need(projected['daily']==v['bars'] and projected['adjustments']==v['adjustments'] and projected['dividend2024']+projected['dividend2025']==v['distributions'],'fresh projection byte-value exact')
    actualquery={str(p.relative_to(O)):sha(p) for p in (O/'queries').rglob('*') if p.is_file()}
    need(actualquery==query_files and len(actualquery)==264 and len(list((O/'queries').iterdir()))==88,'exact88 complete logical queries/264files')
    need(m['query_reservations_consumed']==m['maximum_new_query_reservations']==88 and dict(totals)==m['totals'],'manifest totals')
    need(len(list(O.glob('login-reserved-*.json')))==len(list(O.glob('login-response-*.json')))==len(list(O.glob('logout-response-*.json')))==1,'one administrative login/cleanup')
    need(obj(O/'login-reserved-1.json')=={'attempt':1,'request_sha256':EXPECTED} and obj(O/'login-response-1.json')['error_code']=='0' and obj(O/'logout-response-1.json')['cleanup_called'] is True and obj(O/'logout-response-1.json')['error_code']=='0','login cleanup success')
    oldroot=B/'price-delay-clock-v2-pre2026-development-20261021';oldsummary=obj(oldroot/'summary.json');need(sha(oldroot/'summary.json')==req['screen_files_sha256']['experiments/qlib/price-delay-pre2026-development-results.json'],'old account summary unchanged')
    financial={}
    for label,result in oldsummary['results_by_extra_bps_and_family'].items():
        for n,h in result['artifact_sha256'].items():need(sha(oldroot/label/n)==h,'old financial unchanged');financial[label+'/'+n]=h
    need(len(financial)==42,'42 old financial files')
    report={'status':'PASS_INDEPENDENT_PRE2026_RAW_SOURCE_CAPTURE_AUDIT','request_sha256':EXPECTED,'freeze_commit':freeze,'manifest_sha256':sha(O/'manifest.json'),'audit_script_sha256':sha(Path(__file__)),'method_code_sha256':req['method_code_sha256'],'151_packet_sha256':m['per_code_sha256'],'source_window':[START,END],'sessions_per_packet':486,'totals_reconstructed':dict(totals),'129_reuse_authentication':reuse,'fresh_codes':fresh,'complete_logical_queries':88,'attempts_per_logical_query':1,'query_artifact_sha256':actualquery,'SDK_decoded_responses_all_successful':True,'new_query_parameters_exact_pre2026':True,'no_date_indexed_2026_response_records':True,'failed_or_unfinished_logical_queries':0,'login_attempts_observed':1,'logout_cleanup_success':True,'targets_unchanged':True,'old_summary_sha256':sha(oldroot/'summary.json'),'old42_financial_sha256':financial,'raw_distribution_row_count':totals['distributions'],'noncash_distribution_records':noncash,'adjustment_without_same_issuer_exdate_distribution':without,'primary_source_question_list_only':True,'corporate_action_admission':False,'PIT_or_historical_arrival_verified':False,'real_TCP_attempt_completeness_verified':False,'account_replay_performed':False,'portfolio_returns_computed':False,'uncapped_original_packets_opened':False,'repository_modified':False,'objective_achieved':False,'limitations':['Source capture and byte/value projection audit only; no corporate-action, tax, lifecycle or account admission.','Query ledger authenticates SDK-decoded responses and logical reservations, not every underlying TCP attempt.','Capture timestamps are2026; accepted date-indexed market/distribution records end2025. This is not a historical memory seal or PIT proof.','Noncash and adjustment-without-distribution records are primary-source questions, not inferred omissions, tax treatment or economic entitlements.'],'critical_or_important_findings':[]}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(OUT),'report_sha256':sha(OUT),'script_sha256':report['audit_script_sha256'],'packets':151,'queries':88,'totals':dict(totals),'noncash_rows':len(noncash),'adjustments_without_distribution':len(without)}))
if __name__=='__main__':main()
