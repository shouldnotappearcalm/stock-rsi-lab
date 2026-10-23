"""Frozen two-resource raw HTTP/source-tax diagnostic; no account or2026."""
import argparse
import copy
from datetime import date
from decimal import Decimal
from http.client import IncompleteRead
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,HTTPRedirectHandler,build_opener

from scripts.immutable_http_capture import need,write_once,file_sha as sha,digest,now
from scripts import audit_low_operating_lifecycle_sources_pre2026 as prior
from stock_rsi.vendor_dividend_tax_text import parse_net_cash

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
OUTPUT='low-operating-http-tax-sources-pre2026-v1-20261023'
PREFIX='experiments/qlib/'
PROOF=PREFIX+'low-operating-lifecycle-source-failure-verification.json'
PROOF_SHA='ccd6d169151e07322863ebd491bef50d72ac0ecae24f6dbeae6d59e4584d6f4f'
OLD_REQUEST=PREFIX+'low-operating-lifecycle-source-request.json'
RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
CONTROL='SH600118'
MAX_BYTES=1024*1024
DESIGN='docs/research/low-operating-http-tax-source-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-http-tax-sources.md'
REVIEW=PREFIX+'low-operating-http-tax-source-review.json'
METHODS=('src/stock_rsi/vendor_dividend_tax_text.py','scripts/capture_low_operating_http_pre2026.py',
    'scripts/audit_low_operating_http_pre2026.py','tests/test_low_operating_http_tax_sources.py',
    'scripts/immutable_http_capture.py','scripts/audit_low_operating_lifecycle_sources_pre2026.py','scripts/audit_low_operating_raw_pre2026.py')
PARAMS={'fields1':'f1,f2,f3,f4,f5,f6','fields2':','.join('f'+str(n) for n in range(51,62)),
    'ut':'7eea3edcaed734bea9cbfc24409ed989','klt':'101','fqt':'0','beg':'20231229','end':'20251231'}
