"""Standalone stdlib eight-case pre2026 primary capture provenance audit.

No production imports, network, PDF economics projection or account calls.
Preparation/self-tests never open the planned actual capture output.
"""
import argparse,base64,copy,hashlib,json,re,subprocess
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path

RAW='low-market-residual-vol1m-raw-pre2026-20261021'
OUTPUT='low-market-residual-vol1m-primary-pre2026-20261021'
PROTOCOL='docs/research/low-market-residual-vol1m-primary-source-plan-2026-10-21.md'
API='https://www.cninfo.com.cn/new/hisAnnouncement/query'
METHODS=('scripts/capture_low_market_residual_vol_primary_pre2026.py','scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py','scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')
PUBLIC=('experiments/qlib/low-market-residual-vol1m-raw-source-independent-audit.json','experiments/qlib/low-market-residual-vol1m-raw-source-capture-manifest.json','experiments/qlib/low-market-residual-vol1m-pre2026-corporate-questions.json')
LOCAL=(RAW+'/manifest.json','cninfo-csi500-reports-20261017/plan.json')
SCOPE=(('SH600763','2024-07-01','2024-07-05','NONCASH'),('SH603290','2024-05-16','2024-05-23','NONCASH'),('SH603688','2024-05-16','2024-05-22','NONCASH'),('SH603927','2024-05-15','2024-05-21','NONCASH'),('SZ000403','2025-05-27','2025-06-04','NONCASH'),('SH601966','2024-06-07','2024-06-14','CONFLICTING_CASH_ROWS'),('SH601966','2025-10-16','2025-10-23','MISSING_CASH_SOURCE_QUESTION'),('SZ000728','2025-01-14','2025-01-21','MISSING_CASH_SOURCE_QUESTION'))
MAX_BODY=10*1024*1024

def need(v,s):
 if not v:raise ValueError(s)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def safe(root,name):
 root=Path(root).resolve();p=Path(name);need(not p.is_absolute() and '..' not in p.parts,'unsafe relative artifact');p=(root/p).resolve();need(p.is_relative_to(root),'source path escape');return p

def page_payload(case,page):
 return {'pageNum':str(page),'pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':case['instrument'][2:]+','+case['organization_id'],'searchkey':'','secid':'','category':'','trade':'','seDate':case['publication_day']+'~'+case['publication_day'],'sortName':'','sortType':'','isHLtitle':'true'}
def identity(url,payload,requestsha):return {'source':'CNINFO_HTTP','url':url,'payload':payload,'notice_request_sha256':requestsha}
def publication(ms):
 need(type(ms) is int,'typed issuer publication timestamp required');return datetime.fromtimestamp(ms/1000,timezone(timedelta(hours=8))).date().isoformat()
def listing(body,case,page,total_before):
 d=json.loads(body);need(isinstance(d,dict),'listing body must be an object');n=d.get('totalAnnouncement');rows=d.get('announcements')
 need(type(n) is int and 0<=n<=60 and page in (1,2) and (total_before is None or n==total_before),'typed stable bounded listing total')
 if n==0 and rows is None:rows=[]
 need(isinstance(rows,list) and len(rows)==max(0,min(30,n-(page-1)*30)),'complete exact listing page length')
 result=[]
 for r in rows:
  need(r['secCode']==case['instrument'][2:] and publication(r['announcementTime'])==case['publication_day'],'wrong issuer/day in exact listing response')
  result.append({'code':r['secCode'],'title':r['announcementTitle'],'day':publication(r['announcementTime']),'timestamp_ms':r['announcementTime'],'announcement_id':r['announcementId'],'pdf_path':r.get('adjunctUrl')})
 return n,result

