"""Read-only reconstruction of bounded source identities/wire artifacts; no ROI."""
import argparse,base64,hashlib,json
from collections import Counter
from decimal import Decimal as D
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
p=argparse.ArgumentParser()
for n in ('source-root','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[3];root=base/'etf-relative-eastmoney-development-20261021'
read=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
reqpath=repo/'experiments/qlib/etf-relative-momentum-source-request.json';request=read(reqpath);m=read(root/'manifest.json')
assert sha(reqpath)==m['request_sha256']=='54bb2f9ad9482b7cb581535aac689f47074277c621b2467d290a672a52653961'
assert (root/'request.json').read_bytes()==reqpath.read_bytes()
for field in ('method_code_sha256','public_evidence_sha256'):
 for name,h in request[field].items():assert sha(repo/name)==h
assert sha(base/request['calendar_file'])==request['calendar_sha256']
sessions=[d.strip() for d in (base/request['calendar_file']).read_text().splitlines() if '2022-12-01'<=d.strip()<='2025-12-31'];assert len(sessions)==749
assert {str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file() and f.name not in ('capture.lock','manifest.json')}==m['artifact_sha256']
seen=set();transport=Counter();parsed=0;rows=0
for folder in sorted((root/'queries').iterdir()):
 identity=read(folder/'request.json');assert digest(identity)==folder.name
 assert identity['frozen_request_sha256']==sha(reqpath) and identity['source']=='EASTMONEY_ETF_HISTORY_HTTP'
 parts=urlsplit(identity['url']);q=parse_qs(parts.query,keep_blank_values=True)
 assert parts.scheme=='https' and parts.netloc=='push2his.eastmoney.com' and parts.path=='/api/qt/stock/kline/get' and not parts.fragment
 expected={'fields1':['f1,f2,f3,f4,f5,f6'],'fields2':['f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116'],'ut':['7eea3edcaed734bea9cbfc24409ed989'],'klt':['101'],'beg':['20221201'],'end':['20251231']}
 for k,v in expected.items():assert q[k]==v
 assert set(q)==set(expected)|{'secid','fqt'} and len(q['secid'])==len(q['fqt'])==1
 assert q['secid'][0] in ('1.510300','1.510500','0.159915') and q['fqt'][0] in ('0','2')
 key=(q['secid'][0],q['fqt'][0]);assert key not in seen;seen.add(key)
 reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
 assert sorted(f.name for f in folder.iterdir())==['request.json','reserved-1.json','response-1.json']
 assert reserve['identity_sha256']==folder.name and reserve['attempt']==1 and response['identity_sha256']==folder.name and response['reservation_sha256']==sha(folder/'reserved-1.json')
 if response['status']=='SOURCE_ERROR':transport[response['error_type']]+=1;continue
 assert response['status']=='CAPTURED' and digest(response['payload'])==response['payload_sha256']
 envelope=response['payload'];assert envelope['fields']==['http_response'] and len(envelope['rows'])==1
 wire=envelope['rows'][0];raw=base64.b64decode(wire['body_base64'],validate=True)
 if wire['status']!=200 or not wire['body_complete'] or wire['body_truncated'] or wire['read_error_type'] is not None:
  transport['HTTP_OR_BODY_REJECTED']+=1;continue
 assert wire['final_url']==identity['url'] and len(raw)<=10*1024*1024
 body=json.loads(raw);data=body.get('data')
 if not data or not data.get('klines'):transport['EMPTY_HISTORY']+=1;continue
 code=('SH' if key[0][0]=='1' else 'SZ')+key[0][2:];mode='raw' if key[1]=='0' else 'hfq';packetpath=root/(code+'-'+mode+'.json')
 assert body['rc']==0 and data['code']==code[2:] and data['market']==int(key[0][0])
 lines=[line.split(',') for line in data['klines']];assert [r[0] for r in lines]==sessions
 packet=read(packetpath);assert packet['instrument']==code and packet['mode']==mode and [r['date'] for r in packet['bars']]==sessions
 for original,derived in zip(lines,packet['bars']):
  assert derived['original_fields']==original and len(original) in (11,12)
  op,cl,hi,lo=[D(v) for v in original[1:5]]
  assert min(op,cl,hi,lo)>0 and all(v.is_finite() for v in (op,cl,hi,lo)) and lo<=min(op,cl)<=max(op,cl)<=hi
  assert [D(derived[k]) for k in ('open','close','high','low')]==[op,cl,hi,lo]
  if mode=='raw':assert all(v==v.quantize(D('.001')) for v in (op,cl,hi,lo))
 assert code+'-'+mode in m['series'] and sha(packetpath)==m['series'][code+'-'+mode]['sha256']
 parsed+=1;rows+=len(lines)
assert seen=={(code,mode) for code in ('1.510300','1.510500','0.159915') for mode in ('0','2')}
assert len(seen)==m['HTTP_query_reservations']==6 and parsed==m['captured_series']
assert len(m['errors'])==6-parsed and m['source_admitted_for_account_replay'] is False and m['portfolio_returns_computed'] is False
r={'status':'SIX_FROZEN_ETF_HISTORY_IDENTITIES_AND_WIRE_ARTIFACTS_RECONSTRUCTED','audit_code_sha256':sha(__file__),'request_sha256':sha(reqpath),'manifest_sha256':sha(root/'manifest.json'),'HTTP_identities':6,'immutable_query_files':18,'successful_series':parsed,'successful_bar_rows':rows,'expected_sessions_per_series':749,'source_failures_by_type':dict(transport),'all_current_method_and_document_hashes_verified':True,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'new_2026_bar_queries':False,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(r,indent=2)+'\n');print('Six source chains reconstructed; admitted histories',parsed,'/6; failures',dict(transport))
