"""Independent stdlib pre2026 SDK source/byte reuse audit; no SDK/project imports.
No account replay, strategy selection or corporate/tax/lifecycle admission.
"""
import argparse,hashlib,json,math,re,subprocess
from collections import Counter,defaultdict
from datetime import date,datetime
from decimal import Decimal as D
from pathlib import Path
START,END='2023-12-29','2025-12-31'
PRIORITY=['price-delay-raw-dev-20261021','low-beta60-raw-dev-20261021','szse-value-momentum-raw-dev-20261021','budgeted-residual-raw-dev-20261021','return-families-raw-dev-20261017','szse-value-raw-dev-20261017','illiquidity-raw-source-continuation-20261020']
BF=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DF=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
AF=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
COMPONENTS=('daily','dividend2024','dividend2025','adjustments')
INVENTORY_SHA='9fbfed7d880974a1e1f49193dae169a7c0416732123202a67ca327c5cae21eb4'
SNAPSHOT_SHA='41eaf2e807ab11743b1f52dbb6edb327b8aed0036c8dade816766df5e9c515f8'
TARGET_SHA='64dd4c589b3661aceb5b103bc336a889f68449089f6ce9c2aff4312a7c8373fc'

def need(v,label):
    if not v:raise AssertionError(label)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def obj(p):return json.loads(Path(p).read_bytes())
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def safe(root,name):
    n=Path(name);need(not n.is_absolute() and '..' not in n.parts,'unsafe relative path')
    p=(root/n).resolve();need(p.is_relative_to(root.resolve()),'escaped path');return p

def iso(d):
    need(isinstance(d,str) and date.fromisoformat(d).isoformat()==d,'ISO date');return d

def params(comp):
    if comp=='daily':return {'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'}
    if comp=='adjustments':return {'start_date':START,'end_date':END}
    need(comp in ('dividend2024','dividend2025'),'component');return {'year':comp[-4:],'yearType':'operate'}

def project(rows,fields,expected):
    need(fields==expected and all(isinstance(r,list) and len(r)==len(fields) for r in rows),'SDK columns/schema')
    return [dict(zip(fields,r)) for r in rows]

def divide_rows(rows,code,year):
    accepted=[];quarantine=[];seen=set();vendor=code[:2].lower()+'.'+code[2:]
    for row in rows:
        need(set(row)==set(DF) and row['code']==vendor,'distribution identity')
        at=row['dividOperateDate']
        if not at:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':row});continue
        iso(at);need(at[:4]==str(year),'operate year')
        if at>END:quarantine.append({'reason':'AFTER_CAPTURE_CUTOFF','record':row});continue
        if at<START:quarantine.append({'reason':'BEFORE_CAPTURE_WINDOW','record':row});continue
        for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
            need(not row[k] or D(row[k]).is_finite() and D(row[k])>=0,'nonnegative distribution ratio')
        h=canon(row);need(h not in seen,'duplicate distribution row');seen.add(h);accepted.append(row)
    return accepted,quarantine

