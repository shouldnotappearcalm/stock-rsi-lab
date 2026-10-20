"""Stdlib reconstruction of both bounded primary capture byte chains; no tax approval."""
import argparse,base64,hashlib,json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('source-root','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[3]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
config=[('budgeted-residual-wolong-tax-sources-20261021','budgeted-residual-wolong-tax-source-request.json',
 '2e52e94784b8659ba57f6df92828430e6bd8a0c1fb5fe8e57a03ad29384601d6',['2025-04-26','2025-04-26'],'',4,'wolong_source_request_sha256',('proposal','annual')),
 ('budgeted-residual-wolong-halfyear-20261021','budgeted-residual-wolong-halfyear-source-request.json',
 '16201ab67e045ea8abb677e75cae57e3fb7ada96f1b90de23b01cd7c5513ae29',['2025-07-01','2025-08-31'],'category_bndbg_szsh',3,'wolong_halfyear_request_sha256',('halfyear',))]
patterns={'proposal':r'2024年度利润分配.*(?:资本公积.*转增股本|转增股本).*公告$',
 'annual':r'2024年年度报告(?:（全文）|\(全文\)|全文)?$','halfyear':r'2025年半年度报告(?:（全文）|\(全文\)|全文)?$'}
outputs=[];documents=[]
for directory,requestname,requestsha,window,category,budget,identityfield,roles in config:
 root=base/directory;request=repo/'experiments/qlib'/requestname
 assert sha(request)==requestsha and (root/'request.json').read_bytes()==request.read_bytes()
 r=read(request);m=read(root/'manifest.json');assert m['request_sha256']==requestsha
 assert all(sha(repo/f)==h for f,h in r['method_code_sha256'].items())
 assert all(not Path(f).is_absolute() and '..' not in Path(f).parts and sha(base/f)==h for f,h in r['local_source_sha256'].items())
 assert all(not Path(f).is_absolute() and '..' not in Path(f).parts and sha(repo/f)==h for f,h in r['public_evidence_sha256'].items())
 assert m['documents']==read(root/'documents.json') and not m['errors'] and not read(root/'errors.json') and set(m['documents'])==set(roles)
 assert {str(f.relative_to(root)):sha(f) for f in root.rglob('*') if f.is_file() and f.name not in ('manifest.json','capture.lock')}==m['artifact_sha256']
 api={};pdf={}
 for folder in sorted((root/'queries').iterdir()):
  assert sorted(f.name for f in folder.iterdir())==['request.json','reserved-1.json','response-1.json']
  identity=read(folder/'request.json');reserved=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
  assert digest(identity)==folder.name==reserved['identity_sha256']==response['identity_sha256']
  assert reserved['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
  assert identity['source']=='CNINFO_HTTP' and identity[identityfield]==requestsha
  assert response['status']=='CAPTURED' and digest(response['payload'])==response['payload_sha256']
  envelope=response['payload'];assert envelope['fields']==['http_response'] and len(envelope['rows'])==1
  wire=envelope['rows'][0];body=base64.b64decode(wire['body_base64'],validate=True)
  assert wire['status']==200 and wire['final_url']==identity['url'] and wire['body_complete'] is True
  assert wire['body_truncated'] is False and wire['read_error_type'] is None and wire['read_error'] is None and len(body)<=10485760
  payload=identity['payload']
  if payload is not None:
   assert identity['url']=='https://www.cninfo.com.cn/new/hisAnnouncement/query'
   assert payload['stock']=='600580,gssh0600580' and payload['category']==category and payload['seDate']=='~'.join(window)
   assert payload['pageSize']=='30' and payload['pageNum'] in ('1','2')
   assert int(payload['pageNum']) not in api;api[int(payload['pageNum'])]=json.loads(body)
  else:
   assert identity['url'] not in pdf;pdf[identity['url']]=(folder,body)
 assert len(api)+len(pdf)==m['HTTP_query_reservations']<=budget and m['maximum_HTTP_query_reservations']==budget
 total=int(api[1]['totalAnnouncement']);assert total<=60
 assert set(api)==set(range(1,max(1,(total+29)//30)+1)) and len(pdf)==len(roles)
 rows=[]
 for data in api.values():
  assert int(data['totalAnnouncement'])==total
  for row in data.get('announcements') or []:
   day=datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
   assert window[0]<=day<=window[1];rows.append((row,day))
 for role in roles:
  matches=[(x,d) for x,d in rows if x['secCode']=='600580' and re.search(patterns[role],x['announcementTitle']) and not re.search('更正|修订|取消|补充|摘要',x['announcementTitle'])]
  assert len(matches)==1;row,day=matches[0];doc=m['documents'][role]
  assert doc['code']=='600580' and doc['instrument']=='SH600580' and doc['day']==day and doc['title']==row['announcementTitle']
  assert doc['timestamp_ms']==row['announcementTime'] and doc['announcement_id']==row['announcementId'] and doc['pdf_path']==row['adjunctUrl']
  assert re.fullmatch('[0-9]+',doc['announcement_id']) and doc['pdf_path'].lower()==('finalpage/'+day+'/'+doc['announcement_id']+'.PDF').lower()
  assert doc['url']=='https://static.cninfo.com.cn/'+doc['pdf_path'] and Path(doc['file']).name==doc['file']
  folder,body=pdf[doc['url']];assert (root/doc['file']).read_bytes()==body and body.startswith(b'%PDF') and sha(root/doc['file'])==doc['sha256']
  for prefix,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
   assert doc['HTTP_pdf_receipt'][prefix+'_file']==str((folder/name).relative_to(root)) and doc['HTTP_pdf_receipt'][prefix+'_sha256']==sha(folder/name)
  documents.append({'role':role,'instrument':'SH600580','publication_day':day,'file':doc['file'],'sha256':doc['sha256'],'url':doc['url']})
 outputs.append({'directory':directory,'request_sha256':requestsha,'manifest_sha256':sha(root/'manifest.json'),'HTTP_identities':len(api)+len(pdf),'API_pages':len(api),'PDFs':len(pdf),'all_artifact_bytes_verified':True})
assert len(documents)==3 and sum(x['HTTP_identities'] for x in outputs)==5
result={'status':'ALL_THREE_WOLONG_ORIGINAL_DOCUMENTS_FIVE_HTTP_CHAINS_VERIFIED_REVIEW_SEPARATE',
 'audit_code_sha256':sha(__file__),'captures':outputs,'documents':documents,'immutable_query_artifacts':15,
 'source_errors':0,'original_source_modified':False,'capital_tax_exemption_granted':False,'historical_arrival_certified':False,
 'new_2026_market_queries':False,'portfolio_returns_computed':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n');print('3original PDFs/5HTTP chains fully reconstructed; tax approval separate')
