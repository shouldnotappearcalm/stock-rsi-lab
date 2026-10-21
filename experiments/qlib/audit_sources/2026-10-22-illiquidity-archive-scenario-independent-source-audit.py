"""Independent stdlib-only source audit. No project imports, Parquet decoding,
network, account replay, investment ranking or portfolio return calculation.
Run --self-test alone for synthetic controls without reading real sources.
"""
import argparse,copy,hashlib,json,math,re,struct,sys,tempfile
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
LOCAL=timezone(timedelta(hours=8));UTC=timezone.utc
CONTRACT='BINARY32_UNIQUE_CENT_CLOCK_INTERSECTION_V1'
RAW='illiquidity-raw-source-continuation-20261020';PROOF='illiquidity-corporate-reviewed-20261020';EVENTS='illiquidity-source-events-20261020';TARGET='illiquidity-development-targets-20261020.json'
OLD='tdx-fixed-order-history-20261017';EXTRA='illiquidity-minutes-dev-20261021';ARCHIVE='illiquidity-hf-archive-probe-20261021';GRID='illiquidity-archive-cent-grid-primary-20261022'
DETAIL='illiquidity-minute-admission-20261021-v2/details.json';PUBLIC='experiments/qlib/'
MINREQ=PUBLIC+'illiquidity-minute-development-request.json';ADMISSION=PUBLIC+'illiquidity-development-minute-admission.json';VERIFY=PUBLIC+'illiquidity-hf-archive-probe-run-verification.json'
PUBLIC_FILES=(MINREQ,ADMISSION,VERIFY,*[PUBLIC+n for n in ('illiquidity-minute-development-capture-plan.json','illiquidity-minute-development-capture-manifest.json','illiquidity-raw-source-capture-manifest.json','illiquidity-corporate-reviewed-manifest.json','illiquidity-corporate-capture-manifest.json','illiquidity-source-event-compilation.json','illiquidity-hf-archive-probe-request.json','illiquidity-hf-archive-probe-independent-audit.json','illiquidity-hf-archive-probe-results.json','illiquidity-hf-archive-probe-final-review.json','illiquidity-hf-archive-metadata-discovery.json','illiquidity-archive-cent-clock-code-review.json','illiquidity-archive-cent-grid-primary-research.json','illiquidity-archive-scenario-builder-code-review.json')])
METHODS=set('''scripts/prepare_illiquidity_account_events.py
src/stock_rsi/distribution_event_compiler.py
src/stock_rsi/lifecycle_source_rows.py
src/stock_rsi/stock_distribution_account.py
scripts/run_low_risk_raw_share_validation.py
scripts/capture_frozen_target_development_data.py
src/stock_rsi/raw_share_account.py
src/stock_rsi/calendar.py
src/stock_rsi/broker.py
src/stock_rsi/data.py
src/stock_rsi/time.py
scripts/run_low_risk_intraday_replay.py
scripts/capture_cninfo_csi500_reports_pre2026.py
scripts/capture_low_risk_raw_account_data.py
scripts/tdx_history_checks.py
src/stock_rsi/intraday_broker.py
src/stock_rsi/intraday_tape.py
src/stock_rsi/execution_cost.py
src/stock_rsi/models.py
scripts/admit_illiquidity_minutes_pre2026.py
scripts/illiquidity_minute_sources.py
scripts/fundamental_query_journal.py
scripts/prepare_qlib_master_market_pre2026.py
scripts/build_illiquidity_archive_scenario_sources.py
src/stock_rsi/archive_cent_clock.py
src/stock_rsi/archive_minute_probe.py'''.splitlines())

def need(v,label):
 if not v:raise AssertionError(label)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def utc(t):
 need(t.tzinfo is not None and t.utcoffset() is not None,'aware window clock');return t.astimezone(UTC).isoformat()
def labels():
 return [f'{h:02}:{m:02}' for h in (9,10,11,13,14,15) for m in range(60) if '09:31'<=f'{h:02}:{m:02}'<='11:30' or '13:01'<=f'{h:02}:{m:02}'<='15:00']