def selected(rows,case):
 matches=[]
 for r in rows:
  need(r['code']==case['instrument'][2:] and r['day']==case['publication_day'],'implementation issuer/day mismatch')
  title=re.sub(r'<[^>]*>','',r['title']).strip()
  if re.search(r'(?:权益分派|利润分配)实施(?:的)?公告$',title) and not re.search('预案|更正|补充|提示|摘要|取消',title):matches.append(r)
 need(len(matches)==1,'implementation notice not unique')
 r=matches[0];need(isinstance(r['announcement_id'],str) and re.fullmatch('[0-9]+',r['announcement_id']) and isinstance(r['pdf_path'],str) and r['pdf_path'].lower()==('finalpage/'+case['publication_day']+'/'+r['announcement_id']+'.PDF').lower(),'noncanonical implementation PDF path')
 return r

def http_body(record,url):
 need(record['status']=='CAPTURED' and digest(record['payload'])==record['payload_sha256'],'captured payload SHA/status mismatch')
 p=record['payload'];need(p['fields']==['http_response'] and len(p['rows'])==1,'HTTP byte envelope changed');r=p['rows'][0]
 need(type(r['status']) is int and r['status']==200 and r['final_url']==url and r['body_truncated'] is False and r['body_complete'] is True and r['read_error_type'] is None and r['read_error'] is None,'unsuccessful, redirected, partial or incomplete HTTP body')
 body=base64.b64decode(r['body_base64'],validate=True);need(len(body)<=MAX_BODY,'HTTP body exceeds10MiB bound');return body

