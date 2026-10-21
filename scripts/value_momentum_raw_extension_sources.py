"""Immutable bounded composite source assembly, independently windowed to Oct20.

SDK-decoded responses are preserved before validation. No account or ROI runs.
"""
import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS,ADJUST_FIELDS,source_code
from scripts.capture_illiquidity_raw_development import preserve_response,unwrap_vendor_response,read_vendor_response
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,PRE_END,END='2023-12-29','2025-12-31','2026-10-20'
MAX_QUERIES=362

def day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('canonical source date required')
    return value

def number(value):
    n=Decimal(value)
    if not n.is_finite() or n<0:raise ValueError('finite nonnegative source value required')
    return n

def financial_core(row):
    return [row['date'],row['code'],*[str(number(row[k]).normalize()) if row[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],row['tradestatus'],row['isST']]

def dict_rows(fields,rows,expected):
    if tuple(fields)!=tuple(expected) or any(len(r)!=len(expected) for r in rows):raise ValueError('source schema changed')
    return [dict(zip(fields,r)) for r in rows]

def validate_bars(code,rows,start=START):
    symbol=source_code(code);dates=[]
    for r in rows:
        if (r['code']!=symbol or not start<=day(r['date'])<=END or r['adjustflag']!='3'
            or r['tradestatus'] not in ('0','1') or r['isST'] not in ('0','1')):raise ValueError('bar security/date/state/window changed')
        for k in ('open','high','low','close','preclose','volume','amount'):
            if r[k]:number(r[k])
        if r['tradestatus']=='1':
            if any(not r[k] or number(r[k])<=0 for k in ('open','high','low','close','preclose','volume')):raise ValueError('active bar incomplete')
            if not number(r['low'])<=min(number(r['open']),number(r['close']))<=max(number(r['open']),number(r['close']))<=number(r['high']):raise ValueError('OHLC bounds changed')
        dates.append(r['date'])
    if dates!=sorted(set(dates)):raise ValueError('duplicate or unordered source bars')

def validate_dividends(code,rows,year):
    accepted=[];quarantine=[];seen=set()
    for r in rows:
        if r['code']!=source_code(code):raise ValueError('dividend security changed')
        at=r['dividOperateDate']
        if not at:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':copy.deepcopy(r)});continue
        if day(at)[:4]!=str(year):raise ValueError('dividend requested year changed')
        if not START<=at<=END:
            quarantine.append({'reason':'AFTER_EXTENSION_CUTOFF' if at>END else 'BEFORE_EXTENSION_WINDOW','record':copy.deepcopy(r)});continue
        for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
            if r[k]:number(r[k])
        key=json.dumps(r,sort_keys=True)
        if key in seen:raise ValueError('duplicate distribution record')
        seen.add(key);accepted.append(copy.deepcopy(r))
    return accepted,quarantine

def validate_adjustments(code,rows,start=START):
    seen=set()
    for r in rows:
        if r['code']!=source_code(code) or not start<=day(r['dividOperateDate'])<=END:raise ValueError('adjustment security/window changed')
        key=json.dumps(r,sort_keys=True)
        if key in seen:raise ValueError('duplicate adjustment record')
        seen.add(key)

def expected_sessions(code,sessions,listed_on=None):
    if sessions!=sorted(set(sessions)) or any(not START<=day(d)<=END for d in sessions):raise ValueError('explicit ordered source calendar required')
    if listed_on is not None and (code!='SZ001389' or listed_on!='2024-04-02'):raise ValueError('unregistered listing exception')
    return [d for d in sessions if listed_on is None or d>=listed_on]

def verify_overlap(assembled,cached):
    if assembled['instrument']!=cached['instrument']:raise ValueError('overlap issuer changed')
    left={r['date']:financial_core(r) for r in assembled['bars']};right={r['date']:financial_core(r) for r in cached['bars'] if START<=r['date']<=END}
    if len(left)!=len(assembled['bars']) or len(right)!=sum(START<=r['date']<=END for r in cached['bars']):raise ValueError('duplicate cached dates')
    if any(left[d]!=right[d] for d in left.keys()&right.keys()):raise ValueError('registered common-date financial core conflict')
    lo=max(START,assembled['window'][0],cached['window'][0]);hi=min(END,assembled['window'][1],cached['window'][1])
    for k in ('distributions','adjustments'):
        a=[r for r in assembled[k] if lo<=r['dividOperateDate']<=hi];b=[r for r in cached[k] if lo<=r['dividOperateDate']<=hi]
        if a!=b:raise ValueError('registered cached corporate/adjustment conflict: '+k)

def baseline_from_cache(code,cached,sessions):
    if cached['instrument']!=code or cached['window'][0]>START or cached['window'][1]<PRE_END:raise ValueError('cache lacks complete old window')
    v={'instrument':code,'window':[START,PRE_END]}
    for k,f in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):v[k]=copy.deepcopy([r for r in cached[k] if START<=r[f]<=PRE_END])
    v['quarantine']=copy.deepcopy([q for q in cached.get('quarantine',[]) if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']<=PRE_END])
    if [r['date'] for r in v['bars']]!=[d for d in sessions if d<=PRE_END]:raise ValueError('new cached baseline requires complete486 sessions')
    return v

def compose_packet(code,source,baseline,sessions,*,caches=(),listed_on=None):
    if source['instrument']!=code:raise ValueError('source security changed')
    result={'instrument':code,'window':[START,END]}
    if baseline is not None and (baseline['instrument']!=code or baseline['window']!=[START,PRE_END]):raise ValueError('original pre2026 identity changed')
    for k,f in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        rows=source[k]
        if any(not source['window'][0]<=r[f]<=END for r in rows):raise ValueError('accepted source crossed window')
        if baseline is not None:
            if source['window'][0]<=START:
                old=[r for r in rows if r[f]<=PRE_END]
                same=([financial_core(r) for r in old]==[financial_core(r) for r in baseline[k]]) if k=='bars' else old==baseline[k]
                if not same:raise ValueError('original prefix rewritten: '+k)
            rows=baseline[k]+[r for r in rows if r[f]>PRE_END]
        result[k]=copy.deepcopy(rows)
    result['quarantine']=copy.deepcopy(baseline.get('quarantine',[]) if baseline else [])
    result['quarantine'].extend(copy.deepcopy([q for q in source.get('quarantine',[]) if baseline is None or not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']>PRE_END]))
    validate_bars(code,result['bars'])
    if [r['date'] for r in result['bars']]!=expected_sessions(code,sessions,listed_on):raise ValueError('missing source sessions; no price synthesis')
    for year in (2024,2025,2026):
        rows=[r for r in result['distributions'] if r['dividOperateDate'][:4]==str(year)]
        accepted,excluded=validate_dividends(code,rows,year)
        if accepted!=rows or excluded:raise ValueError('accepted distribution outside contract')
    if any(not START<=r['dividOperateDate']<=END for r in result['distributions']):raise ValueError('accepted distribution window')
    validate_adjustments(code,result['adjustments'])
    for cache in caches:verify_overlap(result,cache)
    return result

def partition(codes,baselines,cached):
    if codes!=sorted(set(codes)) or not set(baselines)<=set(codes) or not set(cached)<=set(codes):raise ValueError('fixed unique universe required')
    fresh=[c for c in codes if c not in cached];incremental=[c for c in fresh if c in baselines];cold=[c for c in fresh if c not in baselines]
    budget=3*len(incremental)+5*len(cold)
    if budget>MAX_QUERIES:raise ValueError('absolute362 query budget exceeded')
    return {'fresh':fresh,'incremental':incremental,'cold':cold,'budget':budget}

def fetch_packet(journal,code,request_sha,fetch,baseline):
    start='2026-01-01' if baseline is not None else START;receipts={}
    def get(component,params):
        value,receipts[component]=preserve_response(journal,{'source':'BaoStock','instrument':code,'component':component,'parameters':params,'composite_raw_extension_request_sha256':request_sha},lambda:fetch(code,component,params),unwrap_vendor_response)
        return value
    v=get('daily',{'start_date':start,'end_date':END,'frequency':'d','adjustflag':'3'})
    bars=dict_rows(v['fields'],v['rows'],BAR_FIELDS);validate_bars(code,bars,start)
    distributions=[];quarantine=[]
    for y in ((2026,) if baseline is not None else (2024,2025,2026)):
        v=get('dividend'+str(y),{'year':str(y),'yearType':'operate'});rows=dict_rows(v['fields'],v['rows'],DIVIDEND_FIELDS)
        accepted,excluded=validate_dividends(code,rows,y);distributions.extend(accepted);quarantine.extend(excluded)
    v=get('adjustments',{'start_date':start,'end_date':END});adjustments=dict_rows(v['fields'],v['rows'],ADJUST_FIELDS);validate_adjustments(code,adjustments,start)
    return {'instrument':code,'window':[start,END],'bars':bars,'distributions':distributions,'adjustments':adjustments,'quarantine':quarantine,'source_query_receipts':receipts}

def capture_packets(out,codes,sessions,baselines,cached,request_sha,fetch,*,overlaps=None,lifecycles=None,lineage=None,request_bytes=None):
    out=Path(out)
    if out.exists():raise ValueError('preserve existing capture; no resume')
    route=partition(codes,baselines,cached);overlaps=overlaps or {};lifecycles=lifecycles or {};lineage=lineage or {}
    if request_bytes is not None and hashlib.sha256(request_bytes).hexdigest()!=request_sha:raise ValueError('request byte identity changed')
    reused={c:compose_packet(c,p,baselines.get(c),sessions,caches=overlaps.get(c,[]),listed_on=lifecycles.get(c)) for c,p in cached.items()}
    out.mkdir(parents=True);(out/'codes').mkdir()
    if request_bytes is not None:(out/'request.json').write_bytes(request_bytes)
    atomic_json(out/'calendar.json',{'sessions':sessions});progress={};errors={};abnormal=None
    atomic_json(out/'progress.json',progress);atomic_json(out/'errors.json',errors)
    journal=QueryJournal(out,max_queries=max(1,route['budget']),max_attempts=1)
    def save(c,packet,source,kind):
        packet['provenance']={'kind':kind,'request_sha256':request_sha,'registered_source_lineage':copy.deepcopy(lineage.get(c,{})),
            'original_prefix_preserved':c in baselines,'baseline_provenance':copy.deepcopy(baselines.get(c,{}).get('provenance')),
            'baseline_source_query_receipts':copy.deepcopy(baselines.get(c,{}).get('source_query_receipts')),
            'source_provenance':copy.deepcopy(source.get('provenance')),'source_query_receipts':copy.deepcopy(source.get('source_query_receipts'))}
        if 'source_query_receipts' in source:packet['source_query_receipts']=copy.deepcopy(source['source_query_receipts'])
        path=out/'codes'/(c+'.json');atomic_json(path,packet);progress[c]=sha256_file(path);atomic_json(out/'progress.json',progress)
    try:
        for c,p in reused.items():save(c,p,cached[c],'AUTHENTICATED_CACHE_SUFFIX_WITH_PRESERVED_PREFIX')
        consecutive=0
        for c in route['fresh']:
            try:
                src=fetch_packet(journal,c,request_sha,fetch,baselines.get(c));packet=compose_packet(c,src,baselines.get(c),sessions,caches=overlaps.get(c,[]),listed_on=lifecycles.get(c))
                save(c,packet,src,'PRESERVED_PREFIX_JOURNALED_SUFFIX' if c in baselines else 'JOURNALED_FULL_WINDOW')
            except Exception as exc:
                (out/'errors').mkdir(exist_ok=True);path=out/'errors'/(c+'.json')
                write_packet_once(path,{'instrument':c,'error_type':type(exc).__name__,'error':str(exc),'request_sha256':request_sha,'source_responses_retained':True})
                errors[c]=sha256_file(path);atomic_json(out/'errors.json',errors);consecutive+=1
            else:consecutive=0
            print('composite raw source',c,'saved',len(progress),'errors',len(errors),flush=True)
            if consecutive>=3:atomic_json(out/'stopped.json',{'reason':'THREE_CONSECUTIVE_FAILED_CODES','last_instrument':c});break
    except BaseException as exc:
        abnormal={'error_type':type(exc).__name__,'error':str(exc)};raise
    finally:
        records=[json.loads((out/'codes'/(c+'.json')).read_text()) for c in progress]
        manifest={'status':'COMPOSITE_RAW_EXTENSION_CAPTURED_ADMISSION_SEPARATE','window':[START,END],'requested_names':len(codes),'names':len(progress),
            'request_sha256':request_sha,'calendar_sha256':sha256_file(out/'calendar.json'),'per_code_sha256':progress,'errors_sha256':errors,
            'pending_codes':[c for c in codes if c not in progress and c not in errors],'fresh_codes':route['fresh'],'reused_codes':sorted(cached),
            'baseline_codes':sorted(baselines),'incremental_codes':route['incremental'],'cold_codes':route['cold'],
            'maximum_source_reservations':route['budget'],'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'abnormal_exit':abnormal,'totals':{k:sum(len(p[k]) for p in records) for k in ('bars','distributions','adjustments','quarantine')},
            'admitted_for_account_replay':False,'historical_arrival_verified':False,'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
            'portfolio_returns_computed':False,'investment_rules_changed':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
    return manifest

class SourceSession:
    def __init__(self,out,request_sha,sdk):
        self.out=Path(out);self.request_sha=request_sha;self.sdk=sdk;self.attempted=False;self.failed=False;self.closed=False
    def __call__(self,code,component,parameters):
        if self.failed:raise RuntimeError('one administrative login already failed')
        if not self.attempted:
            self.attempted=True;write_packet_once(self.out/'login-reserved-1.json',{'attempt':1,'request_sha256':self.request_sha})
            record={}
            try:
                result=self.sdk.login();record={'error_code':result.error_code,'error_msg':result.error_msg}
                if result.error_code!='0':raise RuntimeError('administrative login failed')
            except Exception as exc:
                self.failed=True;write_packet_once(self.out/'login-response-1.json',{**record,'error_type':type(exc).__name__,'error':str(exc)});raise
            write_packet_once(self.out/'login-response-1.json',record)
        symbol=source_code(code)
        if component=='daily':r=self.sdk.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),**parameters)
        elif component in ('dividend2024','dividend2025','dividend2026'):r=self.sdk.query_dividend_data(symbol,**parameters)
        elif component=='adjustments':r=self.sdk.query_adjust_factor(symbol,**parameters)
        else:raise ValueError('unregistered source component')
        return read_vendor_response(r)
    def close(self):
        if self.closed:return
        self.closed=True;record={'login_attempted':self.attempted,'logout_attempted':self.attempted}
        if self.attempted:
            try:
                r=self.sdk.logout();record.update(error_code=getattr(r,'error_code',None),error_msg=getattr(r,'error_msg',None))
            except Exception as exc:record.update(error_type=type(exc).__name__,error=str(exc))
        write_packet_once(self.out/'cleanup.json',record)