def bits_fraction(bits):
 """Exact positive binary32 rational from integer exponent/significand."""
 exp=(bits>>23)&255;mant=bits&0x7fffff
 need(bits<0x7f800000,'finite nonnegative binary32 bit pattern')
 power=(exp-150) if exp else -149;significand=(mant+(1<<23)) if exp else mant
 return F(significand*(1<<power),1) if power>=0 else F(significand,1<<(-power))
def inverse_cent(v):
 need(type(v) is float and math.isfinite(v) and v>=0,'finite published binary32 promotion')
 try:encoded=struct.pack('>f',v)
 except (OverflowError,struct.error):raise AssertionError('unsupported binary32 magnitude')
 n=int.from_bytes(encoded,'big');need(n<0x7f7fffff and struct.unpack('>f',encoded)[0]==v,'exact unsigned finite binary32 promotion')
 if n==0:return D('0.00')
 value=bits_fraction(n);low=(bits_fraction(n-1)+value)*50;high=(value+bits_fraction(n+1))*50
 first=-(-low.numerator//low.denominator);last=high.numerator//high.denominator
 need(last-first<=2,'nonunique cent inverse interval')
 candidates=[k for k in range(first,last+1) if low<k<high or n%2==0 and (k==low or k==high)]
 need(len(candidates)==1,'exactly one cent inverse; no rounding fallback')
 p=D(candidates[0]).scaleb(-2);need(struct.pack('>f',float(p))==encoded,'bit-exact cent inverse roundtrip');return p

def original_comparison(code,day,rows,daily):
 need(code in ('SH603056','SZ002505') and '2024-01-01'<=day<='2025-12-31','fixed two issuer pre2026 archive scope')
 need(daily['date']==day and daily['tradestatus']=='1' and rows,'bound active original daily source')
 labs=[];values=[];volumes=[]
 for row in rows:
  need(set(row)=={'symbol','exchange','timestamp','open','high','low','close','volume','turnover'} and row['symbol']==code[2:] and row['exchange']==code[:2],'original archive fields/issuer identity')
  t=datetime.fromisoformat(row['timestamp']);need(t.tzinfo is None and t.date().isoformat()==day and t.second==t.microsecond==0,'original naive exchange minute clock')
  lab=t.strftime('%H:%M');need('09:30'<=lab<='11:30' or '13:00'<=lab<='15:00','original source session boundary');labs.append(lab)
  p={k:D(str(row[k])) for k in ('open','high','low','close')};need(all(x.is_finite() and x>=0 for x in p.values()),'original finite nonnegative prices');need(p['low']<=min(p['open'],p['close'])<=max(p['open'],p['close'])<=p['high'],'original OHLC ordering')
  v=row['volume'];need(type(v) is int and v>=0 and (not v or min(p.values())>0),'original share volume and positive traded price');turn=D(str(row['turnover']));need(turn.is_finite() and turn>=0,'original finite turnover');values.append(p);volumes.append(v)
 need(labs==sorted(set(labs)),'unique sorted original minute labels')
 checks={'exact_existing_240_end_labels':labs==labels(),'all_prices_exact_cent_without_rounding':all(v==v.quantize(D('.01')) for p in values for v in p.values()),'first_open_matches':values[0]['open']==D(daily['open']),'highest_matches':max(p['high'] for p in values)==D(daily['high']),'lowest_matches':min(p['low'] for p in values)==D(daily['low']),'last_close_matches':values[-1]['close']==D(daily['close']),'total_volume_matches':sum(volumes)==D(daily['volume'])}
 return {'instrument':code,'day':day,'rows':len(rows),'first_label':labs[0],'last_label':labs[-1],'labels':labs,'source_checks':checks,'archive_total_volume_shares':sum(volumes),'daily_volume_shares':daily['volume'],'all_numeric_and_existing_label_checks_pass':all(checks.values()),'upstream_providers_independently_authenticated':False,'minute_interval_semantics_authenticated':False,'admitted_for_reconstructed_execution':False}

def archive_projection(code,day,rows,daily):
 comparison=original_comparison(code,day,rows,daily);need(comparison['labels']==['09:30']+labels() and comparison['source_checks']['total_volume_matches'],'all241 labels and exact whole-day shares')
 decoded=[];lookup={}
 for row in rows:
  prices={k:inverse_cent(row[k]) for k in ('open','high','low','close')};need(prices['low']<=min(prices['open'],prices['close'])<=max(prices['open'],prices['close'])<=prices['high'],'cent-decoded OHLC ordering')
  item={'timestamp':datetime.fromisoformat(row['timestamp']).isoformat(),'raw_price_binary32_bits':{k:struct.pack('>f',row[k]).hex() for k in prices},'decoded_cent_prices':{k:str(v) for k,v in prices.items()},'volume_shares':row['volume']};decoded.append(item);lookup[row['timestamp'][11:16]]=(row,prices,item)
 actual={'open':D(decoded[0]['decoded_cent_prices']['open']),'high':max(D(r['decoded_cent_prices']['high']) for r in decoded),'low':min(D(r['decoded_cent_prices']['low']) for r in decoded),'close':D(decoded[-1]['decoded_cent_prices']['close'])}
 need(all(v==D(daily[k]) for k,v in actual.items()),'decoded whole-day OHLC exact original source')
 windows=[];used=set()
 for endlabel in [s for s in labels() if int(s[-2:])%5==0]:
  end=datetime.fromisoformat(day+'T'+endlabel).replace(tzinfo=LOCAL);start=end-timedelta(minutes=5);selected=[start+timedelta(minutes=i) for i in (1,2,3,4)];names=[t.strftime('%H:%M') for t in selected]
  need(not used.intersection(names),'no double-use of source volume');used.update(names);block=[lookup[n] for n in names]
  for t in selected:need(start<=t-timedelta(minutes=1) and t+timedelta(minutes=1)<=end,'both START/END interval hypotheses wholly contained and complete by bucket end')
  traded=[p for r,p,_ in block if r['volume']>0];evidence={'contract':CONTRACT,'security_id':code,'day':day,'start':utc(start),'end':utc(end),'selected_rows':[item for _,_,item in block]}
  windows.append({'security_id':code,'start':utc(start),'end':utc(end),'available_at':utc(end),'volume_lower_shares':sum(r['volume'] for r,_,_ in block),'buy_price':str(max(p['high'] for p in traded)) if traded else None,'sell_price':str(min(p['low'] for p in traded)) if traded else None,'evidence_id':digest(evidence)})
 excluded=[{'timestamp':r['timestamp'],'volume_shares':r['volume_shares'],'reason':'BOUNDARY_OR_OPENING_LABEL_NOT_USED_FOR_EXECUTION'} for r in decoded if r['timestamp'][11:16] not in used];total=sum(r['volume'] for r in rows);safe=sum(w['volume_lower_shares'] for w in windows)
 need((len(decoded),len(windows),len(used),len(excluded))==(241,48,192,49) and safe+sum(r['volume_shares'] for r in excluded)==total,'complete partition and conserved original volume')
 return {'contract':CONTRACT,'instrument':code,'day':day,'windows':windows,'decoded_price_audit':decoded,'unused_for_execution':excluded,'original_source_comparison':comparison,'whole_day_volume_shares':total,'safe_window_volume_shares':safe,'conditional_clock_hypotheses':['LABEL_IS_INTERVAL_START','LABEL_IS_INTERVAL_END'],'price_grid_and_binary32_encoding_are_explicit_premises':True,'source_rows_rewritten_or_discarded':False,'original_source_admission_overridden':False,'authenticated_provider_or_interval_semantics':False,'historical_arrival_verified':False,'admitted_for_original_reconstructed_execution':False}

def tdx_windows(code,day,packet,daily):
 need(packet['instrument']==code and packet['requested_day']==day,'TDX original packet identity');record=packet.get('methods',{}).get('minutes.history',packet);need(record['status']=='RESPONSE_CAPTURED','old approved source response')
 payload=record['response'];need(payload['exchange']==code[:2].lower() and type(payload['market_id']) is int and payload['market_id']==(1 if code[:2]=='SH' else 0) and payload['code']==code[2:] and payload['trading_date']==day,'TDX decoded request identity');points=payload['points'];need(len(points)==240,'unchanged240 gate')
 for i,(p,lab) in enumerate(zip(points,labels())):
  need(type(p['index']) is int and p['index']==i and p['time_label']==lab and p['time']==day+'T'+lab+':00+08:00','TDX full source labels/index/aware clock')
  price,v=p['price_milli'],p['volume'];need(type(price) is type(v) is int and price>=0 and v>=0 and type(p['price']) is not bool and D(str(p['price'])).is_finite() and D(str(p['price']))==D(price)/1000,'TDX exact integer raw price/hand volume')
  need(not v or price>0 and price%10==0 and D(daily['low'])<=D(price)/1000<=D(daily['high']),'TDX traded cent price and unchanged daily range')
 need(daily['tradestatus']=='1' and D(points[-1]['price_milli'])/1000==D(daily['close']),'TDX original last close signature')
 windows=[]
 for i in range(0,240,5):
  block=points[i:i+5];end=datetime.fromisoformat(block[-1]['time']);start=end-timedelta(minutes=5);prices=[D(p['price_milli'])/1000 for p in block if p['volume']>0];evidence={'security_id':code,'day':day,'points':[{k:p[k] for k in ('time','volume','price_milli')} for p in block]}
  windows.append({'security_id':code,'start':utc(start),'end':utc(end),'available_at':utc(end),'volume_lower_shares':sum(max(0,p['volume']*100-100) for p in block),'buy_price':str(max(prices)) if prices else None,'sell_price':str(min(prices)) if prices else None,'evidence_id':digest(evidence)})
 need(sum(w['volume_lower_shares'] for w in windows)<=D(daily['volume']),'TDX stressed capacity no more than original whole-day shares');return windows

def verify_sha(path,expected):need(sha(path)==expected,'actual source SHA256 differs from frozen binding')
def negative(fn):
 try:fn()
 except (AssertionError,ValueError,KeyError,OverflowError):return True
 raise AssertionError('synthetic negative accepted')
def synthetic_controls():
 day='2024-01-02';code='SH603056';f32=lambda x:struct.unpack('>f',struct.pack('>f',x))[0]
 rows=[{'symbol':'603056','exchange':'SH','timestamp':day+'T'+lab+':00','open':f32(10.01),'high':f32(10.03),'low':f32(9.99),'close':f32(10.02),'volume':1000,'turnover':10000.} for lab in ['09:30']+labels()];daily={'date':day,'tradestatus':'1','open':'10.01','high':'10.03','low':'9.99','close':'10.02','volume':'241000'};projection=archive_projection(code,day,rows,daily)
 changed=copy.deepcopy(projection);changed['windows'][0]['volume_lower_shares']+=1
 controls={'missing_label_rejected':negative(lambda:archive_projection(code,day,rows[1:],daily)),'nonunique_binary32_cent_preimage_rejected':negative(lambda:inverse_cent(f32(500000.))),'changed_projection_rejected':negative(lambda:need(changed==archive_projection(code,day,rows,daily),'synthetic projection tamper'))}
 with tempfile.TemporaryDirectory(prefix='archive-audit-synthetic-') as td:
  p=Path(td)/'source';p.write_bytes(b'original synthetic source');h=sha(p);p.write_bytes(b'changed synthetic source');controls['changed_source_SHA_rejected']=negative(lambda:verify_sha(p,h))
 need(all(controls.values()) and len(projection['windows'])==48,'all synthetic controls');return controls

# Reconstruct input identity set independently from the frozen source metadata.
def required_inputs(base,repo):
 paths={}
 def add(path):
  p=Path(path).resolve()
  if p.is_relative_to(repo):key='repo/'+str(p.relative_to(repo))
  else:need(p.is_relative_to(base),'registered input escapes frozen roots');key='source/'+str(p.relative_to(base))
  paths[key]=p
 for name in set(PUBLIC_FILES)|METHODS:add(repo/name)
 for folder,name in [(RAW,'manifest.json'),(PROOF,'reviewed-manifest.json'),(EVENTS,'summary.json'),(OLD,'manifest.json'),(EXTRA,'manifest.json')]:add(base/folder/name)
 for name in [TARGET,DETAIL,RAW+'/calendar.json',PROOF+'/capture-manifest.json',OLD+'/plan.json',EXTRA+'/plan.json',GRID+'/manifest.json']:add(base/name)
 for code in read(base/RAW/'manifest.json')['per_code_sha256']:
  need(re.fullmatch(r'(SH|SZ)[0-9]{6}',code) is not None,'safe original source issuer');add(base/RAW/'codes'/(code+'.json'))
 for doc in read(base/PROOF/'reviewed-manifest.json')['documents']:need(Path(doc['file']).name==doc['file'],'safe primary filename');add(base/PROOF/doc['file'])
 for name in read(base/EVENTS/'summary.json')['artifact_sha256']:need(Path(name).name==name,'safe event artifact filename');add(base/EVENTS/name)
 index={}
 for folder in (OLD,EXTRA):
  for name in read(base/folder/'manifest.json')['per_session_sha256']:
   need(Path(name).name==name and name.endswith('.json') and name not in index,'safe unique original tape filename');index[name]=base/folder/'sessions'/name
 for code,day in read(repo/MINREQ)['active_requests']:
  need('2024-01-01'<=day<='2025-12-31','pre2026 tape scope');add(index[code+'-'+day+'.json'])
 for name in read(repo/VERIFY)['all13_local_output_file_sha256']:need(Path(name).name==name,'safe archive output filename');add(base/ARCHIVE/name)
 for path in read(base/ARCHIVE/'input-before.json'):add(path)
 for path in (base/GRID).iterdir():
  if path.is_file():add(path)
 return paths

def scope_from_targets(targets,bars,lifecycles):
 active=[];skipped=[];seen=set()
 for day,target in sorted(targets.items()):
  need('2024-01-02'<=day<='2025-12-31' and target['as_of']<day,'fixed pre2026 target clock');seen.update(target['weights']);need(seen<=set(bars),'complete source universe')
  for code in sorted(seen):
   boundary=lifecycles.get(code,{});row=bars[code].get(day);kind=boundary.get('kind');outside=(kind=='LISTING_BEGIN' and day<boundary['effective_date']) or (kind=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    need(code not in target['weights'],'current target cannot use outside lifecycle source');need(boundary['verified_primary_boundary'] is True and re.fullmatch('[0-9a-f]{64}',boundary['primary_document_sha256']) is not None,'authenticated original lifecycle proof')
    if kind=='LISTING_BEGIN':need(row is None,'no source row before original listing boundary')
    reason='BEFORE_PRIMARY_LISTING_BOUNDARY' if kind=='LISTING_BEGIN' else 'AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY'
    skipped.append({'instrument':code,'day':day,'reason':reason,'primary_document_sha256':boundary['primary_document_sha256'],'actual_inventory_proven_zero':False,'synthetic_price_created':False})
   else:
    need(row is not None and row['date']==day,'unexplained source missing day')
    if row['tradestatus']=='0':skipped.append({'instrument':code,'day':day,'reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False})
    else:need(row['tradestatus']=='1','known raw source status');active.append([code,day])
 return active,skipped

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('repo-root','source-root','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+name,required=True)
 a=p.parse_args();repo,base,run,out=map(lambda x:Path(x).resolve(),(a.repo_root,a.source_root,a.run_dir,a.output));request_path=Path(a.request).resolve();need(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo) and not out.is_relative_to(run),'new external audit report only')
 controls=synthetic_controls();verify_sha(request_path,a.expected_request_sha256);request=read(request_path)
 need(request['status']=='FROZEN_BEFORE_ARCHIVE_SCENARIO_SOURCE_INTERPRETATION' and request['contract']==CONTRACT and request['portfolio_returns_permitted'] is False and request['end']=='2025-12-31','source-only externally frozen contract')
 need(set(request['method_code_sha256'])==METHODS,'exact mandatory method set')
 paths=required_inputs(base,repo);need(set(paths)==set(request['input_sha256']),'complete frozen input set independently enumerated');expected={**request['input_sha256'],'frozen_request':a.expected_request_sha256};paths['frozen_request']=request_path
 for name,path in paths.items():verify_sha(path,expected[name])
 for name,h in request['method_code_sha256'].items():need(request['input_sha256']['repo/'+name]==h,'method SHA in complete input map');verify_sha(repo/name,h)
 outputs_before={str(f.relative_to(run)):sha(f) for f in sorted(run.rglob('*')) if f.is_file()};summary=read(run/'summary.json');details=read(run/'details.json');terminal=read(run/'terminal.json');post=read(run/'input-postcheck.json');need(read(run/'input-before.json')==expected,'actual source input-before complete exact map')
 need(post=={'all_inputs_unchanged':True,'count':len(paths),'request_rehashed_after_processing':True,'mismatches':[]},'successful exhaustive input and request postcheck')
 need(terminal['status']=='SOURCE_SCENARIO_BUILD_TERMINAL' and terminal['interpretation_completed'] is True and terminal['original_error'] is None and terminal['postcheck']==post and terminal['partial_sessions']==2276 and terminal['portfolio_returns_computed'] is False and not terminal.get('persistence_errors',[]),'complete source terminal no hidden exception or persistence error')
 need(summary['request_sha256']==a.expected_request_sha256 and summary['method_code_sha256']==request['method_code_sha256'] and summary['details_sha256']==sha(run/'details.json') and summary['input_count']==len(paths),'summary/request/method/detail exact binding')
 oldad=read(repo/ADMISSION);prior=read(base/DETAIL);need(oldad['admitted_for_reconstructed_execution'] is False and oldad['status_counts']=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':2247,'SOURCE_REJECTED':29} and oldad['local_detail_sha256']==sha(base/DETAIL),'old false admission and details never overridden')
 rm=read(base/RAW/'manifest.json');proof=read(base/PROOF/'reviewed-manifest.json');calendar=read(base/RAW/'calendar.json')['sessions'];need(len(calendar)==486 and calendar[0]=='2023-12-29' and calendar[-1]=='2025-12-31' and calendar==sorted(set(calendar)),'original486 explicit pre2026 calendar');verify_sha(base/RAW/'calendar.json',rm['calendar_sha256']);verify_sha(base/TARGET,rm['target_sha256']);need(proof['target_sha256']==rm['target_sha256'],'primary target binding')
 bars={}
 for code,h in rm['per_code_sha256'].items():
  path=base/RAW/'codes'/(code+'.json');verify_sha(path,h);packet=read(path);need(packet['instrument']==code and packet['window']==['2023-12-29','2025-12-31'],'fixed original raw issuer/window');need(all(r['date']<='2025-12-31' for r in packet['bars']),'no future raw bar decoding admitted');bars[code]={r['date']:r for r in packet['bars']}
 active,skipped=scope_from_targets(read(base/TARGET),bars,proof['lifecycles']);oldreq=read(repo/MINREQ);need(len(active)==2276 and len(skipped)==18 and active==oldreq['active_requests'] and skipped==oldreq['nonexecuting_source_intervals'],'all2276 active/18 nonexecuting keys independently reconstructed')
 need([(r['instrument'],r['day']) for r in prior['sessions']]==[tuple(k) for k in active] and prior['nonexecuting_source_intervals']==skipped,'original admission complete order and nonexecuting scope');rejected={(r['instrument'],r['day']) for r in prior['sessions'] if r['status']=='SOURCE_REJECTED'};need(sorted(map(list,rejected))==request['archive_pairs'] and len(rejected)==29,'exact original29 rejected keys only')
 need(details['nonexecuting_source_intervals']==skipped and len(details['sessions'])==2276,'new details complete original scope')
 indexed={}
 for folder in (OLD,EXTRA):
  manifest=read(base/folder/'manifest.json');verify_sha(base/folder/'plan.json',manifest['plan_sha256'])
  for name,h in manifest['per_session_sha256'].items():
   key=tuple(name[:-5].split('-',1));need(key not in indexed,'no duplicate original tape source');indexed[key]=(base/folder/'sessions'/name,h)
 verification=read(repo/VERIFY)
 for name,h in verification['all13_local_output_file_sha256'].items():verify_sha(base/ARCHIVE/name,h)
 for path,h in read(base/ARCHIVE/'input-before.json').items():verify_sha(path,h)
 groups=defaultdict(list)
 for code in sorted({k[0] for k in rejected}):
  for row in read(base/ARCHIVE/(code+'-selected-development-rows.json')):
   t=datetime.fromisoformat(row['timestamp']);key=(code,t.date().isoformat());need(key in rejected,'selected JSON contains only explicit original29 pre2026 pairs');groups[key].append(row)
 need(set(groups)==rejected and sum(map(len,groups.values()))==6989,'all6989 selected original rows retained')
 expected_rows=[];projections={};tdx_count=0
 for priorrow,(code,day),actual in zip(prior['sessions'],active,details['sessions']):
  key=(code,day);path,h=indexed[key];verify_sha(path,h);need(h==priorrow['source_sha256'],'original per-session provenance SHA');packet=read(path);need(packet['instrument']==code and packet['requested_day']==day,'original packet issuer/day unchanged')
  row={'instrument':code,'day':day,'original_status':priorrow['status'],'original_source_sha256':h}
  if key in rejected:
   # Saved original response rejection is preserved; exact error text is immutable prior evidence.
   need(actual.get('original_error_preserved')==priorrow['error'],'old exact rejected source error retained')
   row['original_error_preserved']=priorrow['error'];projection=archive_projection(code,day,groups[key],bars[code][day]);name=code+'-'+day+'.json';need(read(run/name)==projection,'complete archive projection including comparison/decoded prices/bits/rows/exclusions/windows/digests');windows=projection['windows'];projections[name]=sha(run/name)
   row.update(source_kind='CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION',projection_file=name,projection_sha256=sha(run/name),selected_row_count=192,excluded_preserved_row_count=49,whole_day_volume_shares=projection['whole_day_volume_shares'],safe_window_volume_shares=projection['safe_window_volume_shares'])
  else:
   need(priorrow['status']=='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE','only original approved TDX route');windows=tdx_windows(code,day,packet,bars[code][day]);tdx_count+=1;row['source_kind']='UNCHANGED_ORIGINAL_TDX'
  row.update(status='SOURCE_SCENARIO_COMPLETE',windows=48,window_digest=digest(windows));need(row==actual,'full new details row and window digest independently reconstructed');expected_rows.append(row)
 need(tdx_count==2247 and len(projections)==29 and details=={'sessions':expected_rows,'nonexecuting_source_intervals':skipped},'all complete details exact content and scope')
 need(set(outputs_before)==set(projections)|{'summary.json','details.json','input-before.json','input-postcheck.json','terminal.json'},'exact34 new source output files no extra/missing artifact')
 expected_summary={'status':'ILLIQUIDITY_CONDITIONAL_SOURCE_SCENARIO_BUILT','contract':CONTRACT,'request_sha256':a.expected_request_sha256,'method_code_sha256':request['method_code_sha256'],'required_active_sessions':2276,'nonexecuting_source_intervals':18,'original_TDX_sessions':2247,'conditional_archive_sessions':29,'status_counts':{'SOURCE_SCENARIO_COMPLETE':2276},'conditional_source_coverage_complete':True,'all_inputs_unchanged':True,'input_count':len(paths),'archive_original_rows':6989,'original_admission_overridden':False,'admitted_for_original_reconstructed_execution':False,'admitted_for_account_replay':False,'separate_account_freeze_required':True,'historical_arrival_verified':False,'authenticated_provider_or_interval_semantics':False,'cent_grid_and_binary32_promotion_are_assumptions':True,'SZSE_historical_cent_grid_certified':False,'OS_future_data_isolation_claimed':False,'2026_quote_values_decoded':False,'portfolio_returns_computed':False,'objective_achieved':False,'limitations':request['limitations'],'details_sha256':sha(run/'details.json')}
 need(summary==expected_summary,'entire new source summary counts/hash/flags exact reconstruction')
 for name,path in paths.items():verify_sha(path,expected[name])
 need(outputs_before=={str(f.relative_to(run)):sha(f) for f in sorted(run.rglob('*')) if f.is_file()},'all source outputs unchanged after independent audit')
 report={'status':'PASS_INDEPENDENT_ILLIQUIDITY_CONDITIONAL_ARCHIVE_SOURCE_AUDIT','audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),'details_sha256':sha(run/'details.json'),'terminal_sha256':sha(run/'terminal.json'),'input_postcheck_sha256':sha(run/'input-postcheck.json'),'complete_active_keyset_reconstructed':2276,'complete_nonexecuting_intervals_reconstructed':18,'original_TDX_240point_48windows_reconstructed':2247,'archive241row_48window_full_projections_reconstructed':29,'archive_original_rows_reconstructed':6989,'archive_selected_interior_rows_reconstructed':29*192,'archive_boundary_rows_preserved_and_excluded':29*49,'all_archive_original_comparison_fields_reconstructed':True,'all_window_prices_volumes_clocks_evidence_digests_reconstructed':True,'all_inputs_sha256':expected,'all_output_sha256':outputs_before,'semantic_negative_controls_rejected':controls,'imports_project_code':False,'stdlib_only':True,'Parquet_values_decoded':False,'private_batch_body_or_signed_actions_disclosed':False,'data_2026_read':False,'account_or_portfolio_ROI_computed':False,'network_or_SDK_called':False,'original_admission_still_false':True,'admitted_for_account_replay':False,'original_admission_overridden':False,'separate_account_freeze_required':True,'historical_arrival_verified':False,'authenticated_provider_or_interval_semantics':False,'SZSE_historical_cent_grid_certified':False,'OS_future_data_isolation_claimed':False,'objective_achieved':False,'critical_or_important_findings':[],'scope':'Independent full2276 source-key and window reconstruction, original2247 strict240 TDX routes plus29 conditional241-row archive projections, all raw binary32 bit patterns and unique-cent inverse, both interval hypotheses, 192interior/49excluded rows, daily OHLCV, original comparisons, all34output and complete frozen input SHA maps before/after. No project imports, account/scorer, Parquet decoder, private batch disclosure or network.','limitations':['Cent-grid and binary32-promotion premises are conditional engineering assumptions, not upstream provider or historical price certification.','The START/END label interpretation intersection is conservative under those two explicit hypotheses; it is not independently authenticated source interval semantics.','Whole immutable Parquet objects are hashed only. This auditor consumes only already-selected original pre2026 JSON rows and original pre2026 packets; original acquisition OS isolation is not certified.','This is source-only evidence and cannot establish actual inventory/entitlements/delisting exit, execution liquidity, queues/impact, tax liability, profitability or investment objective.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'output':str(out),'report_sha256':sha(out),'audit_code_sha256':sha(__file__)}))
if __name__=='__main__':
 if sys.argv[1:]==['--self-test']:print(json.dumps({'status':'SYNTHETIC_ONLY_PASS','semantic_negative_controls_rejected':synthetic_controls(),'imports_project_code':False}))
 else:main()