def reconstruct_inputs(repo,base,reqfile,requestsha,freeze):
 known={};request=read(reqfile)
 def auth(p,h):
  p=Path(p).resolve();need(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) and sha(p)==h,'frozen input bytes changed: '+str(p));known[str(p)]=h
 auth(reqfile,requestsha)
 fixed={'status':'FROZEN_LOW_MARKET_RESIDUAL_VOL1M_EIGHT_PRIMARY_PRE2026','candidate':'low_market_residual_vol_1m','window':['2023-12-29','2025-12-31'],'protocol_file':PROTOCOL,'output_relative':OUTPUT,'maximum_http_query_reservations':24,'max_pages_per_exact_day':2,'max_attempts_per_identity':1,'minimum_interval_seconds':.3,'maximum_consecutive_failed_cases':3}
 for k,v in fixed.items():need(type(request[k]) is type(v) and request[k]==v,'fixed primary scope changed: '+k)
 need([(c['instrument'],c['publication_day'],c['ex_date'],c['kind']) for c in request['cases']]==list(SCOPE),'ordered eight cases changed')
 for k,keys in [('method_code_sha256',METHODS),('public_evidence_sha256',PUBLIC),('local_source_sha256',LOCAL)]:need(set(request[k])==set(keys),'exact source/method map required')
 for flag in ('source_admitted_for_account_replay','portfolio_returns_computed','new_2026_market_queries','objective_achieved'):need(request[flag] is False,'capture request may not grant financial approval')
 commit=subprocess.run(['git','rev-parse','--verify',freeze+'^{commit}'],cwd=repo,capture_output=True,check=True).stdout.decode().strip()
 def committed(name,h):
  blob=subprocess.run(['git','show',commit+':'+name],cwd=repo,capture_output=True,check=True).stdout;need(hashlib.sha256(blob).hexdigest()==h,'freeze commit blob differs: '+name)
 need(Path(reqfile).resolve().is_relative_to(repo),'request must be committed in repo');committed(Path(reqfile).resolve().relative_to(repo).as_posix(),requestsha)
 for field,root in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)]:
  for name,h in request[field].items():
   auth(safe(root,name),h)
   if root==repo:committed(name,h)
 auth(repo/PROTOCOL,request['protocol_sha256']);committed(PROTOCOL,request['protocol_sha256'])
 m=read(base/LOCAL[0]);audit=read(repo/PUBLIC[0]);questions=read(repo/PUBLIC[2])
 need((repo/PUBLIC[1]).read_bytes()==(base/LOCAL[0]).read_bytes() and audit['status']=='PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT' and audit['manifest_sha256']==sha(base/LOCAL[0]) and audit['capture_complete'] is True and audit['critical_or_important_findings']==[] and audit['packet_sha256']==m['per_code_sha256'] and m['capture_complete'] is True and m['abnormal_exit'] is None and not m['errors_sha256'] and not m['pending_codes'] and m['names']==361 and m['query_reservations_consumed']==240 and m['window']==fixed['window'],'terminal raw sources/audit not authenticated')
 need(questions['manifest_sha256']==sha(base/LOCAL[0]) and questions['source_audit']['sha256']==request['public_evidence_sha256'][PUBLIC[0]] and questions['raw_request_sha256']==m['request_sha256'] and questions['counts']['authenticated_packets']==361,'terminal source-question provenance')
 account=base/'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
 financial=audit['old42_financial_sha256'];expected={f'{bps}/{family}/{name}' for bps in (20,40) for family in ('eligible_equal_weight','low_total_vol_1m_control', 'low_market_residual_vol_1m') for name in ('days.csv','decision_intents.json','holdings.csv','orders.csv','positions.pkl','report.pkl','suspension_mark_audit.json')}
 need(set(financial)==expected,'exact42 frozen financial bytes required')
 for name,h in financial.items():auth(safe(account,name),h)
 auth(account/'targets.json',m['target_sha256'])
 need(len(m['per_code_sha256'])==361,'all361 packet source hashes required');packets={}
 for code,h in m['per_code_sha256'].items():
  need(re.fullmatch('(SH|SZ)[0-9]{6}',code),'unsafe source issuer');path=base/RAW/'codes'/(code+'.json');auth(path,h)
  if code in {x[0] for x in SCOPE}:packets[code]=read(path)
 auth(base/RAW/'calendar.json',m['calendar_sha256']);sessions=read(base/RAW/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==fixed['window'],'pre2026 source calendar')
 orgs=read(base/LOCAL[1])['org_by_code'];cases=[]
 for code,pub,ex,kind in SCOPE:
  p=packets[code];need(p['instrument']==code and p['window']==fixed['window'],'case source issuer/window');rows=[r for r in p['distributions'] if r['dividOperateDate']==ex];ad=[r for r in p['adjustments'] if r['dividOperateDate']==ex];days=[r['date'] for r in p['bars']]
  need(len(ad)==1 and ex in days and days.index(ex)>0 and days==sorted(set(days)) and all(fixed['window'][0]<=d<=fixed['window'][1] for d in days),'case adjustment/reference pair')
  need(all(r['code']==code[:2].lower()+'.'+code[2:] for r in rows+ad),'component source issuer')
  if kind=='NONCASH':need(len(rows)==1 and rows[0]['dividPlanDate']==pub and sum(D(rows[0][f] or '0') for f in ('dividStocksPs','dividReserveToStockPs'))>0,'noncash case no longer source-bound')
  elif kind=='CONFLICTING_CASH_ROWS':need(len(rows)==2 and all(r['dividPlanDate']==pub for r in rows) and {r['dividCashPsBeforeTax'] for r in rows}=={'0.286','0.091'} and all(D(r[f] or '0')==0 for r in rows for f in ('dividStocksPs','dividReserveToStockPs')),'conflicting cash rows not both preserved')
  else:need(not rows,'missing source question now contains a vendor row')
  pair=p['bars'][days.index(ex)-1:days.index(ex)+1];need(all(r['code']==code[:2].lower()+'.'+code[2:] and r['adjustflag']=='3' for r in pair),'raw source pair identity')
  if kind=='MISSING_CASH_SOURCE_QUESTION':need(pair[0]['date']==sessions[sessions.index(ex)-1] and all(r['tradestatus']=='1' for r in pair) and abs(D(pair[0]['close'])-D(pair[1]['preclose']))>D('.005'),'actual continuous traded source gap missing')
  need(isinstance(orgs[code],str) and re.fullmatch('[A-Za-z0-9]+',orgs[code]),'invalid org lookup identity')
  cases.append({'case_id':code+'|'+ex,'instrument':code,'publication_day':pub,'ex_date':ex,'kind':kind,'organization_id':orgs[code],'source_distributions':rows,'source_adjustments':ad,'reference_gap_bars':pair,'source_packet_sha256':m['per_code_sha256'][code]})
 need(cases==request['cases'],'independent eight source-case objects differ')
 need(len(known)==417,'independent input map must contain416 source files plus external request')
 return request,known,commit


