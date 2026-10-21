"""Independent stdlib audit of local reassembly. Run only after terminal notification.
No project imports, production assembly/coordinate calls, network, account or ROI.
"""
from pathlib import Path
from fractions import Fraction as Q
from decimal import Decimal as D
from datetime import date,datetime
from collections import Counter
import argparse,base64,copy,hashlib,json,re,subprocess
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
S=B/'price-delay-raw-horizon-20261021';V=B/'price-delay-raw-horizon-v2-20261021'
P=B/'price-delay-horizon-missing-primary-20261021'
REQ=R/'experiments/qlib/price-delay-horizon-local-reassembly-request.json'
OUT=Path('/tmp/price-delay-horizon-local-reassembly-independent-audit-20261021.json')
EXPECTED='b43aa018c7439824913841643df4af9ea6d6cdb454e18a8bfe570d33974cf12d'
START,PRE,END='2023-12-29','2025-12-31','2026-10-20';HALF=Q(1,2000000)
BF=['date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST']
DF=['code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs']
AF=['code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor']
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(x,msg):
 if not x:raise AssertionError(msg)
def safe(root,rel):
 p=root/rel;need(not Path(rel).is_absolute() and '..' not in Path(rel).parts and p.resolve().is_relative_to(root.resolve()),'safe path');return p
def tree(root):return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def qs(x):return str(x.numerator)+'/'+str(x.denominator)
def six(x):
 need(isinstance(x,str) and re.fullmatch(r'[0-9]+\.[0-9]{6}',x) is not None and Q(x)>HALF,'positive six decimal');return Q(x)
def unique(rows,key):
 keys=[r[key] for r in rows];need(keys==sorted(set(keys)),'unique ordered dates');return dict(zip(keys,rows))
