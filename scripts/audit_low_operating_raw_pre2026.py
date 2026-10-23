"""Independent raw-packet/SDK-envelope lineage and risks; no new producer imports."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
FAMILY='operating_profit_prior_assets_bottom_decile_control'
CALENDAR='qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
OLD='experiments/qlib/audit_sources/2026-10-22-asset-expansion-raw-source-audit.py'
OLD_SHA='ba8a4a14c0e281629637e0239b95fefc5bf4e2f1911e48354878e4a4716ca770'
BAR=('date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST')
DIV=('code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate',
 'dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs')
ADJ=('code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor')


def need(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inventory_files(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def old_auditor(root=None):
    root=root or Path(__file__).resolve().parents[1];need(sha(root/OLD)==OLD_SHA,'original independent envelope checker')
    spec=importlib.util.spec_from_file_location('original_raw_source_checker',root/OLD);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def check_component(payload,fields,*,year=None):
    rows=old_auditor().envelope(payload,fields)
    if year is not None:
        for row in rows:
            at=row['dividOperateDate']
            if at:need(date.fromisoformat(at).isoformat()==at and int(at[:4])==year and START<=at<=END,'operation-year source cutoff')
    return rows


def fingerprint(packet):
    values={}
    for field,key in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        need(all(START<=r[key]<=END for r in packet[field]),'source data cutoff')
        values[field]=sorted(json.dumps(r,sort_keys=True,separators=(',',':')) for r in packet[field])
    values['quarantine']=sorted(json.dumps(r,sort_keys=True,separators=(',',':')) for r in packet['quarantine'])
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def packet_risks(packet,code,sessions):
    need(packet['instrument']==code and packet['window']==[START,END] and [r['date'] for r in packet['bars']]==sessions,'same issuer and complete exact raw source calendar')
    symbol=code[:2].lower()+'.'+code[2:];states=[]
    for row in packet['bars']:
        need(set(row)==set(BAR) and row['code']==symbol and START<=row['date']<=END and row['adjustflag']=='3'
            and row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'original unadjusted market identity/state')
        for field in BAR[2:9]:
            if row[field]:need(Decimal(row[field]).is_finite() and Decimal(row[field])>=0,'finite nonnegative source price/volume/amount')
        if row['tradestatus']=='1':
            need(all(row[f] and Decimal(row[f])>0 for f in ('open','high','low','close','preclose','volume')),'positive observed trading prices and volume')
            need(Decimal(row['high'])>=max(Decimal(row['open']),Decimal(row['close'])) and Decimal(row['low'])<=min(Decimal(row['open']),Decimal(row['close'])),'original OHLC envelope')
        if row['tradestatus']!='1' or row['isST']!='0':states.append({k:row[k] for k in ('date','tradestatus','isST')})
    noncash=[];unknown=[];dates=[]
    for row in packet['distributions']:
        need(set(row)==set(DIV) and row['code']==symbol and START<=row['dividOperateDate']<=END,'original distribution identity/operation date')
        dates.append(row['dividOperateDate'])
        for field in DIV[1:9]:
            if row[field]:need(date.fromisoformat(row[field]).isoformat()==row[field] and row[field]<=END,'no future corporate-action source date')
        for field in ('dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividReserveToStockPs'):
            if row[field]:need(Decimal(row[field]).is_finite() and Decimal(row[field])>=0,'finite nonnegative source dividend component')
        if any(Decimal(row[f] or '0')>0 for f in ('dividStocksPs','dividReserveToStockPs')):noncash.append(row)
        if any(not row[f] for f in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs')):unknown.append(row)
    adjustments=[]
    for row in packet['adjustments']:
        need(set(row)==set(ADJ) and row['code']==symbol and START<=row['dividOperateDate']<=END,'original adjustment identity/date')
        need(all(Decimal(row[k]).is_finite() and Decimal(row[k])>0 for k in ADJ[2:]),'positive finite adjustment references');adjustments.append(row['dividOperateDate'])
    for item in packet['quarantine']:
        for field in DIV[1:9]:
            value=item.get('record',{}).get(field)
            if value:need(date.fromisoformat(value).isoformat()==value and value<=END,'quarantined dates cannot cross source cutoff')
    return {'noncash_distributions_requiring_primary_review':noncash,'unknown_distribution_components_requiring_review':unknown,
        'duplicate_distribution_dates':[d for d,n in Counter(dates).items() if n>1],
        'adjustment_dates_without_vendor_distribution':sorted(set(adjustments)-set(dates)),
        'duplicate_adjustment_dates':[d for d,n in Counter(adjustments).items() if n>1],
        'quarantines':packet['quarantine'],'nonordinary_or_suspended_source_rows':states,'physical_account_admitted':False}


def resolve(key,root,base):
    prefix,name=key.split('/',1);need(prefix in ('repo','source') and not Path(name).is_absolute() and '..' not in Path(name).parts,'root-relative bound source')
    return (root if prefix=='repo' else base)/name


def audit(base,root,raw,request,expected):
    need(sha(request)==expected and (raw/'request.json').read_bytes()==request.read_bytes(),'frozen exact source request')
    r=read(request);inv=r['inventory'];need(r['status']=='FROZEN_LOW_OPERATING_FOLLOWUP_PRE2026_SOURCE_CAPTURE'
        and r['candidate']==CANDIDATE and r['target_family']==FAMILY and r['window']==[START,END]
        and len(r['codes'])==len(set(r['codes']))==43 and r['fresh_codes']==['SZ002326'] and len(r['reuse_routes'])==42
        and r['maximum_new_query_reservations']==4 and r['max_attempts_per_query']==r['maximum_administrative_login_attempts']==1
        and r['socket_timeout_seconds']==20 and r['baostock_version']=='0.9.4' and r['portfolio_returns_permitted'] is False and r['2026_values_permitted'] is False,
        'independent exact adaptive source budget/window')
    paths={k:resolve(k,root,base) for k in r['input_sha256']};paths['frozen_request']=request;want={**r['input_sha256'],'frozen_request':expected}
    for k,p in paths.items():need(sha(p)==want[k],'original source input before '+k)
    need(all(r['input_sha256'].get('repo/'+n)==h for n,h in r['method_sha256'].items()),'explicit source methods bound')
    selected=read(root/'experiments/qlib/low-operating-profitability-continuation.json')
    need(selected['candidate']==CANDIDATE and selected['original_target_family']==FAMILY and selected['selected_from_seen_development_control'] is True
        and selected['fresh_independent_hypothesis'] is False and selected['seen_operating_policies']==3 and selected['original_primary_lead'] is None,'adaptive selection cannot rewrite original rejection')
    targetfile=root/'experiments/qlib/operating-profitability-pre2026-targets.json';targets=read(targetfile)[FAMILY]
    need(sha(targetfile)==r['target_sha256']==selected['target_sha256'] and len(targets)==24
        and sorted({c for t in targets.values() for c in t['weights']})==r['codes']==inv['codes'],'complete unchanged selected targets')
    before=inventory_files(raw);m=read(raw/'manifest.json');outer=read(raw/'followup-terminal.json');need(m['capture_complete'] is True and m['all_source_calendars_complete'] is True
        and m['names']==m['requested_names']==43 and not m['errors_sha256'] and not m['pending_codes'] and outer['complete'] is True
        and outer['candidate']==CANDIDATE and outer['all_inputs_unchanged'] is True and outer['request_sha256']==expected
        and outer['shared_adapter_origin_status']==m['status']=='LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE','complete new wrapper and preserved adapter origin')
    need(not any('failure' in Path(n).name or n.startswith('.followup') for n in before),'no uncommitted/failure outer terminal')
    need(m['request_sha256']==expected and m['target_sha256']==r['target_sha256'] and sha(raw/'calendar.json')==m['calendar_sha256'],'capture manifest source identities')
    sessions=read(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END]
        and sessions==[d for d in (base/CALENDAR).read_text().splitlines() if START<=d<=END],'all actual486 source sessions')
    original=old_auditor(root);risk={};totals=Counter();overlaps=0
    for code in r['codes']:
        choices=inv['all_choices'][code];fingerprints=[]
        for item in choices:
            origin=base/item['file'];need(item['file']==item['directory']+'/codes/'+code+'.json' and sha(origin)==item['packet_sha256']
                and r['input_sha256'].get('source/'+item['file'])==item['packet_sha256'],'all registered original overlaps bound')
            packet=read(origin);packet_risks(packet,code,sessions);fp=fingerprint(packet)
            need(fp==item['fingerprint'] and item['complete_calendar'] is True,'complete original overlap economics');fingerprints.append(fp);overlaps+=1
        need(len(set(fingerprints))<=1,'all complete overlap actions/prices must agree')
        p=raw/'codes'/(code+'.json');need(sha(p)==m['per_code_sha256'][code],'captured packet byte hash');packet=read(p)
        if code in r['reuse_routes']:
            route=r['reuse_routes'][code];need(choices and route==choices[0] and p.read_bytes()==(base/route['file']).read_bytes(),'deterministic byte-identical source reuse')
        else:need(code=='SZ002326' and not choices,'only registered fresh code');original.journal_packet(raw,code,packet,expected)
        risk[code]=packet_risks(packet,code,sessions)
        for k,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[k]+=len(packet[field])
    need(set(m['per_code_sha256'])==set(r['codes']) and dict(totals)==m['totals'],'all captured packets and raw totals')
    need(len(list(raw.rglob('reserved-*.json')))==len(list(raw.rglob('response-*.json')))==m['query_reservations_consumed']==4,'exact four fresh response reservations')
    login,logout=read(raw/'login-response-1.json'),read(raw/'logout-response-1.json')
    need(login['error_code']==logout['error_code']=='0' and len(list(raw.glob('login-reserved-*.json')))==1,'one successful login/cleanup')
    for value in (m,outer,selected):
        for key in ('historical_arrival_verified','corporate_action_completeness_verified','physical_account_admitted','portfolio_return_computed','2026_values_read','objective_achieved'):
            if key in value:need(value[key] is False,'source support never becomes account or return admission')
    for k,p in paths.items():need(sha(p)==want[k],'original source input after '+k)
    need(inventory_files(raw)==before,'all raw capture outputs unchanged')
    return {'status':'PASS_SEPARATE_43_PACKET_ALL_OVERLAPS_AND_FOUR_SDK_ENVELOPES_NOT_ACCOUNT_ADMISSION','candidate':CANDIDATE,'request_sha256':expected,
        'audit_code_sha256':sha(Path(__file__)),'all_input_sha256':want,'all_capture_sha256':before,'names':43,'reused_original_packets':42,
        'registered_overlap_packets_checked':overlaps,'fresh_response_envelopes_redecoded':4,'totals':dict(totals),'source_risks':risk,
        'all_inputs_outputs_unchanged':True,'no_new_producer_imports':True,'same_researcher_and_shared_envelope_checker':True,
        'historical_arrival_verified':False,'corporate_action_completeness_verified':False,'physical_account_admitted':False,
        'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();target=Path(a.output);raw=Path(a.raw_dir).resolve();need(not target.exists() and not target.resolve().is_relative_to(raw),'fresh external source proof')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],raw,Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with target.open('x') as f:json.dump({'status':'FAILED_SEPARATE_LOW_OPERATING_RAW_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,indent=2)
        raise
    with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],result['totals'],flush=True)


if __name__=='__main__':main()
