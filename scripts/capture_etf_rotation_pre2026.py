"""Six bounded raw/hfq ETF histories, with immutable wire receipts; no ROI."""
import argparse,base64,fcntl,json,time
from decimal import Decimal as D
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,build_opener
from scripts.capture_budgeted_corporate_notices_pre2026 import NoRedirect,MAX_BODY,journaled_bytes
from scripts.fundamental_query_journal import QueryJournal,file_sha,write_packet_once

CODES=('SH510300','SH510500','SZ159915');MODES=('raw','hfq')
START='2022-12-01';END='2025-12-31'
METHOD_FILES=('scripts/capture_etf_rotation_pre2026.py','scripts/fundamental_query_journal.py',
              'scripts/capture_budgeted_corporate_notices_pre2026.py')


def history_url(code,mode):
    if code not in CODES or mode not in MODES:raise ValueError('unregistered ETF or adjustment mode')
    params={'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116',
        'ut':'7eea3edcaed734bea9cbfc24409ed989','klt':'101','fqt':'0' if mode=='raw' else '2',
        'beg':START.replace('-',''),'end':END.replace('-',''),'secid':('1.' if code.startswith('SH') else '0.')+code[2:]}
    return 'https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params)


def read_wire(url,payload):
    if payload is not None or url not in {history_url(c,m) for c in CODES for m in MODES}:
        raise ValueError('unregistered historical query')
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
    try:response=build_opener(NoRedirect()).open(req,timeout=15)
    except HTTPError as exc:response=exc
    chunks=[];remaining=MAX_BODY+1;error_type=error=None
    try:
        with response:
            while remaining:
                chunk=response.read(min(65536,remaining))
                if not chunk:break
                if not isinstance(chunk,bytes):raise TypeError('HTTP byte stream required')
                chunks.append(chunk[:remaining]);remaining-=len(chunk[:remaining])
    except Exception as exc:
        partial=getattr(exc,'partial',b'')
        if isinstance(partial,bytes):chunks.append(partial[:remaining])
        error_type,error=type(exc).__name__,str(exc)
    raw=b''.join(chunks);length=response.headers.get('Content-Length')
    if error_type is None and length is not None:
        try:expected=int(length)
        except ValueError:expected=-1
        if expected<0 or len(raw)!=expected:error_type,error='ContentLengthMismatch','incomplete HTTP bytes'
    return ['http_response'],[{'status':response.code,'final_url':response.geturl(),'content_type':response.headers.get('Content-Type',''),
        'body_base64':base64.b64encode(raw).decode(),'body_truncated':len(raw)>MAX_BODY,
        'body_complete':error_type is None and len(raw)<=MAX_BODY,'read_error_type':error_type,'read_error':error}]


def parse_history(body,code,mode,sessions):
    history_url(code,mode)
    data=body.get('data')
    if (body.get('rc')!=0 or not isinstance(data,dict) or data.get('code')!=code[2:]
            or data.get('market')!=(1 if code.startswith('SH') else 0) or not data.get('klines')):
        raise ValueError('historical ETF identity or series missing')
    output=[]
    for line in data['klines']:
        fields=line.split(',')
        if len(fields) not in (11,12):raise ValueError('historical field layout changed')
        day=fields[0];op,close,high,low=(D(x) for x in fields[1:5]);volume=D(fields[5]);amount=D(fields[6])
        if (not START<=day<=END or any(not x.is_finite() or x<=0 for x in (op,close,high,low))
                or low>min(op,close) or high<max(op,close) or high<low
                or not volume.is_finite() or volume<=0 or volume!=volume.to_integral_value()
                or not amount.is_finite() or amount<=0
                or mode=='raw' and any(x!=x.quantize(D('.001')) for x in (op,close,high,low))):
            raise ValueError('invalid date,OHLC,tick,volume or amount')
        output.append({'date':day,'open':str(op),'close':str(close),'high':str(high),'low':str(low),
                       'volume_provider_raw':fields[5],'amount_provider_raw':fields[6],'original_fields':fields})
    if [r['date'] for r in output]!=sessions:raise ValueError('complete explicit calendar coverage required; duplicates/future/gaps forbidden')
    return {'instrument':code,'mode':mode,'window':[START,END],'bars':output,
            'evidence_level':'CURRENT_VINTAGE_ETF_PRICE_ENGINEERING_ONLY','volume_unit_verified':False,
            'corporate_actions_or_adjustment_method_certified':False,'historical_arrival_certified':False}