def validate_packet(v,c,sessions):
    need(v['instrument']==c and v['window']==[START,END],'packet identity/window')
    vendor=c[:2].lower()+'.'+c[2:];days=[]
    for row in v['bars']:
        need(set(row)==set(BF) and row['code']==vendor and row['adjustflag']=='3','bar fields/security/raw')
        d=iso(row['date']);need(START<=d<=END and d in sessions,'bar date boundary');days.append(d)
        need(row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'explicit source state')
        for k in ('open','high','low','close','preclose','volume','amount'):
            need(not row[k] or D(row[k]).is_finite() and D(row[k])>=0,'bar nonnegative finite')
        if row['tradestatus']=='1':
            need(all(row[k] and D(row[k])>0 for k in ('open','high','low','close','preclose','volume')),'trading positive values')
            need(D(row['high'])>=max(D(row['open']),D(row['close']))>=min(D(row['open']),D(row['close']))>=D(row['low']),'OHLC range')
        if row['volume']:need(D(row['volume'])==D(row['volume']).to_integral_value(),'raw volume shares integer')
    need(days==sorted(set(days)),'unique ordered dates')
    for y in (2024,2025):
        a,q=divide_rows([r for r in v['distributions'] if r['dividOperateDate'][:4]==str(y)],c,y);need(not q,'no quarantined row admitted')
    need(all(START<=r['dividOperateDate']<=END and r['dividOperateDate'][:4] in ('2024','2025') for r in v['distributions']),'distribution cutoff')
    for row in v['adjustments']:
        need(set(row)==set(AF) and row['code']==vendor and START<=iso(row['dividOperateDate'])<=END,'adjustment identity/date')
        need(all(D(row[k]).is_finite() and D(row[k])>0 for k in AF[2:]),'positive adjustment values')
    need(len(v['adjustments'])==len({canon(r) for r in v['adjustments']}),'duplicate adjustment row')
    return {'full_explicit_calendar_covered':days==sessions,'observed_rows':len(days),'first_observed_session':days[0] if days else None,'last_observed_session':days[-1] if days else None,'missing_sessions':[d for d in sessions if d not in set(days)],'missing_sessions_classified_as_prelisting':False,'synthetic_source_rows_created':0}

def raw_core(v):
    return canon({k:sorted(v[k],key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False)) for k in ('bars','distributions','adjustments')})

def inspect_journal(out,fresh,request_sha):
    artifacts={};records={};statuses=Counter();reservations=0
    queryroot=out/'queries'
    for folder in sorted(queryroot.iterdir()) if queryroot.exists() else []:
        need(folder.is_dir() and re.fullmatch('[0-9a-f]{64}',folder.name),'query folder identity')
        files={p.name for p in folder.iterdir()};need(files<={'request.json','reserved-1.json','response-1.json'} and 'request.json' in files,'one attempt artifacts only')
        identity=obj(folder/'request.json');c=identity['instrument'];comp=identity['component']
        need(c in fresh and identity=={'source':'BaoStock','instrument':c,'component':comp,'parameters':params(comp),'raw_development_request_sha256':request_sha},'registered exact financial request')
        key=canon(identity);need(key==folder.name and (c,comp) not in records,'canonical unique query')
        for p in folder.iterdir():artifacts[str(p.relative_to(out))]=sha(p)
        rec={'identity':identity,'status':'REQUEST_WITHOUT_RESERVATION','request_file':str((folder/'request.json').relative_to(out))}
        if 'reserved-1.json' in files:
            reservation=obj(folder/'reserved-1.json');need(reservation['identity_sha256']==key and type(reservation['attempt']) is int and reservation['attempt']==1,'reservation identity/count')
            datetime.fromisoformat(reservation['reserved_at_utc']);reservations+=1;rec['status']='RESERVED_OUTCOME_UNKNOWN'
            if 'response-1.json' in files:
                response=obj(folder/'response-1.json');need(response['identity_sha256']==key and response['reservation_sha256']==sha(folder/'reserved-1.json'),'response-reservation binding')
                rec['response_status']=response['status']
                if response['status']=='SOURCE_ERROR':
                    need(response['error_type'] and isinstance(response['error'],str),'source exception evidence');rec['status']='SOURCE_ERROR';rec['error_type']=response['error_type']
                else:
                    need(response['status']=='CAPTURED' and canon(response['payload'])==response['payload_sha256'],'response payload hash')
                    payload=response['payload'];need(datetime.fromisoformat(reservation['reserved_at_utc'])<=datetime.fromisoformat(payload['captured_at_utc']),'query clock')
                    need(payload['fields']==['provider_response'] and len(payload['rows'])==1,'SDK decoded envelope')
                    wire=payload['rows'][0];need({'initial_error_code','initial_error_msg','final_error_code','final_error_msg','fields','rows','iteration_error_type','iteration_error'}<=set(wire),'retained SDK status fields')
                    rec['wire']=wire;rec['status']='SDK_SUCCESS' if wire['initial_error_code']==wire['final_error_code']=='0' and wire['iteration_error_type'] is None and wire['iteration_error'] is None else 'SDK_ERROR'
        else:need('response-1.json' not in files,'response cannot precede reservation')
        records[c,comp]=rec;statuses[rec['status']]+=1
    need(reservations<=240 and len(records)<=240,'bounded240 journal')
    return records,artifacts,dict(statuses),reservations

