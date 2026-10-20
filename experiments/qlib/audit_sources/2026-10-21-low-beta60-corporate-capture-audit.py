"""Stdlib-only audit of the immutable failed capture and bounded continuation."""
import argparse,base64,hashlib,json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path

p=argparse.ArgumentParser()
for n in ('initial-dir','continuation-dir','source-root','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();first=Path(a.initial_dir);second=Path(a.continuation_dir);base=Path(a.source_root)
repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
paths=[repo/'experiments/qlib/low-beta60-corporate-source-request.json',repo/'experiments/qlib/low-beta60-corporate-continuation-request.json']
expected=['d6f63be857682d50c273a30d3d67b94472d52e78d522b40082a9871db6bf7f17','6167bcdb48cfcb4c330d4112b4f8949422c651dcd06f97d30c0a9442e889a62d']
requests=[read(f) for f in paths];manifests=[read(d/'manifest.json') for d in (first,second)]
r0,r1=requests;m0,m1=manifests
assert sha(first/'manifest.json')==r1['previous_capture_manifest_sha256']==m1['previous_capture_manifest_sha256']
assert r1['previous_request_sha256']==expected[0]
assert len(m0['documents'])==8 and len(m0['errors'])==2 and not m0['pending_cases']
assert len(m1['documents'])==10 and not m1['errors'] and not m1['pending_cases']
assert sha(base/'low-beta60-raw-dev-20261021/manifest.json')==r0['raw_manifest_sha256']==m0['raw_manifest_sha256']
assert sha(base/'low-beta60-raw-source-audit-20261021.json')==r0['raw_audit_sha256']==m0['raw_audit_sha256']
assert sha(base/'cninfo-csi500-reports-20261017/plan.json')==r0['org_map_plan_sha256']
cases={v['case_id']:v for v in r0['cases']};assert set(cases)==set(m1['documents']) and len(cases)==10
assert set(m0['errors'])==set(r1['case_ids'])==set(cases)-set(m0['documents'])
all_http=[];all_api=[];all_pdfs={};artifact_counts=[]
for phase,(directory,requestpath,r,m,h) in enumerate(zip((first,second),paths,requests,manifests,expected)):
 assert sha(requestpath)==h==m['request_sha256']
 assert (directory/'request.json').read_bytes()==requestpath.read_bytes()
 assert all(sha(repo/f)==v for f,v in r['method_code_sha256'].items())
 assert sha(repo/r['protocol_file'])==r['protocol_sha256']
 assert m['documents']==read(directory/'progress.json') and (m['errors']==read(directory/'errors.json'))
 files={str(f.relative_to(directory)):sha(f) for f in directory.rglob('*') if f.is_file() and f.name not in ('manifest.json','capture.lock')}
 assert files==m['artifact_sha256'];artifact_counts.append(len(files))
 for folder in sorted((directory/'queries').iterdir()):
  assert sorted(f.name for f in folder.iterdir())==['request.json','reserved-1.json','response-1.json']
  identity=read(folder/'request.json');reserve=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  assert folder.name==digest(identity)==reserve['identity_sha256']==response['identity_sha256']
  assert reserve['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
  assert identity['source']=='CNINFO_HTTP' and identity['notice_request_sha256']==h
  assert response['status']=='CAPTURED' and digest(response['payload'])==response['payload_sha256']
  payload=response['payload'];assert payload['fields']==['http_response'] and len(payload['rows'])==1
  wire=payload['rows'][0];body=base64.b64decode(wire['body_base64'],validate=True)
  assert wire['status']==200 and wire['final_url']==identity['url'] and wire['body_complete'] is True
  assert wire['body_truncated'] is False and wire['read_error_type'] is None and wire['read_error'] is None
  assert len(body)<=10485760
  all_http.append((phase,identity))
  if identity['payload'] is not None:
   assert phase==0 and identity['url']=='https://www.cninfo.com.cn/new/hisAnnouncement/query'
   q=identity['payload'];matches=[c for k,c in cases.items() if k not in r0['reuse_documents'] and q['stock']==c['instrument'][2:]+','+c['organization_id'] and q['seDate']==c['publication_day']+'~'+c['publication_day']]
   assert len(matches)==1 and q['pageNum'] in ('1','2') and q['pageSize']=='30' and q['category']==''
   all_api.append((identity,json.loads(body)))
  else:
   assert identity['url'] not in all_pdfs
   all_pdfs[identity['url']]=(directory,folder,body,phase)
assert sum(v[0]==0 for v in all_http)==m0['HTTP_query_reservations']==8
assert sum(v[0]==1 for v in all_http)==m1['new_PDF_query_reservations']==2
assert len(all_http)==m1['combined_HTTP_query_reservations']==10<=m1['maximum_combined_HTTP_query_reservations']==15
assert m1['new_API_requests']==0 and len(all_api)==5 and len(all_pdfs)==5
proofs=[]
for key,doc in m1['documents'].items():
 case=cases[key];code=case['instrument'];day=case['publication_day']
 assert doc['code']==code[2:] and doc['instrument']==code and doc['day']==day and '2024-01-01'<=day<='2025-12-31'
 assert re.fullmatch('[0-9]+',doc['announcement_id']) and doc['pdf_path'].lower()==('finalpage/'+day+'/'+doc['announcement_id']+'.PDF').lower()
 assert re.search('(?:权益分派|利润分配)实施(?:的)?公告',doc['title'])
 assert doc['url']=='https://static.cninfo.com.cn/'+doc['pdf_path']
 path=second/doc['file'];assert Path(doc['file']).name==doc['file'] and sha(path)==doc['sha256'] and path.read_bytes().startswith(b'%PDF')
 if key in m0['documents']:
  prior=m0['documents'][key];assert doc=={**prior,'capture_route':'BYTE_IDENTICAL_PRIOR_CAPTURE_REUSE','previous_capture_manifest_sha256':sha(first/'manifest.json')}
  assert path.read_bytes()==(first/prior['file']).read_bytes()
 if key in r0['reuse_documents']:
  reuse=r0['reuse_documents'][key];old=base/reuse['directory']
  assert sha(old/'reviewed-manifest.json')==reuse['reviewed_manifest_sha256']
  assert reuse['metadata'] in read(old/'reviewed-manifest.json')['documents']
  assert m0['documents'][key]=={**reuse['metadata'],'capture_route':'BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE','original_reviewed_manifest_sha256':reuse['reviewed_manifest_sha256']}
  assert path.read_bytes()==(old/reuse['file']).read_bytes() and sha(path)==reuse['sha256']
 else:
  matches=[]
  for identity,data in all_api:
   q=identity['payload']
   if q['stock']!=code[2:]+','+case['organization_id'] or q['seDate']!=day+'~'+day:continue
   assert int(data['totalAnnouncement'])<=60
   for row in data.get('announcements') or []:
    pub=datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
    assert pub==day
    if row['secCode']==code[2:] and re.search('(?:权益分派|利润分配)实施(?:的)?公告',row['announcementTitle']):matches.append(row)
  assert len(matches)==1;row=matches[0]
  assert row['announcementId']==doc['announcement_id'] and row['adjunctUrl']==doc['pdf_path'] and row['announcementTitle']==doc['title']
  directory,folder,body,phase=all_pdfs[doc['url']];assert path.read_bytes()==body
  assert phase==(1 if key in r1['case_ids'] else 0)
  receipt=doc['HTTP_pdf_receipt']
  for prefix,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
   assert receipt[prefix+'_file']==str((folder/name).relative_to(directory)) and receipt[prefix+'_sha256']==sha(folder/name)
  if key in r1['case_ids']:
   assert doc['capture_route']=='SAVED_LISTING_NEW_PDF_CONTINUATION' and doc['listing_capture_manifest_sha256']==sha(first/'manifest.json')
   assert {k:doc[k] for k in r1['selected_original_rows'][key]}==r1['selected_original_rows'][key]
 proofs.append({'case_id':key,'file':doc['file'],'sha256':doc['sha256'],'publication_day':day,'byte_and_identity_chain_verified':True})
errors={}
for key,h in m0['errors'].items():
 file=first/('error-'+key.replace('|','-')+'.json');assert sha(file)==h
 err=read(file);assert err['case_id']==key and err['error_type']=='ValueError' and err['error']=='exact implementation notice is not unique'
 assert err['HTTP_responses_retained'] is True;errors[key]=err
for m in manifests:
 for flag in ('documents_financially_reviewed','raw_source_admitted_for_account_replay','investment_rule_changed','portfolio_returns_computed','new_2026_queries','objective_achieved'):assert m[flag] is False
result={'status':'ALL10_PRIMARY_BYTE_CHAINS_VERIFIED_WITH_ORIGINAL_TWO_PARSER_FAILURES_PRESERVED',
 'audit_code_sha256':sha(__file__),'initial_manifest_sha256':sha(first/'manifest.json'),
 'continuation_manifest_sha256':sha(second/'manifest.json'),'request_sha256':expected,'documents':proofs,
 'original_selection_errors':errors,'initial_HTTP_reservations':8,'continuation_HTTP_reservations':2,
 'combined_HTTP_reservations':10,'original_combined_HTTP_limit':15,'new_API_requests_in_continuation':0,
 'total_new_list_API_requests':5,'total_new_PDF_requests':5,'reused_preexisting_documents':5,
 'immutable_query_artifacts_verified':30,'capture_artifact_counts':artifact_counts,
 'financial_review_completed':False,'historical_arrival_certified':False,'raw_source_admitted_for_account_replay':False,
 'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('10 primary documents;8+2 HTTP chains independently authenticated; original parser failures preserved')
