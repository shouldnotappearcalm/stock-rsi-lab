"""Fixed raw tails for all frozen dependencies; no strategy/account invocation."""
import copy
import hashlib
import json
from datetime import date,timedelta
from pathlib import Path

from scripts.fundamental_query_journal import QueryJournal
from scripts.inventory_asset_expansion_raw_horizon_v2 import (
    START,END,BAR_FIELDS,DIVIDEND_FIELDS,ADJUST_FIELDS,sha,read,save,day,canonical,
    validate_packet,compare_packets,
)


def next_day(at):
    return (date.fromisoformat(at)+timedelta(days=1)).isoformat()


def query_parameters(originals):
    allowed={('CN_STOCK_CALENDAR','calendar'):{'start_date':START,'end_date':END}}
    for code,p in sorted(originals.items()):
        start=next_day(p['window'][1])
        if start>END: raise ValueError('known prefix must require a bounded tail')
        allowed[code,'daily']={'start_date':start,'end_date':END,'frequency':'d','adjustflag':'3'}
        allowed[code,'dividend2026']={'year':'2026','yearType':'operate'}
        allowed[code,'adjustments']={'start_date':start,'end_date':END}
    return allowed


def parse_calendar(data,calendars):
    if data['fields']!=['calendar_date','is_trading_day']: raise ValueError('explicit calendar schema changed')
    rows=data['rows']; first,last=map(date.fromisoformat,(START,END))
    labels=[(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    if (any(not isinstance(r,list) or len(r)!=2 or r[1] not in ('0','1') for r in rows)
            or [r[0] for r in rows]!=labels or rows[-1][1]!='1'):
        raise ValueError('complete observed calendar flags through fixed cutoff required')
    sessions=[r[0] for r in rows if r[1]=='1']
    for name,old in calendars.items():
        if (not old or old!=sorted(set(old)) or old[0]!=START or old[-1]>=END
                or any(day(d)!=d for d in old) or [d for d in sessions if d<=old[-1]]!=old):
            raise ValueError('observed calendar contradicts original prefix: '+name)
    return sessions


def records(data,fields):
    if (data['fields']!=list(fields) or not isinstance(data['rows'],list)
            or any(not isinstance(r,list) or len(r)!=len(fields) or any(not isinstance(v,str) for v in r) for r in data['rows'])):
        raise ValueError('complete original source schema required')
    return [dict(zip(fields,row)) for row in data['rows']]


def assemble_packet(code,original,sessions,data):
    old_end=original['window'][1]; bars=records(data['daily'],BAR_FIELDS)
    if any(not old_end<day(r['date'])<=END for r in bars): raise ValueError('new bar outside bounded tail')
    dividends=[];quarantine=[]
    for r in records(data['dividend2026'],DIVIDEND_FIELDS):
        if r['code']!=code[:2].lower()+'.'+code[2:]: raise ValueError('distribution issuer changed')
        at=r['dividOperateDate']
        if not at:
            quarantine.append({'reason':'MISSING_OPERATE_DATE','record':r});continue
        if day(at)[:4]!='2026': raise ValueError('distribution operation year changed')
        if at>END:
            quarantine.append({'reason':'AFTER_CAPTURE_CUTOFF','record':r});continue
        dividends.append(r)
    old_2026=[canonical(r,'distributions') for r in original['distributions'] if r['dividOperateDate'].startswith('2026')]
    overlapping=[canonical(r,'distributions') for r in dividends if r['dividOperateDate']<=old_end]
    if old_2026!=overlapping: raise ValueError('fresh annual distribution prefix contradicts original')
    adjustments=records(data['adjustments'],ADJUST_FIELDS)
    if any(not old_end<day(r['dividOperateDate'])<=END for r in adjustments):
        raise ValueError('new adjustment outside bounded tail')
    packet={'instrument':code,'window':[START,END],
        'bars':copy.deepcopy(original['bars'])+bars,
        'distributions':copy.deepcopy(original['distributions'])+[r for r in dividends if r['dividOperateDate']>old_end],
        'adjustments':copy.deepcopy(original['adjustments'])+adjustments,
        'quarantine':copy.deepcopy(original['quarantine'])+quarantine}
    validate_packet(packet,code,sessions,[START,END])
    if compare_packets(original,packet): raise ValueError('assembled original prefix changed')
    return packet


def unwrap(payload):
    if payload['fields']!=['provider_response'] or len(payload['rows'])!=1:
        raise ValueError('retained SDK response envelope changed')
    r=payload['rows'][0]
    if r['iteration_error_type'] in ('KeyboardInterrupt','SystemExit'):
        exc=KeyboardInterrupt if r['iteration_error_type']=='KeyboardInterrupt' else SystemExit
        raise exc(r['iteration_error'])
    if r['initial_error_code']!='0' or r['final_error_code']!='0' or r['iteration_error_type'] is not None:
        raise RuntimeError('provider response error retained in query journal')
    return {'fields':r['fields'],'rows':r['rows']}


def capture_extension(out,originals,calendars,fetch,*,request_bytes,inputs):
    out=Path(out);codes=sorted(originals);budget=1+3*len(codes)
    if out.exists() or not codes or budget>142: raise ValueError('fresh bounded source attempt required')
    if any(sha(Path(n))!=h for n,h in inputs.items()): raise ValueError('bound input changed before capture')
    if not calendars: raise ValueError('authenticated original calendars required')
    reference=max(calendars.values(),key=lambda s:s[-1])
    for c,p in originals.items():
        prefix=[d for d in reference if d<=p['window'][1]]
        validate_packet(p,c,prefix,p['window'])
        if p['quarantine']: raise ValueError('unresolved original quarantine blocks extension')
    allowed=query_parameters(originals);request_sha=hashlib.sha256(request_bytes).hexdigest()
    (out/'codes').mkdir(parents=True);(out/'errors').mkdir()
    (out/'request.json').write_bytes(request_bytes);save(out/'inputs-before.json',inputs)
    journal=QueryJournal(out,max_queries=budget,max_attempts=1)
    progress={};errors={};totals={k:0 for k in ('bars','distributions','adjustments','quarantine')}
    stopped=False;abnormal=None;original_exception=None;calendar_sha=None;sessions=[];consecutive=0
    def get(code,component):
        params=allowed[code,component]
        payload,receipt=journal.query({'source':'BaoStock','instrument':code,'component':component,
            'parameters':params,'asset_expansion_extension_request_sha256':request_sha},
            lambda:fetch(code,component,params))
        return unwrap(payload),receipt
    def error(code,exc):
        path=out/'errors'/(code+'.json')
        save(path,{'instrument':code,'error_type':type(exc).__name__,'error':str(exc),'source_responses_retained':True})
        errors[code]=sha(path)
    try:
        try:
            calendar,receipt=get('CN_STOCK_CALENDAR','calendar')
            sessions=parse_calendar(calendar,calendars)
            save(out/'calendar.json',{'sessions':sessions,'raw_calendar':calendar,'source_query_receipt':receipt})
            calendar_sha=sha(out/'calendar.json')
        except Exception as exc:error('__calendar__',exc)
        if '__calendar__' not in errors:
            for code in codes:
                try:
                    data={};receipts={}
                    for component in ('daily','dividend2026','adjustments'):
                        data[component],receipts[component]=get(code,component)
                    packet=assemble_packet(code,originals[code],sessions,data)
                    packet['source_query_receipts']=receipts
                    packet['original_packet_semantic_sha256']=hashlib.sha256(
                        json.dumps(originals[code],sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    packet['request_sha256']=request_sha
                    path=out/'codes'/(code+'.json');save(path,packet);progress[code]=sha(path)
                    for k in totals:totals[k]+=len(packet[k])
                    consecutive=0
                except Exception as exc:
                    error(code,exc);consecutive+=1
                save(out/('progress-'+code+'.json'),{'per_code_sha256':dict(progress),'errors_sha256':dict(errors)})
                print('raw extension',code,'saved',len(progress),'errors',len(errors),flush=True)
                if consecutive>=3:stopped=True;break
    except BaseException as exc:
        original_exception=exc;abnormal={'error_type':type(exc).__name__,'error':str(exc)}
    changed=[];posthash_errors=[];persistence=[];finalization_exception=None
    for name,h in inputs.items():
        try:
            if sha(Path(name))!=h:changed.append(name)
        except BaseException as exc:
            changed.append(name);posthash_errors.append({'file':name,'error_type':type(exc).__name__,'error':str(exc)})
            if original_exception is None:
                original_exception=exc;abnormal={'error_type':type(exc).__name__,'error':str(exc)}
    def persist(name,value):
        nonlocal finalization_exception
        try:
            save(out/name,value);return True
        except BaseException as exc:
            persistence.append({'file':name,'error_type':type(exc).__name__,'error':str(exc)})
            if finalization_exception is None:finalization_exception=exc
            return False
    persist('inputs-after.json',{'all_inputs_unchanged':not changed,'changed_or_missing':changed,'posthash_errors':posthash_errors,'count':len(inputs)})
    result={'status':'ASSET_EXPANSION_RAW_EXTENSION_CAPTURED_ADMISSION_SEPARATE','window':[START,END],
        'request_sha256':request_sha,'requested_names':len(codes),'names':len(progress),'per_code_sha256':progress,
        'errors_sha256':errors,'pending_codes':[c for c in codes if c not in progress and c not in errors],
        'capture_complete':len(progress)==len(codes) and not errors and abnormal is None and not changed and not persistence,
        'stopped_after_three_failed_codes':stopped,'original_exception':abnormal,'maximum_source_reservations':budget,
        'query_reservations_consumed':len(list((out/'queries').rglob('reserved-*.json'))),
        'calendar_sha256':calendar_sha,'session_count':len(sessions),'totals':totals,
        'original_inputs_unchanged':not changed,'changed_or_missing_inputs':changed,'consumed_input_files':len(inputs),'posthash_errors':posthash_errors,'persistence_errors':persistence,
        'all_source_packet_prefixes_preserved':len(progress)==len(codes),'source_units':{'price':'CNY/share','volume':'shares','amount':'CNY'},
        'ready_for_separate_source_QA':len(progress)==len(codes) and not errors and not totals['quarantine'] and not changed and abnormal is None and not persistence,
        'SDK_decoded_responses_not_TCP_wire':True,'admitted_for_account_replay':False,
        'historical_observed_arrival_verified':False,'portfolio_returns_computed':False,'full_October_complete':False,'objective_achieved':False}
    if not result['capture_complete']:result['status']='INCOMPLETE_SOURCE_CAPTURE_RETAINED'
    if not persist('manifest.json',result):
        result['capture_complete']=False;result['ready_for_separate_source_QA']=False
        result['status']='INCOMPLETE_SOURCE_CAPTURE_RETAINED'
        if not persist('finalization-error.json',result):
            print('source finalization failures retained in foreground log',persistence,flush=True)
    if original_exception is not None:raise original_exception
    if finalization_exception is not None:raise finalization_exception
    return result
