"""Separate HTTP bytes/literal-risk reconstruction; no new producer imports."""
import argparse
import copy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urlsplit,parse_qs
from scripts import audit_low_operating_lifecycle_sources_pre2026 as legacy
from scripts.immutable_http_capture import need,digest,file_sha as sha

RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
PROOF='experiments/qlib/low-operating-lifecycle-source-failure-verification.json'
CONTROL='SH600118'
FIELDS=('date','open','close','high','low','volume_lots','amount','amplitude','change_pct','change_abs','turnover')
def read(p):return json.loads(Path(p).read_text())
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}


def decode_bars(body,code,sessions):
    obj=json.loads(body)['data'];need(obj['code']==code[2:] and obj['market']==int(code.startswith('SH')),'separate HTTP identity')
    result=[]
    for text in obj['klines']:
        values=text.split(',');need(len(values)==len(FIELDS),'separate exact11columns');r=dict(zip(FIELDS,values));at=r['date']
        need(date.fromisoformat(at).isoformat()==at and '2023-12-29'<=at<='2025-12-31','separate historical cutoff')
        n={k:Decimal(v) for k,v in r.items() if k!='date'};need(all(v.is_finite() for v in n.values()),'separate finite numeric fields')
        need(min(n[k] for k in ('open','close','high','low'))>0 and n['volume_lots']>=0 and n['amount']>=0,'separate positive prices/nonnegative activity')
        need(n['low']<=min(n['open'],n['close'])<=max(n['open'],n['close'])<=n['high'],'separate OHLC range');result.append(r)
    need([v['date'] for v in result]==sessions==sorted(set(sessions)),'separate exact calendar');return result


