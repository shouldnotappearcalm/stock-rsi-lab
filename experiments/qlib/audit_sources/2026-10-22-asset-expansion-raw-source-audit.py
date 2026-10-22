"""Separate original-file and SDK-envelope QA; stdlib only, no production imports."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

START,END='2023-12-29','2025-12-31'
BAR=('date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST')
DIV=('code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate',
     'dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate',
     'dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs')
ADJ=('code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor')


def need(condition,message):
    if not condition:raise ValueError(message)


def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def envelope(payload,fields):
    need(payload['fields']==['provider_response'] and len(payload['rows'])==1,'one SDK envelope')
    v=payload['rows'][0]
    need(v['initial_error_code']==v['final_error_code']=='0' and v['iteration_error_type'] is None
         and v['iteration_error'] is None and v['fields']==list(fields),'successful complete SDK schema')
    need(all(len(r)==len(fields) and all(isinstance(c,str) for c in r) for r in v['rows']),'rectangular string source rows')
    return [dict(zip(fields,r)) for r in v['rows']]


def journal_packet(raw,code,packet,request_sha):
    receipts=packet['source_query_receipts'];need(set(receipts)=={'daily','dividend2024','dividend2025','adjustments'},'all four source components')
    response_rows={};bound={}
    for component,receipt in receipts.items():
        paths={}
        for label in ('request','reserved','response'):
            rel=Path(receipt[label+'_file']);need(not rel.is_absolute() and '..' not in rel.parts,'local source receipt path')
            path=raw/rel;need(sha(path)==receipt[label+'_sha256'],'unchanged journal '+label);paths[label]=path;bound[str(rel)]=sha(path)
        q,r,s=(read(paths[n]) for n in ('request','reserved','response'));key=digest(q)
        parameters=({'start_date':START,'end_date':END,'frequency':'d','adjustflag':'3'} if component=='daily'
            else {'year':component[-4:],'yearType':'operate'} if component.startswith('dividend')
            else {'start_date':START,'end_date':END})
        need(q=={'source':'BaoStock','instrument':code,'component':component,'parameters':parameters,
            'raw_development_request_sha256':request_sha},'exact frozen query identity and cutoff')
        need(r['identity_sha256']==key and r['attempt']==1 and s['identity_sha256']==key
            and s['reservation_sha256']==sha(paths['reserved']) and s['status']=='CAPTURED'
            and s['payload_sha256']==digest(s['payload']),'one-attempt response checksum chain')
        response_rows[component]=envelope(s['payload'],BAR if component=='daily' else DIV if component.startswith('dividend') else ADJ)
    need(packet['bars']==response_rows['daily'] and packet['adjustments']==response_rows['adjustments'],'unaltered bar/adjustment decoding')
    accepted=[];quarantine=[]
    for year in (2024,2025):
        for row in response_rows['dividend'+str(year)]:
            at=row['dividOperateDate']
            if not at:quarantine.append({'reason':'MISSING_OPERATE_DATE','record':row})
            else:
                need(date.fromisoformat(at).isoformat()==at and int(at[:4])==year and START<=at<=END,'operation-year cutoff')
                accepted.append(row)
    need(packet['distributions']==accepted and packet['quarantine']==quarantine,'all accepted and quarantined response rows retained')
    return bound


def inventory_files(directory):return {str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file()}


def audit(base,repo,raw,request_path,expected):
    need(sha(request_path)==expected and (raw/'request.json').read_bytes()==request_path.read_bytes(),'frozen source request')
    req=read(request_path);inv=req['inventory'];manifest=read(raw/'manifest.json');before=inventory_files(raw)
    need(manifest['status']=='ASSET_EXPANSION_RAW_CAPTURE_COMPLETE_NOT_ADMITTED' and manifest['names']==36
        and manifest['requested_names']==36 and not manifest['errors_sha256'] and not manifest['pending_codes']
        and manifest['request_sha256']==expected and manifest['original_inputs_unchanged'] is True,'complete source capture')
    dependencies={request_path:expected,repo/req['protocol_file']:req['protocol_sha256']}
    for n,h in req['method_code_sha256'].items():dependencies[repo/n]=h
    for n,h in inv['public_evidence_sha256'].items():dependencies[repo/n]=h
    for n,h in inv['source_manifests_sha256'].items():dependencies[base/n/'manifest.json']=h
    calendar_path=base/'qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
    dependencies[calendar_path]=inv['reference_calendar_sha256']
    targets=base/'asset-expansion-conditional-development-v1-20261022/targets.json';dependencies[targets]=inv['target_sha256']
    for p,h in dependencies.items():need(sha(p)==h,'original input before '+str(p))
    need(sha(raw/'calendar.json')==manifest['calendar_sha256'],'captured calendar hash')
    sessions=read(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions))
        and [sessions[0],sessions[-1]]==[START,END] and sessions==[s for s in calendar_path.read_text().splitlines() if START<=s<=END],'complete actual486session calendar')
    target=read(targets)['low_asset_expansion_decile_conditional'];codes=sorted({c for v in target.values() for c in v['weights']})
    need(len(target)==24 and codes==inv['codes']==sorted(manifest['per_code_sha256']),'complete fixed primary source universe')
    totals=Counter();risk={};new_responses=0;lineage=0
    for code in codes:
        p=raw/'codes'/(code+'.json');need(sha(p)==manifest['per_code_sha256'][code],'raw packet hash');v=read(p)
        need(v['instrument']==code and v['window']==[START,END],'issuer/window identity')
        if code in inv['reuse_routes']:
            route=inv['reuse_routes'][code];origin=base/route['directory']/'codes'/(code+'.json')
            need(sha(origin)==route['packet_sha256'] and origin.read_bytes()==p.read_bytes(),'byte-identical original reuse');dependencies[origin]=route['packet_sha256'];lineage+=1
        else:
            need(code in inv['fresh_codes'],'explicit fresh source route');journal_packet(raw,code,v,expected);new_responses+=4
        symbol=code[:2].lower()+'.'+code[2:]
        need([r['date'] for r in v['bars']]==sessions,'every raw source session exactly once')
        for row in v['bars']:
            need(set(row)==set(BAR) and row['code']==symbol and row['adjustflag']=='3'
                and row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'raw row state/units schema')
            for field in ('open','high','low','close','preclose','volume','amount'):
                if row[field]:need(Decimal(row[field]).is_finite() and Decimal(row[field])>=0,'finite nonnegative raw source amount')
            if row['tradestatus']=='1':
                need(all(row[k] and Decimal(row[k])>0 for k in ('open','high','low','close','preclose','volume')),'positive trading prices/volume')
                need(Decimal(row['high'])>=max(Decimal(row['open']),Decimal(row['close'])) and Decimal(row['low'])<=min(Decimal(row['open']),Decimal(row['close'])),'source OHLC envelope')
        seen=set();noncash=[]
        for row in v['distributions']:
            at=row['dividOperateDate'];need(set(row)==set(DIV) and row['code']==symbol and START<=at<=END and at not in seen,'unique in-window distributions');seen.add(at)
            for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'):
                if row[k]:need(Decimal(row[k]).is_finite() and Decimal(row[k])>=0,'finite nonnegative distribution component')
            if Decimal(row['dividStocksPs'] or '0')>0 or Decimal(row['dividReserveToStockPs'] or '0')>0:noncash.append(row)
        for row in v['adjustments']:
            need(set(row)==set(ADJ) and row['code']==symbol and START<=row['dividOperateDate']<=END,'adjustment issuer/date/schema')
            for k in ADJ[2:]:need(Decimal(row[k]).is_finite() and Decimal(row[k])>0,'positive finite reference adjustment')
        risk[code]={'noncash_distributions_requiring_primary_review':noncash,
            'adjustment_dates_without_vendor_distribution':sorted({r['dividOperateDate'] for r in v['adjustments']}-seen),
            'quarantines':v['quarantine'],
            'nonordinary_or_suspended_source_rows':[{'date':r['date'],'tradestatus':r['tradestatus'],'isST':r['isST']} for r in v['bars'] if r['tradestatus']!='1' or r['isST']!='0']}
        for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[key]+=len(v[field])
    need(dict(totals)==manifest['totals'] and new_responses==manifest['query_reservations_consumed']==4
        and len(list(raw.rglob('reserved-*.json')))==4 and len(list(raw.rglob('response-*.json')))==4,'all totals and bounded query files')
    for p,h in dependencies.items():need(sha(p)==h,'original input after '+str(p))
    need(inventory_files(raw)==before,'all capture bytes unchanged through audit')
    return {'status':'SEPARATE_36_PACKET_LINEAGE_AND_FOUR_SDK_RESPONSE_AUDIT_PASSED_NOT_CORPORATE_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':expected,'capture_manifest_sha256':sha(raw/'manifest.json'),
        'names':36,'byte_identical_original_packets':lineage,'fresh_response_envelopes_redecoded':new_responses,
        'totals':dict(totals),'all_capture_sha256':before,'all_original_inputs_sha256':{str(p):h for p,h in dependencies.items()},
        'source_risks':risk,'no_production_imports':True,'same_researcher_source_QA':True,
        'all_raw_packets_and_original_inputs_unchanged':True,'historical_arrival_verified':False,
        'corporate_action_completeness_verified':False,'physical_account_admitted':False,
        'new_2026_provider_query':False,'portfolio_return_computed':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.output);need(not out.exists(),'fresh external QA output')
    r=audit(Path(a.source_root),Path(a.repo_root),Path(a.raw_dir),Path(a.request),a.expected_request_sha256)
    with out.open('x') as f:json.dump(r,f,indent=2,ensure_ascii=False);f.write('\n')
    print(r['status'],r['totals'])


if __name__=='__main__':main()