def core(r):return [r['date'],r['code'],*[Q(r[k]) if r[k] else None for k in ('open','high','low','close','preclose','volume','amount')],r['adjustflag'],r['tradestatus'],r['isST']]
def clipped(p):
 v={'instrument':p['instrument'],'window':[START,PRE]}
 for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:v[f]=[r for r in p[f] if START<=r[k]<=PRE]
 v['quarantine']=[q for q in p.get('quarantine',[]) if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']<=PRE];return v

def chain(root,receipt,identity_expected,fields):
 paths={k:safe(root,receipt[k+'_file']) for k in ('request','reserved','response')}
 for k,p in paths.items():need(sha(p)==receipt[k+'_sha256'],'receipt bytes')
 i=read(paths['request']);key=digest(i);reserve=read(paths['reserved']);response=read(paths['response'])
 need(i==identity_expected and paths['request'].parent==root/'queries'/key,'exact component query identity')
 need(paths['reserved'].name=='reserved-1.json' and paths['response'].name=='response-1.json' and reserve['attempt']==1 and reserve['identity_sha256']==key,'one reservation/attempt')
 need(response['identity_sha256']==key and response['status']=='CAPTURED' and response['reservation_sha256']==sha(paths['reserved']) and response['payload_sha256']==digest(response['payload']),'response chain')
 env=response['payload'];need(env['fields']==['provider_response'] and len(env['rows'])==1 and datetime.fromisoformat(reserve['reserved_at_utc'])<=datetime.fromisoformat(env['captured_at_utc']),'SDK envelope chronology');wire=env['rows'][0]
 need(wire['initial_error_code']==wire['final_error_code']=='0' and wire['iteration_error_type'] is None and wire['iteration_error'] is None,'SDK terminal status')
 need(wire['fields']==fields and all(len(r)==len(fields) for r in wire['rows']),'schema');return [dict(zip(fields,r)) for r in wire['rows']]
def validate(c,p,sessions):
 need(p['instrument']==c and p['window']==[START,END] and [r['date'] for r in p['bars']]==sessions,'issuer/676calendar')
 for r in p['bars']:
  need(list(r)==BF and r['code']==c[:2].lower()+'.'+c[2:] and r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1'),'raw state')
  for k in ('open','high','low','close','preclose','volume','amount'):need(not r[k] or D(r[k]).is_finite() and D(r[k])>=0,'raw number')
  if r['tradestatus']=='1':need(all(r[k] and D(r[k])>0 for k in ('open','high','low','close','preclose','volume')) and D(r['low'])<=min(D(r['open']),D(r['close']))<=max(D(r['open']),D(r['close']))<=D(r['high']),'active OHLC')
 for f,fields in [('distributions',DF),('adjustments',AF)]:
  need(len(p[f])==len({digest(r) for r in p[f]}),'corporate duplicates')
  for r in p[f]:need(list(r)==fields and r['code']==c[:2].lower()+'.'+c[2:] and START<=r['dividOperateDate']<=END,'accepted corporate boundaries')
def reconstruct_proof(src,ref,review):
 lo='2026-01-01';hi=ref['window'][1];a=unique([r for r in src['bars'] if r['date']<=hi],'date');b=unique([r for r in ref['bars'] if r['date']>=lo],'date')
 need(a.keys()==b.keys() and all(core(a[d])==core(b[d]) for d in a),'all188 common raw cores')
 dv=[r for r in src['distributions'] if lo<=r['dividOperateDate']<=hi];need(dv==[r for r in ref['distributions'] if lo<=r['dividOperateDate']<=hi],'allcommon dividend fields')
 old=unique([r for r in ref['adjustments'] if r['dividOperateDate']>=lo],'dividOperateDate');new=unique(src['adjustments'],'dividOperateDate');need(set(old)<=set(new),'retained old adjustment dates');added=[r for d,r in new.items() if d>hi]
 need(len(added)==1 and added[0]['dividOperateDate']==review['ex_date'] and Q(review['stock_per_original_share'])==Q(review['capital_per_original_share'])==0 and review['cash_per_original_share_CNY']=='0.41','separately reviewed primary cash only dates')
 ob=old[max(old)];nb=new[max(new)];need(ob['foreAdjustFactor']==nb['foreAdjustFactor']=='1.000000','latestfore one');x,y=six(ob['backAdjustFactor']),six(nb['backAdjustFactor']);need(y>x,'latestback increase');ratio=x/y;rl=(x-HALF)/(y+HALF);rh=(x+HALF)/(y-HALF);steps=[]
 for d,before in old.items():
  after=new[d];need({k:v for k,v in before.items() if k!='foreAdjustFactor'}=={k:v for k,v in after.items() if k!='foreAdjustFactor'},'allnonfore exact');aa,bb=six(before['foreAdjustFactor']),six(after['foreAdjustFactor']);lower=(aa-HALF)*rl;upper=(aa+HALF)*rh;need(lower<=bb+HALF and upper>=bb-HALF,'rational rounding interval overlap')
  steps.append({'date':d,'cached_fore':before['foreAdjustFactor'],'fresh_fore':after['foreAdjustFactor'],'predicted_interval':[qs(lower),qs(upper)],'fresh_rounding_interval':[qs(bb-HALF),qs(bb+HALF)],'nonfore_fields_exact':True})
 for row in new.values():
  for k in AF[2:]:six(row[k])
 need(added[0]['adjustFactor']==added[0]['backAdjustFactor'],'newfactor integrity')
 return {'instrument':'SH603233','comparison_window':[lo,hi],'common_daily_rows':len(a),'common_distribution_rows':len(dv),'old_latest_back':ob['backAdjustFactor'],'new_latest_back':nb['backAdjustFactor'],'ratio_exact':qs(ratio),'ratio_rounding_interval':[qs(rl),qs(rh)],'common_fore_coordinate_checks':steps,'new_adjustment_row':added[0],'primary_notice':review,'economic_cause_inferred_from_factors':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--terminal-confirmed',action='store_true');ap.add_argument('--freeze-commit',required=True);a=ap.parse_args();need(a.terminal_confirmed,'terminal notification required before actual output read')
 req=read(REQ);need(sha(REQ)==EXPECTED==sha(V/'request.json'),'frozen reassembly request');freeze=subprocess.check_output(['git','rev-parse',a.freeze_commit],cwd=R,text=True).strip();need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(REQ.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozenrequestblob')
 for field,parent in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('immutable_financial_sha256',B)]:
  for n,h in req[field].items():
   need(sha(safe(parent,n))==h,'immutable binding '+n)
   if parent==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'frozenmethod/evidence '+n)
 need(tree(S)==req['immutable_capture_tree_sha256'] and tree(P)==req['immutable_primary_tree_sha256'],'full oldcapture/primary exact trees');need(len(req['immutable_financial_sha256'])==48,'48 oldfinancials')
 rawreq=read(R/'experiments/qlib/price-delay-horizon-raw-source-request.json');rawaudit=read(R/'experiments/qlib/price-delay-horizon-raw-independent-audit.json');sm=read(S/'manifest.json');ss=read(S/'price-delay-scope.json')
 need(rawaudit['failed_capture_correctly_preserved'] is True and rawaudit['imports_project_code'] is False and rawaudit['capture_manifest_sha256']==sha(S/'manifest.json') and rawaudit['scope_sha256']==sha(S/'price-delay-scope.json') and rawreq['immutable_financial_sha256']==req['immutable_financial_sha256'],'previous independent failedcapture anchor')
 actualq={str(p.relative_to(S)):sha(p) for p in (S/'queries').rglob('*') if p.is_file()};need(actualq==rawaudit['query_artifact_sha256'] and len(actualq)==1035,'all original345 query trees unchanged');need(sm['names']==202 and list(sm['errors_sha256'])==['SH603233'] and sm['pending_codes']==[] and ss['capture_complete'] is False,'originalfailure not relabelled')
 pm=read(P/'manifest.json');content=read(R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json');pa=read(R/'experiments/qlib/price-delay-horizon-single-primary-independent-review.json');doc=pm['documents']['SH603233'];review=content['documents'][0]
 need(pm['capture_complete'] is True and not pm['errors'] and pm['http_query_reservations']==1 and content['capture_manifest_sha256']==pa['capture_manifest_sha256']==sha(P/'manifest.json') and pa['root_content_review_sha256']==sha(R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json') and pa['imports_project_code'] is False and pa['all4pages_independently_text_extracted_and_visually_reviewed'] is True and not pa['critical'] and not pa['important'],'independent originalPDF content anchor')
 need(all(doc[k]==review[k] for k in ('instrument','file','sha256','publication_day')),'PDF content identity');pdf=safe(P,doc['file']);need(sha(pdf)==doc['sha256'] and pdf.read_bytes().startswith(b'%PDF'),'originalPDFbytes')
 paths={}
 for k in ('request','reserved','response'):paths[k]=safe(P,doc['pdf_receipt'][k+'_file']);need(sha(paths[k])==doc['pdf_receipt'][k+'_sha256'],'primaryreceiptbytes')
 i=read(paths['request']);reserve=read(paths['reserved']);resp=read(paths['response']);need(i['source']=='CNINFO_HTTP' and i['url']==doc['url'] and i['payload'] is None and reserve['attempt']==1 and reserve['identity_sha256']==resp['identity_sha256']==digest(i) and resp['reservation_sha256']==sha(paths['reserved']) and resp['status']=='CAPTURED','HTTP logicalchain')
 payload=resp['payload'];need(resp['payload_sha256']==digest(payload) and payload['fields']==['http_response'] and len(payload['rows'])==1,'HTTP payloadbinding');w=payload['rows'][0];need(w['status']==200 and w['final_url']==doc['url'] and w['body_complete'] is True and w['body_truncated'] is False and w['read_error_type'] is None and w['read_error'] is None and base64.b64decode(w['body_base64'],validate=True)==pdf.read_bytes(),'complete HTTP PDF body')
 c='SH603233';route=rawreq['cache_routes'][c];refpath=B/route['cache_route']/'codes'/(c+'.json');need(sha(refpath)==route['cache_packet_sha256'] and route['source_class']=='incremental','original fixedderivedroute');ref=read(refpath);baseline=clipped(ref);sessions=read(S/'calendar.json')['sessions'];need(len(sessions)==676 and sessions==sorted(set(sessions)) and [r['date'] for r in baseline['bars']]==sessions[:486],'676calendar/derived486baseline')
 receipts={};src={'instrument':c,'window':['2026-01-01',END],'bars':[],'distributions':[],'adjustments':[],'quarantine':[]}
 for comp,fields in [('daily',BF),('dividend2026',DF),('adjustments',AF)]:
  params={'start_date':'2026-01-01','end_date':END,'frequency':'d','adjustflag':'3'} if comp=='daily' else {'start_date':'2026-01-01','end_date':END} if comp=='adjustments' else {'year':'2026','yearType':'operate'}
  ident={'source':'BaoStock','instrument':c,'component':comp,'parameters':params,'composite_raw_extension_request_sha256':req['original_request_sha256']};folder=S/'queries'/digest(ident);receipt={}
  for k,n in [('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')]:p=folder/n;receipt[k+'_file']=str(p.relative_to(S));receipt[k+'_sha256']=sha(p)
  rows=chain(S,receipt,ident,fields);receipts[comp]=receipt
  if comp=='dividend2026':
   for row in rows:
    d=row['dividOperateDate']
    if not d:src['quarantine'].append({'reason':'MISSING_OPERATE_DATE','record':row})
    else:
     need(date.fromisoformat(d).isoformat()==d and d[:4]=='2026','operatedate/year')
     if not START<=d<=END:src['quarantine'].append({'reason':'AFTER_EXTENSION_CUTOFF' if d>END else 'BEFORE_EXTENSION_WINDOW','record':row})
     else:src['distributions'].append(row)
  else:src['bars' if comp=='daily' else 'adjustments']=rows
 need([r['date'] for r in src['bars']]==sessions[486:] and not any(r['dividOperateDate']==review['ex_date'] for r in src['distributions']),'complete190freshbars, no invented vendorcash')
 proof=reconstruct_proof(src,ref,review);need(digest(proof)==req['new_coordinate_proof_sha256'] and read(V/'new-coordinate-proof.json')==proof,'independent sixdecimal Fraction proof exact')
 packet={'instrument':c,'window':[START,END]}
 for f,k in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:packet[f]=baseline[f]+[r for r in src[f] if r[k]>PRE]
 packet['quarantine']=baseline['quarantine']+[q for q in src['quarantine'] if not q['record'].get('dividOperateDate') or q['record']['dividOperateDate']>PRE];packet['source_query_receipts']=receipts
 packet['provenance']={'kind':'LOCAL_ONLY_PRICE_DELAY_PRIMARY_COORDINATE_ASSEMBLY','request_sha256':EXPECTED,'original_failed_capture_manifest_sha256':sha(S/'manifest.json'),'original_query_receipts_relative_to':S.name,'source_query_receipts':receipts,'baseline_provenance':None,'baseline_source_route':route,'primary_notice_sha256':review['sha256'],'factor_values_normalized_or_rewritten':False,'vendor_dividend_rows_supplemented':False}
 need(read(V/'codes'/ (c+'.json'))==packet and clipped(packet)==baseline,'full reassembled packet/metadata and literal486prefix')
 hashes={};copied={};totals=Counter();original_prefixes={}
 for code in rawreq['codes']:
  p=V/'codes'/(code+'.json');v=read(p);validate(code,v,sessions);hashes[code]=sha(p)
  if code!=c:need(p.read_bytes()==(S/'codes'/(code+'.json')).read_bytes() and hashes[code]==sm['per_code_sha256'][code],'202literal bytecopy');copied[code]=hashes[code]
  for f in ('bars','distributions','adjustments','quarantine'):totals[f]+=len(v[f])
  if code in rawreq['original_packet_sha256']:
   op=B/'price-delay-raw-dev-20261021/codes'/(code+'.json');need(sha(op)==rawreq['original_packet_sha256'][code] and clipped(v)==clipped(read(op)),'original151literalprefix');original_prefixes[code]=sha(op)
 need(len(hashes)==203 and len(copied)==202 and len(original_prefixes)==151 and {p.name for p in (V/'codes').iterdir()}=={x+'.json' for x in hashes},'exact203files');need((V/'calendar.json').read_bytes()==(S/'calendar.json').read_bytes(),'calendarbytecopy')
 expected_manifest={'status':'PRICE_DELAY_203_LOCAL_RAW_REASSEMBLY_INDEPENDENT_ADMISSION_PENDING','request_sha256':EXPECTED,'target_sha256':rawreq['target_sha256'],'window':[START,END],'names':203,'calendar_sha256':sha(V/'calendar.json'),'per_code_sha256':hashes,'copied_packet_sha256':copied,'reassembled_codes':[c],'totals':dict(totals),'new_coordinate_proof_sha256':sha(V/'new-coordinate-proof.json'),'original_failed_capture_manifest_sha256':sha(S/'manifest.json'),'original_query_receipts_relative_to':S.name,'original_query_reservations_consumed':345,'primary_manifest_sha256':sha(P/'manifest.json'),'all_original_capture_bytes_unchanged':True,'all48_financial_artifacts_unchanged':True,'local_assembly_complete':True,'new_source_queries':0,'factor_values_rewritten':False,'vendor_cash_rows_supplemented':False,'source_admitted_for_account_replay':False,'historical_arrival_verified':False,'portfolio_returns_computed':False,'investment_rules_changed':False,'full_October_2026_complete':False,'objective_achieved':False}
 need(read(V/'manifest.json')==expected_manifest,'all manifest metadata/counts/hashes/boundaries');need({str(p.relative_to(V)) for p in V.rglob('*') if p.is_file()}=={'manifest.json','request.json','calendar.json','new-coordinate-proof.json'}|{'codes/'+x+'.json' for x in hashes},'exactoutput file scope no newqueries')
 neg={}
 def reject(label,fn):
  try:fn()
  except AssertionError:neg[label]=True
  else:raise AssertionError('semanticnegative accepted '+label)
 bad=copy.deepcopy(src);bad['adjustments'][0]['foreAdjustFactor']='1.000000';reject('fore_outside_rounding_interval',lambda:reconstruct_proof(bad,ref,review))
 bad=copy.deepcopy(src);bad['adjustments'][0]['backAdjustFactor']='3.000000';reject('common_nonfore_change',lambda:reconstruct_proof(bad,ref,review))
 bad=copy.deepcopy(review);bad['cash_per_original_share_CNY']='0.40';reject('cash_not_exact_reviewed_primary',lambda:reconstruct_proof(src,ref,bad))
 bad=copy.deepcopy(packet);bad['bars'].pop();reject('missing_source_session',lambda:validate(c,bad,sessions))
 bad=copy.deepcopy(expected_manifest);bad['source_admitted_for_account_replay']=True;reject('ungranted_source_account_admission',lambda:need(bad==expected_manifest,'boundarychange'))
 need(tree(S)==req['immutable_capture_tree_sha256'] and tree(P)==req['immutable_primary_tree_sha256'],'postaudit all sourcebytes unchanged')
 for n,h in req['immutable_financial_sha256'].items():need(sha(B/n)==h,'postaudit48financials')
 report={'status':'PASS_INDEPENDENT_LOCAL_ONLY_SOURCE_REASSEMBLY_AUDIT_ADMISSION_PENDING','manifest_sha256':sha(V/'manifest.json'),'request_sha256':EXPECTED,'freeze_commit':freeze,'audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'production_assembly_or_coordinate_function_called':False,'method_code_sha256':req['method_code_sha256'],'original_failed_capture_manifest_sha256':sha(S/'manifest.json'),'original_failed_capture_complete':False,'original345_receipt_tree_unchanged':True,'original_query_artifact_sha256':actualq,'all_original_capture_tree_unchanged':True,'immutable_capture_tree_file_count':len(req['immutable_capture_tree_sha256']),'immutable_primary_tree_unchanged':True,'copied202_packets_byte_identical':True,'reassembled_SH603233_three_saved_component_projection_exact':True,'SH603233_reassembled_packet_sha256':hashes[c],'all203_packets_676_sessions_verified':True,'all151_original_literal_pre2026_prefixes_identical':True,'derived486_SH603233_baseline_literal_prefix_identical':True,'all48_old_financial_artifacts_unchanged':True,'per_code_sha256':hashes,'totals_independently_reconstructed':dict(totals),'new_coordinate_proof_sha256':sha(V/'new-coordinate-proof.json'),'new_coordinate_proof_canonical_sha256':digest(proof),'independent_fraction_proof':proof,'primary_manifest_sha256':sha(P/'manifest.json'),'primary_PDF_sha256':sha(pdf),'primary_content_review_sha256':sha(R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json'),'primary_independent_review_sha256':sha(R/'experiments/qlib/price-delay-horizon-single-primary-independent-review.json'),'primary_HTTP_full_bytes_chain_verified':True,'cash_source':'Separately reviewed original issuer PDF;0.41CNY/share, not inferred from adjustment factors.','economic_cause_inferred_from_factors':False,'vendor_dividend_rows_supplemented':False,'factor_values_rewritten':False,'new_source_queries':0,'network_calls':0,'semantic_negative_controls_rejected':neg,'source_admitted_for_account_replay':False,'historical_arrival_verified':False,'portfolio_returns_computed':False,'full_October_2026_complete':False,'investment_rules_changed':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Local source assembly and coordinate rounding consistency only; original failedcapture remains unchanged and false.','The primary PDF0.41cash is separate from vendor rows; no missing vendor cash row was created and factor changes do not establish economic cause.','Literal pre2026coordinate prefix is preserved; this is not a globally normalized coordinate history.','No corporate-action/source-account admission, tax/PIT/arrival certification or account return claim.','No new transport calls; old logical SDK/HTTP chains do not certify all physical TCP attempts.']}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(OUT),'report_sha256':sha(OUT),'audit_code_sha256':report['audit_code_sha256'],'manifest_sha256':report['manifest_sha256'],'203names':True,'new_queries':0}))
if __name__=='__main__':main()