def capture(out,sessions,request_sha,*,fetch=read_wire,minimum_interval=.3):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        m=json.loads((out/'manifest.json').read_text())
        if m['request_sha256']!=request_sha:raise ValueError('terminal scope changed')
        for n,h in m['artifact_sha256'].items():
            if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(out/n)!=h:raise ValueError('terminal source bytes changed')
        return m
    journal=QueryJournal(out,max_queries=6,max_attempts=1);series={};errors={};next_query=0.
    for code in CODES:
        for mode in MODES:
            key=code+'-'+mode;url=history_url(code,mode)
            def wire():
                nonlocal next_query
                pause=next_query-time.monotonic()
                if pause>0:time.sleep(pause)
                try:return fetch(url,None)
                finally:next_query=time.monotonic()+minimum_interval
            try:
                raw,receipt=journaled_bytes(journal,{'source':'EASTMONEY_ETF_HISTORY_HTTP','url':url,'frozen_request_sha256':request_sha},wire)
                packet=parse_history(json.loads(raw),code,mode,sessions);write_packet_once(out/(key+'.json'),packet)
            except Exception as exc:errors[key]={'error_type':type(exc).__name__,'error':str(exc)}
            else:series[key]={'file':key+'.json','sha256':file_sha(out/(key+'.json')),'rows':len(packet['bars']),'HTTP_receipt':receipt}
    write_packet_once(out/'errors.json',errors)
    m={'status':'BOUNDED_ETF_HISTORY_CAPTURE_FINISHED_ADMISSION_SEPARATE','request_sha256':request_sha,'window':[START,END],
       'series':series,'errors':errors,'captured_series':len(series),'expected_series':6,'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),
       'maximum_HTTP_queries':6,'artifact_sha256':{str(f.relative_to(out)):file_sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name not in ('manifest.json','capture.lock')},
       'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'2026_bar_queries_requested':False,
       'candidate_promoted':False,'objective_achieved':False}
    write_packet_once(out/'manifest.json',m);return m


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];r=json.loads(Path(a.request).read_text());base=Path(a.source_root);out=Path(a.output_dir)
    if (file_sha(a.request)!=a.expected_request_sha256 or r['status']!='FROZEN_SIX_ETF_PRE2026_HISTORY_QUERIES'
        or r['instruments']!=list(CODES) or r['modes']!=list(MODES) or r['window']!=[START,END]
        or r['maximum_http_queries']!=6 or r['max_attempts_per_identity']!=1 or r['minimum_interval_seconds']!=.3
        or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):
        raise ValueError('frozen ETF capture request/method changed')
    for n,h in r['public_evidence_sha256'].items():
        if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(repo/n)!=h:raise ValueError('frozen public evidence changed')
    name=r['calendar_file']
    if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(base/name)!=r['calendar_sha256']:raise ValueError('frozen calendar changed')
    days=[d.strip() for d in (base/name).read_text().splitlines() if START<=d.strip()<=END]
    if days!=sorted(set(days)) or not days or [days[0],days[-1]]!=[START,END]:raise ValueError('explicit development sessions required')
    out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        original=out/'request.json'
        if original.exists() and original.read_bytes()!=Path(a.request).read_bytes():raise ValueError('checkpoint request differs')
        if not original.exists():original.write_bytes(Path(a.request).read_bytes())
        m=capture(out,days,a.expected_request_sha256,minimum_interval=r['minimum_interval_seconds'])
        print('ETF historical series',m['captured_series'],'/6; immutable requests',m['HTTP_query_reservations'],'; errors',list(m['errors']),flush=True)
        return 0 if m['captured_series']==6 else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