def verify_receipt(out,receipt,c,comp,records,artifacts):
    need((c,comp) in records and records[c,comp]['status']=='SDK_SUCCESS','accepted packet requires successful journal response')
    directory=Path(records[c,comp]['request_file']).parent
    for part,name in [('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')]:
        rel=receipt[part+'_file'];need(Path(rel)==directory/name and artifacts[rel]==receipt[part+'_sha256'],'packet receipt exact chain');safe(out,rel)
    w=records[c,comp]['wire'];return project(w['rows'],w['fields'],BF if comp=='daily' else AF if comp=='adjustments' else DF)

# Main captures schema is finalized when the independently reviewed wrapper is available.

def authenticate_inventory(repo,base,inventory_file,snapshot_file):
    watched={}
    def bind(path,expected):
        need(sha(path)==expected,'immutable source '+str(path));watched[str(path)]=expected
    bind(inventory_file,INVENTORY_SHA);inv=obj(inventory_file)
    need(inv['source_priority']==PRIORITY and inv['cross_cache_normalized_raw_core_conflicts']==[],'fixed pre2026 sources')
    target=base/'low-market-residual-vol1m-budgeted-pre2026-development-20261021/targets.json';bind(target,TARGET_SHA)
    targets=obj(target)['low_market_residual_vol_1m'];codes=sorted({c for v in targets.values() for c in v['weights']})
    need(len(targets)==24 and len(codes)==361 and inv['target_sha256']==TARGET_SHA,'target scope')
    bind(snapshot_file,SNAPSHOT_SHA);snap=obj(snapshot_file);need(snap['inventory_sha256']==INVENTORY_SHA and snap['target_sha256']==TARGET_SHA and snap['mandatory_target_snapshots']==1840 and snap['covered_snapshots']==1478 and snap['unknown_snapshots']==362,'mandatory snapshot inventory')
    need(snap['all_required_snapshots_ordinary_proven'] is False and snap['unknown_treated_as_pass'] is False,'unknown admission preserved')
    sources=inv['source_directories_checked'];need([x['directory'] for x in sources]==PRIORITY,'source priority')
    legacy=inv['legacy_source_request_anchor'];legacy_path=safe(repo,legacy['file']);bind(legacy_path,legacy['sha256']);legacyreq=obj(legacy_path)
    legacy_manifests={x['directory']:x['manifest_sha256'] for x in legacyreq['reuse_sources']}
    calendars={};all_options=defaultdict(list);packet_values={}
    for entry in sources:
        name=entry['directory'];root=safe(base,name);bind(root/'manifest.json',entry['manifest_sha256']);m=obj(root/'manifest.json')
        need(m['window']==[START,END] and m['new_2026_market_queries'] is False,'bounded old source')
        bind(root/'calendar.json',entry['calendar_sha256']);need(m['calendar_sha256']==entry['calendar_sha256'],'old calendar identity')
        sessions=obj(root/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and sessions[0]==START and sessions[-1]==END,'old486calendar');calendars[name]=sessions
        anchor=entry['audit_anchor'];ap=safe(repo,anchor['file']);bind(ap,anchor['sha256']);audit=obj(ap)
        if 'authenticated_source_manifest_via_request' in anchor:
            bind(safe(repo,anchor['authenticated_source_manifest_via_request']),anchor['request_sha256'])
            need(legacy_manifests[name]==entry['manifest_sha256'] and audit['request_sha256']==legacy['sha256'] and audit['capture_complete'] is True and audit['all5_authenticated_cache_calendars_identical_486'] is True,'legacy manifest audit chain')
        else:
            actual=audit.get('capture_manifest_sha256',audit.get('manifest_sha256',audit.get('raw_manifest_sha256')))
            need(actual==entry['manifest_sha256'],'source independent audit anchor')
        for c in sorted(set(codes)&set(m['per_code_sha256'])):
            p=root/'codes'/(c+'.json');bind(p,m['per_code_sha256'][c]);v=obj(p);diagnostic=validate_packet(v,c,sessions);need(not v['quarantine'],'historical quarantine-free inventory scope')
            existing=next(x for x in inv['per_instrument'][c]['all_registered_pre2026_cache_options'] if x['directory']==name)
            need(existing['packet_sha256']==sha(p) and existing['raw_core_sha256']==raw_core(v) and existing['missing_sessions']==diagnostic['missing_sessions'] and existing['complete_486_session_calendar']==diagnostic['full_explicit_calendar_covered'],'inventory option exact')
            all_options[c].append(existing);packet_values[c,name]=v
    calendar=calendars[PRIORITY[0]];need(all(x==calendar for x in calendars.values()) and canon(calendar)==inv['canonical_calendar_dates_sha256'],'seven common explicit calendars')
    routes={}
    for c in codes:
        options=all_options[c];need(options==inv['per_instrument'][c]['all_registered_pre2026_cache_options'],'all registered options covered')
        full=[v for v in options if v['complete_486_session_calendar']]
        need(len({v['raw_core_sha256'] for v in full})<=1,'full cache economic source conflict')
        if full:routes[c]=full[0]
    need(routes==inv['selected_reuse'] and len(routes)==301,'priority301byte reuse')
    fresh=sorted(set(codes)-set(routes));need(fresh==inv['missing_or_incomplete_instruments'] and len(fresh)==60,'fresh60scope')
    incomplete=[{'instrument':c,'directory':x['directory'],'packet_sha256':x['packet_sha256'],'missing_sessions':x['missing_sessions'],'missing_sessions_classified_as_prelisting':False} for c in codes for x in all_options[c] if not x['complete_486_session_calendar']]
    covered=[];unknown=[];conflict=[]
    for execution,t in targets.items():
        for c,w in t['weights'].items():
            need(w>0 and START<=t['as_of']<execution<=END,'mandatory target clock')
            if c not in routes:unknown.append((c,t['as_of']));continue
            v=packet_values[c,routes[c]['directory']];row=next(x for x in v['bars'] if x['date']==t['as_of']);covered.append((c,t['as_of']))
            if row['isST']!='0' or row['tradestatus']!='1':conflict.append((c,t['as_of']))
    need(len(covered)==1478 and len(unknown)==362 and not conflict,'independent mandatory snapshot counts')
    return inv,targets,codes,routes,fresh,calendar,watched,incomplete