def reconstruct_tax_risk(packet,sessions):
    view=copy.deepcopy(packet);receipts=[]
    for raw,v in zip(packet['distributions'],view['distributions']):
        text=raw['dividCashPsAfterTax'];gross=raw['dividCashPsBeforeTax'];options=[]
        if text:
            g=Decimal(gross);need(g.is_finite() and g>=0,'separate finite gross amount')
            options=text.split('或');need(all(re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',x) for x in options),'separate supported literal options')
            need(all(Decimal(x)<=g for x in options),'separate net/gross bound')
        status='UNKNOWN_EMPTY_SOURCE_TEXT' if not text else 'LITERAL_ALTERNATIVES_UNSELECTED' if len(options)>1 else 'LITERAL_SINGLE_AMOUNT_NOT_ACCOUNT_TAX'
        receipts.append({'original_row_sha256':digest(raw),'operation_date':raw['dividOperateDate'],'source_text':text,
            'gross_source_text':gross,'options':options,'selected_net_cash':None,'tax_treatment_admitted':False,'status':status})
        v['dividCashPsAfterTax']=''
    risk=legacy.source_risk(view,packet['instrument'],sessions,legacy.BOUNDARIES)
    return {**risk,'after_tax_receipts':receipts,'separately_checked_after_tax_validation_view':True,
        'original_packet_sha256':digest(packet),'original_packet_modified':False,'tax_treatment_admitted':False}


def compare_control(rows,original):
    need([v['date'] for v in rows]==[v['date'] for v in original],'separate control calendar');bad=[]
    for a,b in zip(rows,original):
        fields=[k for k in ('open','close','high','low') if Decimal(a[k])!=Decimal(b[k])]
        if Decimal(a['volume_lots'])*100!=Decimal(b['volume']):fields.append('volume_100_shares_per_lot')
        if abs(Decimal(a['amount'])-Decimal(b['amount']))>Decimal('0.01'):fields.append('amount_CNY')
        if fields:bad.append({'date':a['date'],'fields':fields})
    return {'corroborated':not bad,'sessions_checked':len(rows),'mismatches':bad,'account_admitted':False}


def audit(base,root,raw,request,expected):
    need(sha(request)==expected,'frozen exact HTTP request');r=read(request)
    need(r['status']=='FROZEN_LOW_OPERATING_TWO_HTTP_AND_LITERAL_TAX_SOURCE_DIAGNOSTIC' and r['candidate']=='low_operating_profitability_followup_v1'
        and r['window']==['2023-12-29','2025-12-31'] and r['maximum_http_attempts']==2 and r['max_attempts_per_resource']==1
        and r['timeout_seconds']==20 and r['max_body_bytes']==1048576 and r['account_or_returns_permitted'] is False
        and r['2026_values_permitted'] is False and set(r['resources'])=={'SZ002326',CONTROL},'separate bounded HTTP scope')
    for code,res in r['resources'].items():
        url=urlsplit(res['url']);q=parse_qs(url.query)
        need(res['method']=='GET' and url.scheme=='https' and url.netloc=='push2his.eastmoney.com' and url.path=='/api/qt/stock/kline/get'
            and q=={'fields1':['f1,f2,f3,f4,f5,f6'],'fields2':[','.join('f'+str(n) for n in range(51,62))],
                'ut':['7eea3edcaed734bea9cbfc24409ed989'],'klt':['101'],'fqt':['0'],'beg':['20231229'],'end':['20251231'],
                'secid':[('1.' if code.startswith('SH') else '0.')+code[2:]]},'independent exact HTTP identity')
    paths={k:legacy.resolve(k,root,base) for k in r['input_sha256']};paths['frozen_request']=request;want={**r['input_sha256'],'frozen_request':expected}
    for k,p in paths.items():need(sha(p)==want[k],'original input before '+k)
    need(sha(root/PROOF)=='ccd6d169151e07322863ebd491bef50d72ac0ecae24f6dbeae6d59e4584d6f4f','retained original failed context')
    before=tree(raw);terminal=read(raw/'terminal.json');need(terminal['request_sha256']==expected and not any(n.startswith('.') for n in before),'exact request/no pending persistence staging')
    need(terminal['all_inputs_unchanged'] is True and terminal['all_capture_outputs_unchanged'] is True
        and terminal['capture_sha256']=={k:h for k,h in before.items() if k!='terminal.json'},'full output tree retained through persistence')
    sessions=read(base/RAW/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)),'486explicit original sessions')
    manifest=read(base/RAW/'manifest.json');views=read(raw/'tax-risk-views.json');risks={};tax_errors={}
    for code,h in manifest['per_code_sha256'].items():
        p=base/RAW/'codes'/(code+'.json');need(sha(p)==h,'original raw tax packet')
        try:risks[code]=reconstruct_tax_risk(read(p),sessions)
        except Exception as exc:tax_errors[code]={'type':type(exc).__name__,'message':str(exc)}
    need(views=={'risks':risks,'errors':tax_errors},'independent literal receipts/all source risks')
    projected={};resource_records={}
    for code,res in r['resources'].items():
        folder=raw/code;reservation=read(folder/'reservation.json');meta=read(folder/'response.json')
        need(read(folder/'request.json')==res and reservation['resource']==code and reservation['attempt']==1
            and reservation['identity_sha256']==digest(res) and meta['resource']==code
            and meta['request_sha256']==sha(folder/'request.json') and meta['reservation_sha256']==sha(folder/'reservation.json'),'one exact reserved resource')
        body=folder/'body.bin'
        if body.exists():need(sha(body)==meta['body_sha256'] and body.stat().st_size==meta['body_bytes'],'all original HTTP bytes')
        if meta['status']=='RAW_HTTP_BARS_CAPTURED_NOT_ACCOUNT_ADMITTED':
            need(meta['http_status']==200 and meta['final_url']==res['url'] and body.stat().st_size<=1048576,'successful registered transport')
            rows=decode_bars(body.read_bytes(),code,sessions);need(rows==read(folder/'bars.json') and sha(folder/'bars.json')==meta['bars_sha256'],'independent bar projection')
            projected[code]=rows
        else:need(meta['status']=='HTTP_FAILURE_RETAINED' and not (folder/'bars.json').exists(),'failed HTTP never becomes accepted bars')
        resource_records[code]=meta
    control=compare_control(projected[CONTROL],read(base/RAW/'codes'/f'{CONTROL}.json')['bars']) if CONTROL in projected else {'corroborated':False,'reason':'CONTROL_HTTP_UNAVAILABLE'}
    complete=len(projected)==2 and control['corroborated'] and not tax_errors
    need(terminal['resources']==resource_records and terminal['control_comparison']==control and terminal['complete']==complete
        and terminal['tax_risk_codes']==len(risks) and terminal['tax_errors']==tax_errors,'independent separate sub-outcomes')
    need(len(list(raw.rglob('reservation.json')))==len(list(raw.rglob('response.json')))==2,'only two HTTP attempts')
    for k in ('physical_account_admitted','tax_treatment_admitted','corporate_action_completeness_verified','historical_arrival_verified','actual_flat_inventory_proven','portfolio_return_computed','2026_values_read','objective_achieved'):
        need(terminal[k] is False,'source support cannot admit full account/goal')
    for k,p in paths.items():need(sha(p)==want[k],'original input after '+k)
    need(tree(raw)==before,'all raw outputs unchanged')
    return {'status':'PASS_SEPARATE_SOURCE_DIAGNOSTIC_RECONSTRUCTION_NOT_ACCOUNT_ADMISSION','request_sha256':expected,
        'all_input_sha256':want,'all_capture_sha256':before,'all_inputs_outputs_unchanged':True,'no_new_producer_or_tax_parser_imports':True,
        'shared_legacy_source_risk_helper':True,'tax_risk_codes':len(risks),'tax_errors':tax_errors,'literal_tax_receipts':sum(len(x['after_tax_receipts']) for x in risks.values()),
        'HTTP_resources':resource_records,'projected_bar_resources':list(projected),'control_comparison':control,'source_diagnostic_complete':complete,
        'physical_account_admitted':False,'tax_treatment_admitted':False,'historical_arrival_verified':False,'corporate_action_completeness_verified':False,
        'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();out=Path(a.output);raw=Path(a.raw_dir).resolve();need(not out.exists() and not out.resolve().is_relative_to(raw),'fresh external proof')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],raw,Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with out.open('x') as f:json.dump({'status':'FAILED_SEPARATE_HTTP_TAX_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,indent=2)
        raise
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],'tax',result['tax_risk_codes'],'HTTP',result['projected_bar_resources'],'complete',result['source_diagnostic_complete'],flush=True)


if __name__=='__main__':main()
