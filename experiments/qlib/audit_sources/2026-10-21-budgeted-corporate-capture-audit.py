"""Independent stdlib-only verification of original CNINFO response chains."""
import argparse,base64,hashlib,json,re
from pathlib import Path
from datetime import datetime,timezone,timedelta

p=argparse.ArgumentParser()
for n in ('capture-dir','source-root','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();root=Path(a.capture_dir);sources=Path(a.source_root);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
request=repo/'experiments/qlib/budgeted-residual-corporate-notice-request.json'
assert sha(request)=='99a5f18edf3e2ef27f519c8f7e0b649ad6e9959d381c2a79d1ded8f64d07b2ba'
r=read(request);m=read(root/'manifest.json');assert (root/'request.json').read_bytes()==request.read_bytes()
assert m['request_sha256']==sha(request) and all(sha(repo/f)==h for f,h in r['method_code_sha256'].items())
assert m['raw_manifest_sha256']==r['raw_manifest_sha256'] and m['raw_audit_sha256']==r['raw_audit_sha256']
assert sha(sources/'budgeted-residual-raw-dev-20261021/manifest.json')==r['raw_manifest_sha256']
assert sha(sources/'budgeted-residual-raw-source-audit-20261021.json')==r['raw_audit_sha256']
assert m['documents']==read(root/'progress.json') and not m['errors'] and not read(root/'errors.json') and not m['pending_cases']
files={str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file() and f.name not in ('manifest.json','capture.lock')}
assert files==m['artifact_sha256']
responses={};api=[]
for folder in sorted((root/'queries').iterdir()):
 assert sorted(f.name for f in folder.iterdir())==['request.json','reserved-1.json','response-1.json']
 identity=read(folder/'request.json');reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
 assert folder.name==digest(identity)==reserve['identity_sha256']==response['identity_sha256']
 assert reserve['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
 assert identity['source']=='CNINFO_HTTP' and identity['notice_request_sha256']==sha(request)
 assert response['status']=='CAPTURED' and response['payload_sha256']==digest(response['payload'])
 payload=response['payload'];assert payload['fields']==['http_response'] and len(payload['rows'])==1
 wire=payload['rows'][0];body=base64.b64decode(wire['body_base64'],validate=True)
 assert wire['status']==200 and wire['final_url']==identity['url'] and wire['body_complete'] is True
 assert wire['body_truncated'] is False and wire['read_error_type'] is None and wire['read_error'] is None and len(body)<=10485760
 responses[identity['url'] if identity['payload'] is None else digest(identity)]=(folder,body,identity)
 if identity['payload'] is not None:api.append((identity,json.loads(body)))
assert len(responses)==m['HTTP_query_reservations']==24<=36
cases={c['case_id']:c for c in r['cases']};assert set(cases)==set(m['documents']) and len(cases)==13
proofs=[]
for key,doc in m['documents'].items():
 case=cases[key];code=case['instrument'];day=case['publication_day']
 assert doc['instrument']==code and doc['code']==code[2:] and doc['day']==day and '2024-01-01'<=day<='2025-12-31'
 expected='finalpage/'+day+'/'+doc['announcement_id']+'.PDF'
 assert re.fullmatch('[0-9]+',doc['announcement_id']) and doc['pdf_path'].lower()==expected.lower()
 assert doc['url']=='https://static.cninfo.com.cn/'+doc['pdf_path']
 assert re.search('权益分派实施(?:的)?公告',doc['title'])
 path=root/doc['file'];assert Path(doc['file']).name==doc['file'] and sha(path)==doc['sha256'] and path.read_bytes().startswith(b'%PDF')
 if key in r['reuse_documents']:
  reuse=r['reuse_documents'][key];old=sources/reuse['directory'];assert path.read_bytes()==(old/reuse['file']).read_bytes()
  assert sha(old/'reviewed-manifest.json')==reuse['reviewed_manifest_sha256'] and reuse['metadata'] in read(old/'reviewed-manifest.json')['documents']
  assert doc['capture_route']=='BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE'
 else:
  matches=[]
  for identity,data in api:
   payload=identity['payload']
   if payload['stock']!=code[2:]+','+case['organization_id'] or payload['seDate']!=day+'~'+day:continue
   assert identity['url']=='https://www.cninfo.com.cn/new/hisAnnouncement/query'
   assert payload['pageNum'] in ('1','2') and payload['pageSize']=='30' and payload['category']==''
   assert int(data['totalAnnouncement'])<=60
   for row in data.get('announcements') or []:
    pub=datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
    assert pub==day
    if row['secCode']==code[2:] and re.search('权益分派实施(?:的)?公告',row['announcementTitle']):matches.append(row)
  assert len(matches)==1;row=matches[0]
  assert row['announcementId']==doc['announcement_id'] and row['adjunctUrl']==doc['pdf_path'] and row['announcementTitle']==doc['title']
  folder,body,_=responses[doc['url']];assert path.read_bytes()==body
  for prefix,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
   assert doc['HTTP_pdf_receipt'][prefix+'_file']==str((folder/name).relative_to(root)) and doc['HTTP_pdf_receipt'][prefix+'_sha256']==sha(folder/name)
  assert doc['capture_route']=='JOURNALED_ORIGINAL_PRIMARY_HTTP'
 proofs.append({'case_id':key,'file':doc['file'],'sha256':doc['sha256'],'publication_day':day,'byte_and_identity_chain_verified':True})
assert len(api)==12 and len(responses)-len(api)==12
result={'status':'ALL13_PRIMARY_BYTE_IDENTITY_CHAINS_VERIFIED_FINANCIAL_REVIEW_SEPARATE','audit_code_sha256':sha(__file__),
 'request_sha256':sha(request),'capture_manifest_sha256':sha(root/'manifest.json'),'documents':proofs,
 'new_API_requests':12,'new_PDF_requests':12,'reused_documents':1,'captured_HTTP_responses':24,
 'immutable_query_artifacts':72,'capture_artifact_files':len(files),'source_errors':0,
 'financial_review_completed':False,'historical_arrival_certified':False,'portfolio_returns_computed':False,
 'new_2026_queries':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('13 original documents /24 HTTP chains independently reconstructed; financial review separate')
