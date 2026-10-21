"""Read-only independent29pre2026 session audit; no projectimports/network/accounts."""
import argparse,copy,hashlib,json,pathlib,re,struct,subprocess
from datetime import datetime,timedelta
from decimal import Decimal as D
from collections import Counter
import pyarrow.parquet as pq

FREEZE='d5ef5bce96f84c534ee8ce0b64cec602c71479a2'
REQUEST='experiments/qlib/illiquidity-hf-archive-probe-request.json'
EXPECTED='6927ea42f2217fe0a19076fcf683dee0d760faef8c89df1ae2c97cbf5736c144'
ADMISSION='experiments/qlib/illiquidity-development-minute-admission.json'
FIELDS=('symbol','exchange','timestamp','open','high','low','close','volume','turnover')

def sha(p):
 d=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):d.update(b)
 return d.hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def require(v,msg):
 if not v:raise ValueError(msg)
def gitbytes(repo,path):return subprocess.check_output(['git','show',FREEZE+':'+path],cwd=repo)
def verify_object(path,spec):
 require(path.stat().st_size==spec['size'] and sha(path)==spec['oid'],'immutable objectOID/length differs')
def labels240(day):
 labels=[]
 for a,z in [('09:31','11:30'),('13:01','15:00')]:
  t=datetime.fromisoformat(day+'T'+a)
  while t.strftime('%H:%M')<=z:labels.append(t.strftime('%H:%M'));t+=timedelta(minutes=1)
 return labels