def negative_controls():
    results={}
    row=dict(zip(BF,['2024-01-02','sh.600000','10','11','9','10','10','100','1000','3','1','0']))
    packet={'instrument':'SH600000','window':[START,END],'bars':[row],'distributions':[],'adjustments':[],'quarantine':[]}
    cal=['2024-01-02','2024-01-03']
    need(validate_packet(packet,'SH600000',cal)['missing_sessions']==['2024-01-03'],'partial remains missing')
    cases={'future_date':('date','2026-01-05'),'wrong_security':('code','sh.600001'),'adjusted_quote':('adjustflag','2'),'negative_price':('open','-1'),'fractional_share_volume':('volume','100.5'),'OHLC_conflict':('high','9'),'unknown_isST':('isST','')}
    for label,(k,value) in cases.items():
        bad=json.loads(json.dumps(packet));bad['bars'][0][k]=value
        try:validate_packet(bad,'SH600000',cal)
        except (AssertionError,ValueError):results[label]=True
        else:raise AssertionError('negative escaped '+label)
    bad=json.loads(json.dumps(packet));bad['bars'].append(dict(row))
    try:validate_packet(bad,'SH600000',cal)
    except AssertionError:results['duplicate_date']=True
    else:raise AssertionError('duplicate date escaped')
    div=dict.fromkeys(DF,'');div['code']='sh.600000';div['dividCashPsBeforeTax']='NOT_A_NUMBER'
    accepted,quarantine=divide_rows([div],'SH600000',2024)
    need(not accepted and quarantine==[{'reason':'MISSING_OPERATE_DATE','record':div}],'quarantine before amount parse');results['quarantine_does_not_parse_unadmitted_amount']=True
    return results