RESOURCES={c:{'method':'GET','url':'https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode({**PARAMS,'secid':('1.' if c.startswith('SH') else '0.')+c[2:]})} for c in ('SZ002326',CONTROL)}
FIELDS=('date','open','close','high','low','volume_lots','amount','amplitude','change_pct','change_abs','turnover')


def read(p):return json.loads(Path(p).read_text())
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def unchanged(paths):
    bad=[]
    for p,h in paths.items():
        try:
            if sha(p)!=h:bad.append(p)
        except OSError:bad.append(p)
    return bad


def parse_bars(body,code,sessions):
    data=json.loads(body)['data'];need(data['code']==code[2:] and data['market']==int(code.startswith('SH')),'HTTP issuer/market identity')
    rows=[]
    for literal in data['klines']:
        parts=literal.split(',');need(len(parts)==11,'exact historical kline schema');r=dict(zip(FIELDS,parts));day=r['date']
        need(date.fromisoformat(day).isoformat()==day and START<=day<=END,'HTTP source date cutoff')
        values={k:Decimal(r[k]) for k in FIELDS[1:]};need(all(v.is_finite() for v in values.values()),'finite source values')
        need(all(values[k]>0 for k in ('open','close','high','low')) and values['volume_lots']>=0 and values['amount']>=0,'positive OHLC/nonnegative volume/amount')
        need(values['high']>=max(values['open'],values['close']) and values['low']<=min(values['open'],values['close']),'OHLC envelope')
        rows.append(r)
    need([r['date'] for r in rows]==sessions and sessions==sorted(set(sessions)),'complete exact explicit historical calendar')
    return rows


def control_check(bars,original):
    need([r['date'] for r in bars]==[r['date'] for r in original],'same explicit control sessions')
    mismatches=[]
    for r,v in zip(bars,original):
        fields=[k for k in ('open','close','high','low') if Decimal(r[k])!=Decimal(v[k])]
        if Decimal(r['volume_lots'])*100!=Decimal(v['volume']):fields.append('volume_100_shares_per_lot')
        if abs(Decimal(r['amount'])-Decimal(v['amount']))>Decimal('.01'):fields.append('amount_CNY')
        if fields:mismatches.append({'date':r['date'],'fields':fields})
    return {'corroborated':not mismatches,'sessions_checked':len(bars),'mismatches':mismatches,'account_admitted':False}


def tax_risk(packet,sessions):
    view=copy.deepcopy(packet);receipts=[]
    for original,row in zip(packet['distributions'],view['distributions']):
        receipt=parse_net_cash(original['dividCashPsAfterTax'],original['dividCashPsBeforeTax'])
        receipts.append({'original_row_sha256':digest(original),'operation_date':original['dividOperateDate'],**receipt})
        row['dividCashPsAfterTax']=''  # only the validation view; every original literal is checked above.
    risk=prior.source_risk(view,packet['instrument'],sessions,prior.BOUNDARIES)
    return {**risk,'after_tax_receipts':receipts,'separately_checked_after_tax_validation_view':True,
        'original_packet_sha256':digest(packet),'original_packet_modified':False,'tax_treatment_admitted':False}


def context(base,root):
    need(sha(root/PROOF)==PROOF_SHA,'exact retained failed source verification');p=read(root/PROOF);paths={}
    for k,h in p['all_input_sha256'].items():
        key='repo/'+OLD_REQUEST if k=='frozen_request' else k
        path=root/OLD_REQUEST if k=='frozen_request' else prior.resolve(k,root,base)
        need(sha(path)==h,'unchanged original context '+k);paths[key]=path
    for name,h in p['all_capture_sha256'].items():
        path=base/RAW/name;need(sha(path)==h,'unchanged captured context '+name);paths['source/'+RAW+'/'+name]=path
    paths['repo/'+PROOF]=root/PROOF;m=read(base/RAW/'manifest.json');sessions=read(base/RAW/'calendar.json')['sessions']
    need(m['capture_complete'] is False and m['names']==42 and m['pending_codes']==['SZ002326'] and len(sessions)==486
        and [sessions[0],sessions[-1]]==[START,END] and sessions==sorted(set(sessions)),'retained42-source failure and exact486sessions')
    packets={c:read(base/RAW/'codes'/(c+'.json')) for c in m['per_code_sha256']}
    need(CONTROL in packets and [r['date'] for r in packets[CONTROL]['bars']]==sessions,'fixed full-session control')
    return packets,sessions,paths


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'frozen HTTP request');r=read(request)
    need(r['status']=='FROZEN_LOW_OPERATING_TWO_HTTP_AND_LITERAL_TAX_SOURCE_DIAGNOSTIC' and r['candidate']==CANDIDATE
        and r['window']==[START,END] and r['resources']==RESOURCES and r['maximum_http_attempts']==2 and r['max_attempts_per_resource']==1
        and r['timeout_seconds']==20 and r['max_body_bytes']==MAX_BYTES and r['account_or_returns_permitted'] is False
        and r['2026_values_permitted'] is False,'exact two-resource/source-only HTTP scope')
    packets,sessions,paths=context(base,root)
    for name in (*METHODS,DESIGN,PLAN,REVIEW):paths['repo/'+name]=root/name
    need(set(paths)==set(r['input_sha256']) and set(r['method_sha256'])==set(METHODS),'complete source/method binding closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'HTTP context binding '+k)
    for p,h in r['method_sha256'].items():need(h==r['input_sha256']['repo/'+p],'explicit method identity')
    return r,{'sessions':sessions,'packets':packets,'request_sha256':expected,'known_hashes':{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


def execute(req,auth,out,opener):
    need(req['resources']==RESOURCES and not out.exists() and not out.is_symlink(),'fixed fresh two-resource capture')
    need(not unchanged(auth['known_hashes']),'original HTTP inputs before capture');out.mkdir();results={};risks={};tax_errors={};tax_error_details={};primary=None;baseline=None
    result={'candidate':CANDIDATE,'request_sha256':auth['request_sha256'],'status':'SOURCE_DIAGNOSTIC_FAILURE_RETAINED','complete':False,'physical_account_admitted':False,
        'tax_treatment_admitted':False,'corporate_action_completeness_verified':False,'historical_arrival_verified':False,
        'actual_flat_inventory_proven':False,'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}
    try:
        for code,p in auth['packets'].items():
            try:risks[code]=tax_risk(p,auth['sessions'])
            except Exception as exc:
                tax_errors[code]={'category':'SOURCE_TAX_OR_OTHER_FIELD_REJECTED','packet_value_sha256':digest(p)}
                tax_error_details[code]={'type':type(exc).__name__,'message':str(exc)}
        write_once(out/'tax-risk-views.json',{'risks':risks,'errors':tax_errors,'error_details':tax_error_details})
        for code,resource in req['resources'].items():
            folder=out/code;folder.mkdir();write_once(folder/'request.json',resource)
            write_once(folder/'reservation.json',{'resource':code,'identity_sha256':digest(resource),'attempt':1,'reserved_at':now()})
            meta={'status':'HTTP_FAILURE_RETAINED','resource':code,'request_sha256':sha(folder/'request.json'),'reservation_sha256':sha(folder/'reservation.json')}
            try:
                try:response=opener(Request(resource['url'],method='GET',headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'}),timeout=20)
                except HTTPError as exc:response=exc
                with response:
                    meta.update(http_status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'))
                    try:
                        with (folder/'body.bin').open('xb') as f:
                            received=0
                            try:
                                while received<MAX_BYTES+1:
                                    remaining=min(65536,MAX_BYTES+1-received)
                                    try:chunk=response.read(remaining)
                                    except IncompleteRead as exc:
                                        partial=exc.partial[:remaining];f.write(partial);received+=len(partial);raise
                                    if not chunk:break
                                    f.write(chunk[:remaining]);received+=len(chunk[:remaining])
                            finally:f.flush();os.fsync(f.fileno())
                    finally:
                        bodyfile=folder/'body.bin'
                        if bodyfile.exists():meta.update(body_sha256=sha(bodyfile),body_bytes=bodyfile.stat().st_size)
                    body=(folder/'body.bin').read_bytes()
                    need(len(body)<=MAX_BYTES,'HTTP body cap; raw prefix retained')
                    length=response.headers.get('Content-Length')
                    need(length is None or str(length).isdigit() and int(length)==len(body),'HTTP Content-Length completeness')
                    need(response.status==200 and response.url==resource['url'],'exact frozen HTTP response, no redirect')
                rows=parse_bars(body,code,auth['sessions']);write_once(folder/'bars.json',rows)
                meta.update(status='RAW_HTTP_BARS_CAPTURED_NOT_ACCOUNT_ADMITTED',bars_sha256=sha(folder/'bars.json'),rows=len(rows))
            except BaseException as exc:
                meta.update(error_type=type(exc).__name__,error=str(exc))
                if not isinstance(exc,Exception):primary=exc
            write_once(folder/'response.json',meta);results[code]=meta
            if primary is not None:raise primary
        comparison=control_check(read(out/CONTROL/'bars.json'),auth['packets'][CONTROL]['bars']) if (out/CONTROL/'bars.json').exists() else {'corroborated':False,'reason':'CONTROL_HTTP_UNAVAILABLE'}
        result.update(resources=results,tax_risk_codes=len(risks),tax_errors=tax_errors,control_comparison=comparison,
            complete=len(results)==2 and all(x['status']=='RAW_HTTP_BARS_CAPTURED_NOT_ACCOUNT_ADMITTED' for x in results.values()) and comparison['corroborated'] and not tax_errors)
        if result['complete']:result['status']='HTTP_AND_LITERAL_TAX_SOURCE_DIAGNOSTIC_COMPLETE_NOT_ACCOUNT_ADMITTED'
    except BaseException as exc:
        if primary is None:primary=exc
        elif exc is not primary:primary.add_note('secondary capture persistence failure: '+type(exc).__name__+': '+str(exc))
        result.update(error_type=type(primary).__name__,error=str(primary),complete=False)
    try:
        baseline=tree(out);result.update(capture_sha256=baseline,all_capture_outputs_unchanged=True,all_inputs_unchanged=not unchanged(auth['known_hashes']))
        write_once(out/'.terminal-pending.json',result)
        changed_input=unchanged(auth['known_hashes']);after={k:h for k,h in tree(out).items() if k!='.terminal-pending.json'}
        need(not changed_input and after==baseline,'HTTP diagnostic inputs or outputs changed during final persistence')
        os.replace(out/'.terminal-pending.json',out/'terminal.json')
    except BaseException as exc:
        if primary is None:primary=exc
        after={k:h for k,h in tree(out).items() if k not in ('.terminal-pending.json','terminal.json')}
        result.update(status='SOURCE_DIAGNOSTIC_FAILURE_RETAINED',complete=False,all_inputs_unchanged=not unchanged(auth['known_hashes']),
            all_capture_outputs_unchanged=after==baseline,error_type=type(primary).__name__,error=str(primary))
        write_once(out/'.terminal-failure.json',result);os.replace(out/'.terminal-failure.json',out/'terminal.json')
    if primary is not None:raise primary
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','request','expected-request-sha256','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();root=Path(__file__).resolve().parents[1];base=Path(a.source_root).resolve();req=Path(a.request).resolve();out=Path(a.output).resolve()
    need(out==base/OUTPUT and not out.exists(),'fixed fresh source output');r,auth=authenticate(base,root,req,a.expected_request_sha256)
    if a.preflight_only:print('source context/two HTTP identities preflight PASS; no network',flush=True);return 0
    result=execute(r,auth,out,build_opener(NoRedirect()).open);print(result['status'],flush=True);return 0 if result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