def reconstruct(code,day,rows,daily):
 require('2024-01-01'<=day<='2025-12-31' and daily['date']==day and daily['tradestatus']=='1','date/daily active scope')
 require(bool(rows),'selected requested date missing')
 labels=[];prices=[];volumes=[];cent_fail=0
 for r in rows:
  require(set(r)==set(FIELDS) and r['symbol']==code[2:] and r['exchange']==code[:2],'minute field/issuer mismatch')
  t=r['timestamp'];require(type(t) is datetime and t.tzinfo is None and t.date().isoformat()==day and t.second==t.microsecond==0,'minute clock mismatch')
  label=t.strftime('%H:%M');require('09:30'<=label<='11:30' or '13:00'<=label<='15:00','minute outside sessions')
  labels.append(label);v={k:D(str(r[k])) for k in ['open','high','low','close']}
  require(all(x.is_finite() and x>=0 for x in v.values()),'nonfinite/negativeOHLC')
  require(v['low']<=min(v['open'],v['close'])<=max(v['open'],v['close'])<=v['high'],'inconsistentOHLC')
  require(type(r['volume']) is int and r['volume']>=0,'volume not nonnegative integer')
  require(r['volume']==0 or min(v.values())>0,'positive volume with zero price')
  turn=D(str(r['turnover']));require(turn.is_finite() and turn>=0,'nonfinite/negativeturnover')
  # Exact divisibility test, no quantize/round/writeback to prices.
  cent_fail+=sum(x*100!=(x*100).to_integral_value() for x in v.values())
  prices.append(v);volumes.append(r['volume'])
 require(labels==sorted(set(labels)),'unsorted/duplicate minute labels')
 aggregates={'open':prices[0]['open'],'high':max(v['high'] for v in prices),'low':min(v['low'] for v in prices),'close':prices[-1]['close']}
 ck={'exact_existing_240_end_labels':labels==labels240(day),'all_prices_exact_cent_without_rounding':cent_fail==0,
 'first_open_matches':aggregates['open']==D(daily['open']),'highest_matches':aggregates['high']==D(daily['high']),
 'lowest_matches':aggregates['low']==D(daily['low']),'last_close_matches':aggregates['close']==D(daily['close']),
 'total_volume_matches':sum(volumes)==D(daily['volume'])}
 out={'instrument':code,'day':day,'rows':len(rows),'first_label':labels[0],'last_label':labels[-1],'labels':labels,'source_checks':ck,
 'archive_total_volume_shares':sum(volumes),'daily_volume_shares':daily['volume'],'all_numeric_and_existing_label_checks_pass':all(ck.values()),
 'upstream_providers_independently_authenticated':False,'minute_interval_semantics_authenticated':False,'admitted_for_reconstructed_execution':False,'status':'SOURCE_COMPARISON_COMPLETE'}
 diag={}
 for k,v in aggregates.items():
  expected=D(daily[k]); encoded=struct.unpack('!f',struct.pack('!f',float(expected)))[0]
  diag[k]={'archive_decimal_from_original_float_text':str(v),'raw_daily_decimal':daily[k],'exact_comparison':v==expected,
   'daily_decimal_reencoded_IEEE754_binary32_then_binary64_exactly_matches_archive':D(str(encoded))==v,
   'archive_minus_raw_daily':str(v-expected)}
 return out,diag,cent_fail

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',required=True);ap.add_argument('--source-root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 repo=pathlib.Path(a.repo_root);base=pathlib.Path(a.source_root);request=repo/REQUEST
 require(sha(request)==EXPECTED and hashlib.sha256(gitbytes(repo,REQUEST)).hexdigest()==EXPECTED,'current/frozen requestSHA mismatch')
 plan=read(request);out=base/plan['output_relative'];summary=read(out/'summary.json')
 require(plan['maximum_logical_requests']==3 and plan['max_attempts_per_identity']==1 and plan['portfolio_replay_allowed'] is False,'source-only budget mismatch')
 for f,h in plan['method_code_sha256'].items():require(sha(repo/f)==h==hashlib.sha256(gitbytes(repo,f)).hexdigest(),'frozen methodbytes mismatch')
 adm=read(repo/ADMISSION);require(sha(repo/ADMISSION)==plan['admission_sha256'],'oldadmissionSHA mismatch')
 pairs=plan['pairs'];require(pairs==sorted([[x['instrument'],x['day']] for x in adm['exceptions']]) and len(pairs)==29 and len({tuple(p) for p in pairs})==29,'requested pairs are not exact29oldexceptions')
 require(all(c in plan['objects'] and '2024-01-01'<=d<='2025-12-31' for c,d in pairs),'pair scope mismatch')
 known={str(repo/f):h for f,h in plan['method_code_sha256'].items()};known[str(repo/ADMISSION)]=plan['admission_sha256'];known[str(request)]=EXPECTED
 known.update({str(base/f):h for f,h in plan['source_file_sha256'].items()})
 require(len(known)==16 and read(out/'input-before.json')==known,'exact16input-before map mismatch')
 require(read(out/'input-postcheck.json')=={f:True for f in known},'inputpostcheck mismatch')
 for f,h in known.items():require(sha(f)==h,'actualboundinput changed')
 reserved=[read(p) for p in sorted(out.glob('reserved-*.json'))];require(len(reserved)==3,'logicalreservationcount mismatch')
 expected_batch={'method':'LFS_BATCH_DOWNLOAD','url':'https://huggingface.co/datasets/'+plan['dataset']+'.git/info/lfs/objects/batch','body':{'operation':'download','transfers':['basic'],'ref':{'name':plan['revision']},'objects':[{'oid':v['oid'],'size':v['size']} for v in plan['objects'].values()]}}
 require(reserved[0]==expected_batch,'batch identity mismatch')
 # Private signedURL response is parsed locally only for nonsecret object identities.
 # Never emit href/header values or exceptions containing its payload.
 private=read(out/'private-batch-response.json');objs=private['objects'];require(len(objs)==2 and len({x['oid'] for x in objs})==2,'privatebatchobjectidentity mismatch')
 require({(x['oid'],x['size']) for x in objs}=={(v['oid'],v['size']) for v in plan['objects'].values()} and all('error' not in x for x in objs),'batchOID/size mismatch')
 from urllib.parse import urlsplit
 for i,(code,spec) in enumerate(plan['objects'].items(),1):
  obj=next(x for x in objs if x['oid']==spec['oid']);parts=urlsplit(obj['actions']['download']['href'])
  require(parts.scheme=='https' and parts.hostname and (parts.hostname=='huggingface.co' or parts.hostname.endswith(('.huggingface.co','.hf.co'))),'download authority invalid')
  require(reserved[i]=={'method':'PINNED_OBJECT_GET','instrument':code,'oid':spec['oid'],'size':spec['size'],'download_authority':parts.hostname},'objectreservation mismatch')
 del private,objs,obj,parts
 records=[];diagnostics=[];rowcount=0;noncent=0;object_checks=[];sample=None
 for code,spec in plan['objects'].items():
  pointer=(base/'illiquidity-hf-archive-metadata-20261021'/spec['file']).read_text()
  require(pointer==f"version https://git-lfs.github.com/spec/v1\noid sha256:{spec['oid']}\nsize {spec['size']}\n",'LFS pointer identity mismatch')
  path=out/(code+'.parquet');verify_object(path,spec)
  receipt=read(out/(code+'-receipt.json'));require(receipt=={'instrument':code,'file':spec['file'],'expected_sha256':spec['oid'],'status':'OBJECT_VERIFIED_SELECTED_DEVELOPMENT_COMPARISON_COMPLETE'},'objectreceipt mismatch')
  days=[d for c,d in pairs if c==code]
  filters=[[('timestamp','>=',datetime.fromisoformat(d)),('timestamp','<',datetime.fromisoformat(d)+timedelta(days=1))] for d in days]
  table=pq.read_table(path,columns=list(FIELDS),filters=filters)
  rows=table.to_pylist();require(all(type(r['timestamp']) is datetime and r['timestamp'].tzinfo is None and r['timestamp'].date().isoformat() in days for r in rows),'filteredreader returnedunrequesteddate')
  require({r['timestamp'].date().isoformat() for r in rows}==set(days),'missingrequesteddate')
  require([{**r,'timestamp':r['timestamp'].isoformat()} for r in rows]==read(out/(code+'-selected-development-rows.json')),'selectedrows artifact differsfromfilteredParquet')
  daily={r['date']:r for r in read(base/plan['raw_packet_relative'][code])['bars'] if r['date'] in days}
  require(set(daily)==set(days),'missingrawrequesteddate')
  object_checks.append({'instrument':code,'oid':spec['oid'],'bytes':spec['size'],'selected_rows':len(rows),'selected_days':len(days),'schema':str(table.schema)})
  rowcount+=len(rows)
  for day in days:
   selected=[r for r in rows if r['timestamp'].date().isoformat()==day]
   rec,diag,nonc=reconstruct(code,day,selected,daily[day]);require(rec==next(x for x in summary['session_comparisons'] if x['instrument']==code and x['day']==day),'producercomparison mismatch')
   records.append(rec);diagnostics.append({'instrument':code,'day':day,'aggregate_OHLC':diag,'noncent_original_price_cells':nonc});noncent+=nonc
   if sample is None:sample=(code,day,selected,copy.deepcopy(daily[day]),rec)
 require(rowcount==6989 and rowcount==29*241 and len(records)==29 and len(summary['session_comparisons'])==29,'row/sessiontotal mismatch')
 require(summary['status']=='HF_ARCHIVE_SOURCE_PROBE_COMPLETE' and summary['request_sha256']==EXPECTED and summary['logical_requests_reserved']==3 and summary['source_failures']==[] and summary['terminal_error'] is None and summary['all_bound_inputs_unchanged'] is True,'terminalsummary mismatch')
 require(summary['dataset']==plan['dataset'] and summary['revision']==plan['revision'] and type(summary['new_alpha_candidates']) is int and summary['new_alpha_candidates']==0,'summary sourceidentity/scope mismatch')
 for k in ['admitted_for_reconstructed_execution','historical_arrival_verified','portfolio_returns_computed','objective_achieved','later_year_quote_rows_exposed_by_filtered_reader','source_intervals_shifted_or_prices_rounded','prior_rejected_sources_modified']:require(summary[k] is False,'falseboundary upgraded')
 neg={};code,day,rows,daily,rec=sample
 try:reconstruct(code,day,[],daily)
 except ValueError:neg['missing_requested_date']=True
 else:raise ValueError('missingdate controlaccepted')
 changed=copy.deepcopy(daily);changed['volume']=str(D(daily['volume'])+1)
 result,_,_=reconstruct(code,day,rows,changed);require(result!=rec and result['source_checks']['total_volume_matches'] is False,'rawvolume controlaccepted');neg['raw_daily_volume_changed']=True
 changed=copy.deepcopy(rows);changed[0]['timestamp']+=timedelta(seconds=1)
 try:reconstruct(code,day,changed,daily)
 except ValueError:neg['minute_label_changed']=True
 else:raise ValueError('clockcontrolaccepted')
 code=next(iter(plan['objects']));wrong=copy.deepcopy(plan['objects'][code]);wrong['oid']='0'*64
 try:verify_object(out/(code+'.parquet'),wrong)
 except ValueError:neg['object_oid_changed']=True
 else:raise ValueError('OIDcontrolaccepted')
 counts={k:sum(x['source_checks'][k] for x in records) for k in records[0]['source_checks']}
 binary32={k:sum(x['aggregate_OHLC'][k]['daily_decimal_reencoded_IEEE754_binary32_then_binary64_exactly_matches_archive'] for x in diagnostics) for k in ['open','high','low','close']}
 for f,h in known.items():require(sha(f)==h,'inputchanged duringaudit')
 artifact_hashes={p.name:sha(p) for p in out.iterdir() if p.is_file()}
 report={'status':'INDEPENDENT_29_PRE2026_ARCHIVE_SOURCE_COMPARISONS_RECONSTRUCTED','freeze_commit':FREEZE,'request_sha256':EXPECTED,'summary_sha256':sha(out/'summary.json'),'audit_code_sha256':sha(__file__),'method_sha256':plan['method_code_sha256'],'all16bound_inputs_rehashed_unchanged':True,'request_and_methods_match_frozen_Git_blobs':True,'exact_old29exceptions_verified':True,'LFS_pointers_objects_and_reservations_verified':object_checks,'logical_request_reservations':3,'selected_pre2026_rows_reconstructed':rowcount,'all29_summary_comparisons_exactly_reconstructed':True,'per_field_pass_counts_out_of29':counts,'aggregate_OHLC_binary32_reference_encoding_pass_counts_out_of29':binary32,'binary32_diagnostic_method':'Encode only the original daily reference Decimal as IEEE754binary32 via struct.pack/unpack, expand to Pythonbinary64, compare original archive float text exactly; archive values are never rounded, shifted or rewritten. Matching is representation compatibility, not upstream-provider truth or admission.','original_noncent_OHLC_cells_out_of27956':noncent,'source_quality_conclusion':'All29 requested sessions contain241 original labels including09:30 and therefore fail the existing240end-label contract. Exact source checks and their failures are preserved. Binary32 compatibility is a separate diagnostic and does not turn any failed exact-cent/OHLC check into admission.','per_session_exact_differences':diagnostics,'negative_controls_rejected':neg,'all_source_artifact_sha256':artifact_hashes,'critical_or_important_audit_discrepancies':[],'source_admission':False,'admitted_for_reconstructed_execution':False,'historical_arrival_verified':False,'portfolio_returns_computed':False,'network_queries':0,'project_code_imported':False,'2026_quote_rows_materialized_to_Python':False,'private_signed_URLs_or_headers_disclosed':False,'limitations':['Whole immutable object hashing includes allbytes; Arrow may internally decode mixed-year rowgroups. Only explicitly filtered29pre2026 sessions were materialized or compared. NoOS isolation claimed.','Reservation/body/objectbytes prove local identities and logicalrequestbudget, not an independent HTTPwiretrace, actual server transportcount, historical arrival or upstream source truth. SignedURLs/headers are not emitted; private response hashlocallybound only.','The original241rows/09:30 label, floatprecision, and all exact source comparison failures remainunchanged; no rounding, source rewrite, labeldropping, queue/impact certification or account replay.']}
 pathlib.Path(a.output).write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'output':a.output,'report_sha256':sha(a.output),'rows':rowcount,'source_checks_pass_counts':counts,'binary32_reference_encoding_pass_counts':binary32,'admitted':False},sort_keys=True))
if __name__=='__main__':main()