def run(args):
    repo=Path(args.repo_root).resolve();base=Path(args.source_root).resolve();request=Path(args.request).resolve();out=base/'low-market-residual-vol1m-raw-pre2026-20261021'
    need(sha(request)==args.expected_request_sha256,'external request digest');req=obj(request)
    freeze=subprocess.check_output(['git','rev-parse',args.freeze_commit],cwd=repo,text=True).strip()
    need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(request.relative_to(repo))],cwd=repo)).hexdigest()==args.expected_request_sha256,'frozen request bytes')
    invfile=repo/'experiments/qlib/low-market-residual-vol1m-pre2026-raw-source-inventory.json';snapfile=repo/'experiments/qlib/low-market-residual-vol1m-pre2026-mandatory-snapshot-inventory.json'
    inv,targets,codes,routes,fresh,sessions,watched,incomplete=authenticate_inventory(repo,base,invfile,snapfile)
    need(req['status']=='FROZEN_LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCE_REQUEST' and req['candidate']=='low_market_residual_vol_1m' and req['window']==[START,END],'source request identity')
    need(req['inventory_sha256']==INVENTORY_SHA and req['mandatory_snapshot_inventory_sha256']==SNAPSHOT_SHA and req['codes']==codes and req['reuse_routes']==routes and req['fresh_codes']==fresh,'registered routing')
    need(req['maximum_new_query_reservations']==240 and req['max_attempts_per_query']==1 and req['maximum_administrative_login_attempts']==1 and req['maximum_consecutive_failed_fresh_codes']==3 and req['socket_timeout_seconds']==20 and req['baostock_version']=='0.9.4','frozen query/administrative budgets')
    def bind(p,h):need(sha(p)==h,'bound bytes '+str(p));watched[str(p)]=h
    bind(request,args.expected_request_sha256)
    need(set(req['method_code_sha256'])=={'scripts/capture_budgeted_residual_raw_pre2026.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_frozen_target_development_data.py','scripts/capture_illiquidity_raw_development.py','scripts/capture_low_risk_raw_account_data.py','scripts/fundamental_query_journal.py','scripts/capture_low_market_residual_vol_raw_pre2026.py'},'exact capture method set')
    for n,h in req['method_code_sha256'].items():
        bind(safe(repo,n),h);need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=repo)).hexdigest()==h,'frozen capture method '+n)
    screen=['experiments/qlib/low-market-residual-vol1m-budgeted-pre2026-results.json','experiments/qlib/low-market-residual-vol1m-budgeted-development-independent-audit.json','experiments/qlib/low-market-residual-vol1m-budgeted-pre2026-verification.json']
    need(set(req['screen_files_sha256'])==set(screen),'exact prior screen files')
    for n,h in req['screen_files_sha256'].items():bind(safe(repo,n),h)
    need(req['protocol_file']=='docs/research/low-market-residual-vol1m-raw-source-plan-2026-10-21.md','exact protocol');bind(safe(repo,req['protocol_file']),req['protocol_sha256'])
    prior=base/'low-market-residual-vol1m-budgeted-pre2026-development-20261021';audit=obj(repo/screen[1]);summary=obj(prior/'summary.json')
    bind(prior/'summary.json',audit['summary_sha256']);financial={f'{case}/{n}':h for case,v in summary['results_by_extra_bps_and_family'].items() for n,h in v['artifact_sha256'].items()}
    need(len(financial)==42 and financial==req['immutable_financial_sha256']==audit['financial_artifact_hashes_verified'],'canonical42oldfinancial')
    for n,h in financial.items():bind(safe(prior,n),h)
    need(audit['selected_development_lead']=='low_market_residual_vol_1m' and audit['critical_or_important_audit_findings']==[] and summary['targets_sha256']==TARGET_SHA,'prior development gate/evidence')
    need(req['target_sha256']==TARGET_SHA and req['reference_calendar_file']=='qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt','frozen target/calendar')
    cp=safe(base,req['reference_calendar_file']);bind(cp,req['reference_calendar_sha256']);need([d for d in cp.read_text().splitlines() if START<=d<=END]==sessions,'reference calendar486')
    need(req['reuse_sources']==[{k:e[k] for k in ('directory','manifest_sha256','calendar_sha256')} for e in inv['source_directories_checked']],'seven registered sources')
    m=obj(out/'manifest.json');need(sha(out/'request.json')==args.expected_request_sha256==m['request_sha256'],'copied request')
    need(m['status']=='LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE' and m['window']==[START,END] and m['requested_names']==361,'manifest identity')
    need(sha(out/'calendar.json')==m['calendar_sha256'] and obj(out/'calendar.json')=={'sessions':sessions,'origin_sha256':req['reference_calendar_sha256'],'clipped_to':[START,END]},'output calendar exact')
    progress=obj(out/'progress.json');errors=obj(out/'errors.json');need(progress==m['per_code_sha256'] and errors==m['errors_sha256'] and not set(progress)&set(errors) and (set(progress)|set(errors))<=set(codes),'terminal partitions')
    pending=[c for c in codes if c not in progress and c not in errors];need(pending==m['pending_codes'] and len(progress)==m['names'],'pending/count exact')
    need({p.name for p in (out/'codes').iterdir()}=={c+'.json' for c in progress},'exact saved packet set')
    need({p.name for p in (out/'errors').iterdir()}=={c+'.json' for c in errors},'exact preserved error set')
    for c,h in errors.items():
        path=out/'errors'/(c+'.json');need(sha(path)==h,'source error SHA');er=obj(path);need(er['instrument']==c and er['request_sha256']==args.expected_request_sha256 and er['raw_responses_retained'] is True and er['error_type'],'source error evidence')
    records,queryhashes,statuses,count=inspect_journal(out,set(fresh),args.expected_request_sha256)
    need(count==m['query_reservations_consumed'] and m['maximum_new_query_reservations']==240,'reservation budget count')
    expectedroutes={c:{'path':str(safe(base,v['file'])),'packet_sha256':v['packet_sha256'],'directory':v['directory'],'file':v['file']} for c,v in routes.items()}
    need(obj(out/'reuse-routes.json')==m['reuse_routes']==expectedroutes and m['fresh_codes']==fresh,'byte reuse sidecar exact')
    totals=Counter(dict(bar_rows=0,distributions=0,adjustments=0,quarantines=0));diagnostics={};packets={};noncash=[];unmatched=[];reuse=[];quarantines=[]
    for c,h in progress.items():
        path=out/'codes'/(c+'.json');need(sha(path)==h,'packet hash '+c);v=obj(path);packets[c]=v;diagnostics[c]=validate_packet(v,c,sessions)
        for k,f in [('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')]:totals[k]+=len(v[f])
        if c in routes:
            origin=safe(base,routes[c]['file']);need(h==routes[c]['packet_sha256']==sha(origin) and path.read_bytes()==origin.read_bytes(),'literal reused packet/provenance unchanged')
            need(diagnostics[c]['full_explicit_calendar_covered'],'selected reuse complete486');reuse.append({'instrument':c,'original_file':routes[c]['file'],'sha256':h})
        else:
            need(set(v['source_query_receipts'])==set(COMPONENTS),'four fresh receipts')
            projected={comp:verify_receipt(out,v['source_query_receipts'][comp],c,comp,records,queryhashes) for comp in COMPONENTS}
            accepted=[];quarantined=[]
            for year in (2024,2025):
                a,q=divide_rows(projected['dividend'+str(year)],c,year);accepted+=a;quarantined+=q
            need(v['bars']==projected['daily'] and v['adjustments']==projected['adjustments'] and v['distributions']==accepted and v['quarantine']==quarantined,'exact journal to packet projection')
            need(v['provenance']=={'kind':'JOURNALED_PRE2026_RAW_SOURCE','request_sha256':args.expected_request_sha256,'query_end':END,'calendar_complete_not_assumed':True},'fresh provenance')
        for row in v['distributions']:
            if D(row['dividStocksPs'] or '0')>0 or D(row['dividReserveToStockPs'] or '0')>0:noncash.append({'instrument':c,'ex_date':row['dividOperateDate'],'source_record':row,'packet_sha256':h})
        for row in v['adjustments']:
            if not any(x['dividOperateDate']==row['dividOperateDate'] for x in v['distributions']):unmatched.append({'instrument':c,'ex_date':row['dividOperateDate'],'source_record':row,'packet_sha256':h})
        if v['quarantine']:quarantines.append({'instrument':c,'row_count':len(v['quarantine']),'packet_sha256':h,'record_hashes':[canon(q) for q in v['quarantine']]})
    need(dict(totals)==m['totals'] and diagnostics==m['calendar_diagnostics'],'totals and complete/missing calendar reconstruction')
    need(m['all_source_calendars_complete']==(len(diagnostics)==361 and all(d['full_explicit_calendar_covered'] for d in diagnostics.values())),'source calendar completeness flag')
    # The ordered driver cannot query later codes after three consecutive errors.
    consecutive=0;stop_at=None
    for c in fresh:
        if c in errors:consecutive+=1
        elif c in progress:consecutive=0
        if consecutive==3:stop_at=c;break
    if stop_at:
        need(obj(out/'stopped.json')=={'reason':'THREE_CONSECUTIVE_FAILED_FRESH_CODES','last_instrument':stop_at},'three-code stop retained')
        need(not any(c in {k[0] for k in records} for c in fresh[fresh.index(stop_at)+1:]),'no query after failure stop')
    else:need(not (out/'stopped.json').exists(),'no spurious failure stop')
    cleanup=obj(out/'cleanup.json');post=obj(out/'input-postcheck.json')
    need(sha(out/'cleanup.json')==m['cleanup_sha256'] and sha(out/'input-postcheck.json')==m['postcheck_sha256'],'cleanup/postcheck artifact hashes')
    loginfiles=list(out.glob('login-reserved-*.json'));need(len(loginfiles)<=1 and {x.name for x in loginfiles}<={'login-reserved-1.json'},'single administrative login')
    login={}
    if loginfiles:
        need(obj(loginfiles[0])=={'attempt':1,'request_sha256':args.expected_request_sha256},'login reservation')
        login=obj(out/'login-response-1.json');need(login['login_attempted'] is True and cleanup['login_attempted'] is True and cleanup['logout_attempted'] is True and obj(out/'logout-response-1.json')==cleanup,'login/cleanup result retained')
    else:need(not records and not cleanup['login_attempted'],'no financial queries without login')
    need(not list(out.glob('login-response-[2-9]*.json')) and not list(out.glob('logout-response-[2-9]*.json')),'no administrative retry')
    if m['abnormal_exit'] is not None:need(obj(out/'terminal-error.json')==m['abnormal_exit'],'abnormal exit preserved')
    else:need(not (out/'terminal-error.json').exists(),'no omitted abnormal exit')
    input_before=obj(out/'input-before.json')
    for n,h in input_before.items():need(sha(n)==h,'producer post-input immutable '+n)
    for n,h in watched.items():need(sha(n)==h,'independent post-input immutable '+n)
    need(post['source_inputs_unchanged_after_capture'] is True,'source postcheck passed')
    complete=(set(progress)==set(codes) and not errors and not pending and m['abnormal_exit'] is None and login.get('error_code')=='0' and cleanup.get('error_code')=='0' and 'error' not in cleanup and count==240 and statuses=={'SDK_SUCCESS':240})
    need(type(m['capture_complete']) is bool and m['capture_complete']==complete,'honest terminal capture completion')
    for k in ('missing_rows_synthesized','admitted_for_account_replay','corporate_action_completeness_verified','historical_arrival_verified','portfolio_return_computed','new_2026_market_queries','strategy_or_targets_changed','objective_achieved'):need(m[k] is False,'no unearned admission '+k)
    snapshot_counts=Counter();snapshot_issues=[]
    for execution,t in targets.items():
        for c in t['weights']:
            matches=[row for row in packets.get(c,{}).get('bars',[]) if row['date']==t['as_of']]
            if not matches:state='UNKNOWN_MISSING_SOURCE'
            elif matches[0]['isST']=='1':state='IS_ST_SOURCE'
            elif matches[0]['tradestatus']=='0':state='HALTED_SOURCE'
            else:state='ORDINARY_TRADED_SOURCE_SNAPSHOT_ONLY'
            snapshot_counts[state]+=1
            if state!='ORDINARY_TRADED_SOURCE_SNAPSHOT_ONLY':snapshot_issues.append({'instrument':c,'as_of':t['as_of'],'execution_session':execution,'source_state':state})
    need(sum(snapshot_counts.values())==1840,'mandatory snapshots conserved')
    negative=negative_controls();tree={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    report={'status':'PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT' if complete else 'PASS_AUDIT_OF_PRESERVED_INCOMPLETE_CAPTURE','capture_complete':complete,'request_sha256':args.expected_request_sha256,'freeze_commit':freeze,'manifest_sha256':sha(out/'manifest.json'),'audit_script_sha256':sha(Path(__file__)),'packet_sha256':progress,'error_sha256':errors,'pending_codes':pending,'complete_packets_saved':len(progress),'reused_packets_byte_exact':len(reuse),'source_window':[START,END],'explicit_sessions':486,'all_source_calendars_complete':m['all_source_calendars_complete'],'partial_source_calendars':{c:d for c,d in diagnostics.items() if not d['full_explicit_calendar_covered']},'original_partial_cache_references_preserved':incomplete,'totals_reconstructed':dict(totals),'query_reservations_consumed':count,'maximum_financial_query_budget':240,'query_status_counts':statuses,'query_artifact_sha256':queryhashes,'whole_capture_tree_sha256':tree,'old42_financial_sha256':financial,'original_input_hashes_rechecked':watched,'login_attempts':len(loginfiles),'cleanup':cleanup,'source_postcheck':post,'quarantined_records':quarantines,'noncash_distribution_records':noncash,'adjustment_without_same_exdate_distribution':unmatched,'mandatory_snapshot_counts':dict(snapshot_counts),'mandatory_snapshot_issues':snapshot_issues,'negative_controls':negative,'critical_or_important_findings':[],'admitted_for_account_replay':False,'corporate_action_completeness_verified':False,'tax_or_lifecycle_verified':False,'PIT_or_historical_arrival_verified':False,'network_used_by_auditor':False,'portfolio_returns_computed':False,'account_replay_performed':False,'repository_modified':False,'limitations':['Source/SDK decoded response chain only; logical reservations do not certify every underlying TCP attempt.','Missing dates remain unexplained source gaps: no IPO, delisting or suspension classification and no synthetic row.','Dividend/adjustment relationships and noncash rows are issuer-primary evidence questions, not inferred entitlements or tax clearance.','Ordinary target snapshots do not certify full future holdings/orders/entitlement dependency intervals.','All accepted date-indexed records are pre2026; capture timestamps and quarantined unadmitted bytes do not establish historical arrival.']}
    destination=Path(args.output).resolve();need(not destination.exists() and not destination.is_relative_to(repo) and not destination.is_relative_to(out),'new external audit output required')
    with destination.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(destination),'sha256':sha(destination),'script_sha256':sha(Path(__file__)),'capture_complete':complete,'saved':len(progress),'queries':count,'partial_calendar_names':len(report['partial_source_calendars']),'negative_controls':len(negative)}))


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',default='/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');p.add_argument('--source-root',default='/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
    for n in ('request','expected-request-sha256','freeze-commit','output'):p.add_argument('--'+n,required=True)
    run(p.parse_args())

if __name__=='__main__':cli()