def self_tests():
 case={'instrument':'SZ000403','publication_day':'2025-05-27'};stamp=int(datetime(2025,5,27,tzinfo=timezone(timedelta(hours=8))).timestamp()*1000)
 row={'secCode':'000403','announcementTime':stamp,'announcementTitle':'派林生物：2024年年度利润分配实施的公告','announcementId':'123','adjunctUrl':'finalpage/2025-05-27/123.PDF'}
 body=json.dumps({'totalAnnouncement':1,'announcements':[row]}).encode();n,rows=listing(body,case,1,None);need(n==1 and selected(rows,case)['announcement_id']=='123','Pailin implementation title success path')
 payload={'fields':['http_response'],'rows':[{'status':200,'final_url':API,'body_truncated':False,'body_complete':True,'read_error_type':None,'read_error':None,'body_base64':base64.b64encode(body).decode()}],'captured_at_utc':'2026-10-21T00:00:00+00:00'}
 envelope={'status':'CAPTURED','payload':payload,'payload_sha256':digest(payload)};need(http_body(envelope,API)==body,'HTTP byte chain success')
 rejected={}
 def reject(k,fn):
  try:fn()
  except (ValueError,KeyError,TypeError):rejected[k]=True
  else:raise AssertionError('negative accepted '+k)
 q=copy.deepcopy(envelope);q['payload']['rows'][0]['body_complete']=False;q['payload_sha256']=digest(q['payload']);reject('incomplete_HTTP_body',lambda:http_body(q,API))
 q=copy.deepcopy(envelope);q['payload_sha256']='0'*64;reject('payload_SHA_tamper',lambda:http_body(q,API))
 q=copy.deepcopy(envelope);q['payload']['rows'][0]['body_base64']='%%%';q['payload_sha256']=digest(q['payload']);reject('invalid_base64',lambda:http_body(q,API))
 q=copy.deepcopy(row);q['secCode']='600763';reject('wrong_listing_issuer',lambda:listing(json.dumps({'totalAnnouncement':1,'announcements':[q]}),case,1,None))
 q=copy.deepcopy(row);q['announcementTime']+=86400000;reject('wrong_listing_publication_day',lambda:listing(json.dumps({'totalAnnouncement':1,'announcements':[q]}),case,1,None))
 reject('typed_listing_total_bool',lambda:listing(json.dumps({'totalAnnouncement':True,'announcements':[row]}),case,1,None))
 reject('incomplete_listing_page',lambda:listing(json.dumps({'totalAnnouncement':2,'announcements':[row]}),case,1,None))
 reject('inconsistent_second_page_total',lambda:listing(json.dumps({'totalAnnouncement':1,'announcements':[row]}),case,2,31))
 reject('two_implementation_notices',lambda:selected(rows+rows,case))
 q=copy.deepcopy(rows);q[0]['title']='派林生物利润分配实施的公告（更正）';reject('correction_is_not_unique_original',lambda:selected(q,case))
 q=copy.deepcopy(rows);q[0]['pdf_path']='finalpage/2025-05-28/123.PDF';reject('PDF_path_day_mismatch',lambda:selected(q,case))
 return rejected


def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--self-test-only',action='store_true');parser.add_argument('--source-preflight-only',action='store_true')
 for name in ('request','expected-request-sha256','freeze-commit','repo-root','source-root','output'):parser.add_argument('--'+name)
 a=parser.parse_args(argv);neg=self_tests()
 if a.self_test_only:print(json.dumps({'negative_controls_rejected':neg,'actual_output_read':False},sort_keys=True));return 0
 need(all(getattr(a,x.replace('-','_')) for x in ('request','expected-request-sha256','freeze-commit','repo-root','source-root')),'explicit frozen request/commit/source roots required')
 repo,base=Path(a.repo_root).resolve(),Path(a.source_root).resolve();req,known,commit=reconstruct_inputs(repo,base,Path(a.request).resolve(),a.expected_request_sha256,a.freeze_commit)
 if a.source_preflight_only:print('417 independent frozen commit/source inputs authenticated; no actual primary output read');return 0
 need(a.output,'independent report output required');root=safe(base,req['output_relative']);m=read(root/'manifest.json');need(m['request_sha256']==a.expected_request_sha256 and (root/'request.json').read_bytes()==Path(a.request).read_bytes(),'captured external request literal differs')
 need(read(root/'input-before.json')==known,'producer before map differs from independently reconstructed417 actual hashes')
 post=read(root/'input-postcheck.json');need(sha(root/'input-postcheck.json')==m['postcheck_sha256'] and post['source_inputs_unchanged_after_capture']==m['source_inputs_unchanged_after_capture'],'source postcheck evidence mismatch')
 tree={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'};need(tree==m['artifact_sha256'],'complete primary container artifact map mismatch')
 need(m['status']=='LOW_MARKET_RESIDUAL_VOL1M_PRIMARY_SOURCES_CAPTURED_REVIEW_SEPARATE' and m['maximum_HTTP_query_reservations']==24 and m['HTTP_query_reservations']<=24,'terminal primary source scope')
 docs=m['documents'];errors=m['errors'];ids=[c['case_id'] for c in req['cases']];need(not set(docs)&set(errors) and set(docs)|set(errors)<=set(ids),'terminal case partition')
 need(read(root/'progress.json')==docs and read(root/'errors.json')==errors,'terminal checkpoint differs from manifest')
 for flag in ('content_reviewed','documents_financially_reviewed','admitted_for_account_replay','corporate_action_completeness_verified','tax_verified','historical_arrival_verified','investment_rule_changed','portfolio_returns_computed','new_2026_queries','objective_achieved'):need(m[flag] is False,'source capture cannot grant review/admission')
 queries={};queryfacts=[]
 qroot=root/'queries'
 for folder in qroot.iterdir() if qroot.exists() else []:
  need(folder.is_dir() and re.fullmatch('[0-9a-f]{64}',folder.name),'query folder identity')
  q=read(folder/'request.json');need(digest(q)==folder.name and set(q)=={'source','url','payload','notice_request_sha256'} and q['source']=='CNINFO_HTTP' and q['notice_request_sha256']==a.expected_request_sha256,'exact query identity digest')
  files={p.name for p in folder.iterdir()};need({'request.json','reserved-1.json'}<=files and files<={'request.json','reserved-1.json','response-1.json'},'exact attempt1 immutable query artifacts')
  reserve=read(folder/'reserved-1.json');need(reserve['identity_sha256']==folder.name and type(reserve['attempt']) is int and reserve['attempt']==1,'reservation identity/attempt')
  when=datetime.fromisoformat(reserve['reserved_at_utc']);need(when.tzinfo is not None,'UTC-aware reserved time')
  record=read(folder/'response-1.json') if (folder/'response-1.json').exists() else None
  if record is not None:
   need(record['identity_sha256']==folder.name and record['reservation_sha256']==sha(folder/'reserved-1.json') and record['status'] in ('CAPTURED','SOURCE_ERROR'),'response provenance/status')
   if record['status']=='CAPTURED':
    need(digest(record['payload'])==record['payload_sha256'],'immutable payload digest')
    captured=datetime.fromisoformat(record['payload']['captured_at_utc']);need(captured.tzinfo is not None and captured>=when,'response timestamp precedes reservation')
  receipt={'request_file':(folder/'request.json').relative_to(root).as_posix(),'request_sha256':sha(folder/'request.json'),'reserved_file':(folder/'reserved-1.json').relative_to(root).as_posix(),'reserved_sha256':sha(folder/'reserved-1.json')}
  if record is not None:receipt.update(response_file=(folder/'response-1.json').relative_to(root).as_posix(),response_sha256=sha(folder/'response-1.json'))
  queries[folder.name]={'identity':q,'record':record,'reserved_at':when,'receipt':receipt};queryfacts.append({'identity_sha256':folder.name,'identity':q,'receipt':receipt,'response_status':record['status'] if record else 'RESERVED_OUTCOME_UNKNOWN'})
 need(len(queries)==m['HTTP_query_reservations'],'actual total consumed reservations differ')
 used=[];cases=[];consecutive=0;processed=[];stopped_at=None
 def take(qid):
  key=digest(qid);need(key in queries and key not in used,'missing or reused HTTP identity');used.append(key);entry=queries[key];need(entry['identity']==qid,'query identity literal changed')
  record=entry['record']
  if record is None or record['status']=='SOURCE_ERROR':raise RuntimeError('retained source failure or reserved unknown outcome')
  data=http_body(record,qid['url']);return data,entry['receipt'],key
 for case in req['cases']:
  key=case['case_id'];first=digest(identity(API,page_payload(case,1),a.expected_request_sha256))
  if first not in queries:break
  processed.append(key);listing_receipts=[];http_evidence=[];failure=None;selectedrow=None
  try:
   body,receipt,qid=take(identity(API,page_payload(case,1),a.expected_request_sha256));total,rows=listing(body,case,1,None);listing_receipts.append(receipt);http_evidence.append({'identity_sha256':qid,'kind':'LISTING','body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'total':total,'page':1})
   if total>30:
    body,receipt,qid=take(identity(API,page_payload(case,2),a.expected_request_sha256));n,extra=listing(body,case,2,total);rows.extend(extra);listing_receipts.append(receipt);http_evidence.append({'identity_sha256':qid,'kind':'LISTING','body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body),'total':n,'page':2})
   need(len(rows)==total,'complete flattened listing total');selectedrow=selected(rows,case);url='https://static.cninfo.com.cn/'+selectedrow['pdf_path']
   body,receipt,qid=take(identity(url,None,a.expected_request_sha256));http_evidence.append({'identity_sha256':qid,'kind':'PDF','body_sha256':hashlib.sha256(body).hexdigest(),'body_bytes':len(body)})
   filename=case['instrument']+'-'+case['publication_day']+'.pdf';need((root/filename).read_bytes()==body and body.startswith(b'%PDF'),'original PDF bytes/signature differ from captured HTTP')
   expected={'instrument':case['instrument'],'publication_day':case['publication_day'],'source_question_ex_date':case['ex_date'],'file':filename,'sha256':hashlib.sha256(body).hexdigest(),'url':url,'listing_row':selectedrow,'HTTP_listing_receipts':listing_receipts,'HTTP_pdf_receipt':receipt,'capture_route':'JOURNALED_ORIGINAL_PRIMARY_HTTP'}
   need(key in docs and docs[key]==expected,'saved accepted PDF docmeta differs from independent chain')
  except (ValueError,KeyError,TypeError,RuntimeError,json.JSONDecodeError) as exc:failure={'type':type(exc).__name__,'reason':str(exc)}
  if key in docs:need(failure is None,'accepted document has an invalid independent provenance chain');consecutive=0
  else:
   need(key in errors and failure is not None,'capture case failure not preserved in terminal errors');errorfile=root/('error-'+key.replace('|','-')+'.json');need(sha(errorfile)==errors[key],'case error hash');error=read(errorfile);need(error['case_id']==key and error['HTTP_responses_retained'] is True and error['financial_approval_granted'] is False,'source failure incorrectly grants approval');consecutive+=1
  cases.append({'case_id':key,'accepted_PDF_byte_chain_verified':key in docs,'selected_notice':selectedrow,'HTTP_body_evidence':http_evidence,'retained_source_error':read(root/('error-'+key.replace('|','-')+'.json')) if key in errors else None,'independent_failure':failure})
  if consecutive>=3:stopped_at=key;break
 need(set(used)==set(queries),'unexpected/out-of-order/unconsumed source query identities')
 chronological=sorted(used,key=lambda k:queries[k]['reserved_at']);need(chronological==used,'reservation timestamps contradict frozen ordered case/page/PDF sequence')
 pending=[k for k in ids if k not in docs and k not in errors];need(m['pending_cases']==pending and set(processed)==set(docs)|set(errors),'terminal processed/pending case partition')
 if stopped_at is not None:need(read(root/'stopped.json')=={'reason':'THREE_CONSECUTIVE_FAILED_CASES','last_case_id':stopped_at},'three-failure stop evidence')
 else:need(not (root/'stopped.json').exists(),'unexplained stopped marker')
 if m['abnormal_exit'] is not None:need(read(root/'terminal-error.json')==m['abnormal_exit'],'abnormal terminal evidence')
 else:need(not pending or stopped_at is not None,'pending without stop/abnormal closure')
 if errors or m['abnormal_exit'] is not None or not post['source_inputs_unchanged_after_capture']:need((root/'first-error.json').is_file(),'first source error was not preserved')
 complete=len(docs)==8 and not errors and m['abnormal_exit'] is None and post['source_inputs_unchanged_after_capture'] is True and len(queries)<=24
 need(m['capture_complete'] is complete,'source completeness flag inconsistent with independent reconstruction')
 for path,h in known.items():need(sha(path)==h,'frozen source bytes changed after capture')
 need(tree=={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'},'capture artifacts changed during audit')
 report={'status':'PASS_INDEPENDENT_EIGHT_PRIMARY_CAPTURE_AUDIT' if complete else 'PARTIAL_TERMINAL_PRIMARY_CAPTURE_PRESERVED_NOT_ADMITTED','request_sha256':a.expected_request_sha256,'freeze_commit':commit,'manifest_sha256':sha(root/'manifest.json'),'audit_code_sha256':sha(__file__),'capture_complete':complete,'accepted_documents':len(docs),'case_errors':errors,'pending_cases':pending,'abnormal_exit':m['abnormal_exit'],'HTTP_query_reservations_reconstructed':len(queries),'maximum_HTTP_logical_budget':24,'attempts_per_identity':1,'independent_bound_input_files':len(known),'all42_old_financial_files_and_original_target_byte_unchanged':True,'all361_source_packets_authenticated':True,'freeze_commit_request_method_protocol_public_blobs_authenticated':True,'input_before_exact_independent_map':True,'source_postcheck':post,'case_reviews':cases,'query_provenance':queryfacts,'artifact_sha256':tree,'source_input_sha256':known,'negative_controls_rejected':neg,'critical_or_important_findings':[],
  'network_used_by_auditor':False,'imports_business_modules':False,'content_reviewed_by_this_audit':False,'primary_economics_projected':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'2026_market_queries':0,
  'limitations':['Byte provenance and bounded query/case closure only. Original PDF economics, tax, lifecycle and corporate-event admission require separate content review.','HTTP decoded bodies/status are retained, not TCP wire packets. Completeness follows authenticated client full-body/error flags; original Content-Length headers are not independently retained.','Logical reservation counts/attempt1 and code no-resume/fresh-directory guards are verified; cannot prove absence of an external unrecorded prior process.','0.3-second transport throttle is enforced by frozen code; reservations occur before waits, so exact actual wire start spacing is not independently certified.','Timestamp/order checks use captured system clock records, not historical publication-arrival or PIT certification.']}
 out=Path(a.output);need(not out.exists(),'preserve prior independent report');out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n');print('independent primary byte/query provenance audited; content/financial admission remainsfalse');return 0

if __name__=='__main__':raise SystemExit(main())
