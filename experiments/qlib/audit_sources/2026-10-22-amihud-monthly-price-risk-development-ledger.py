"""Independent stdlib-only Amihud monthly-price-risk source/account audit draft. No project imports, Parquet decoding,
network, account replay, investment ranking or portfolio return calculation.
Run --self-test alone for synthetic controls without reading real sources.
"""
import argparse,copy,csv,hashlib,io,json,math,re,struct,sys,tempfile
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


from decimal import ROUND_HALF_UP,ROUND_DOWN,ROUND_UP
from zoneinfo import ZoneInfo
def cents(value):return value.quantize(D(".01"),rounding=ROUND_HALF_UP)

def fee_for(gross,action,extra):return cents(max(D(5),gross*D('.0005' if action=='BUY' else '.0015')))+cents(gross*D(extra)/10000)

def audit_children(day,orders,parents,fills,p,extra,cash,*,tape,bars):
 pmap={r['order_id']:r for r in parents};groups=defaultdict(list)
 for child in orders:
  at=datetime.fromisoformat(child['submitted_at'])
  if at.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()==day:groups[at].append(child)
 fmap={r['order_id']:r for r in fills};assert len(fmap)==len(fills)
 seen=set()
 filled_by_parent=defaultdict(int)
 for at,children in sorted(groups.items()):
  assert len({c['security_id'] for c in children})==len(children),'duplicate security/window child'
  assert len({c['parent_id'] for c in children})==len(children),'duplicate parent/window child'
  reserved=D(0)
  for child in children:
   code=child['security_id'];parent=pmap[child['parent_id']];q=child['quantity'];end=datetime.fromisoformat(child['expires_at'])
   series=tape(code,day);indices=[i for i,w in enumerate(series) if w['start']==at and w['end']==end]
   assert len(indices)==1 and 1<=indices[0]<=46
   i=indices[0];prev,current=series[i-1],series[i];limit=D(child['limit_price']);buy=child['action']=='BUY'
   assert child['security_id']==parent['security_id'] and child['action']==parent['action']
   assert datetime.fromisoformat(parent['submitted_at'])<at and datetime.fromisoformat(parent['expires_at'])>=end
   assert datetime.fromisoformat(child['source_volume_as_of'])==prev['end']
   assert child['source_evidence_id']==prev['evidence'] and child['source_volume_lower_shares']==prev['volume']
   remaining=parent['quantity']-filled_by_parent[parent['order_id']]
   assert 0<q<=min(1000000,prev['volume']*p//10000,remaining)
   assert at.astimezone(ZoneInfo('Asia/Shanghai')).date()==datetime.fromisoformat(parent['eligible_at']).astimezone(ZoneInfo('Asia/Shanghai')).date()
   assert q%100==0 or not buy and q==remaining
   assert not buy or q%100==0
   source=bars[code][day];expected=(D(source['preclose'])*D('1.095' if buy else '.905')).quantize(D('.01'),rounding=ROUND_DOWN if buy else ROUND_UP)
   assert limit==expected
   reserve=limit*q+fee_for(limit*q,child['action'],extra) if buy else D(0)
   assert reserve==D(child['reserved_cash']);reserved+=reserve
   assert child['order_id']==digest({'parent':parent['order_id'],'start':at.isoformat(),'end':end.isoformat(),'quantity':q,'previous_volume':prev['volume'],'evidence_id':prev['evidence']})
   fill=fmap.get(child['order_id'])
   if fill is None:
    assert child['filled_quantity']==0 and child['status'].startswith('UNFILLED_');continue
   seen.add(child['order_id']);fq=fill['quantity'];price=D(fill['price'])
   assert fill['parent_id']==parent['order_id'] and fill['security_id']==code and fill['action']==child['action']
   assert 0<fq<=min(q,current['volume']*p//10000) and child['filled_quantity']==fq
   assert fq%100==0 or not buy and fq==remaining,'illegal odd-share partial fill'
   assert child['status']==('FILLED' if fq==q else 'PARTIAL_WINDOW_EXPIRED')
   assert datetime.fromisoformat(fill['execution_at'])==end
   assert fill['current_evidence_id']==current['evidence'] and fill['current_volume_lower_shares']==current['volume']
   assert price==current['buy' if buy else 'sell'] and (price<limit if buy else price>limit)
   assert not buy or price*fq+fee_for(price*fq,'BUY',extra)<=reserve
  assert reserved<=cash,(day,at,'same-window cash reuse')
  ordered_fills=[fmap[c['order_id']] for c in sorted(children,key=lambda x:(x['action']!='BUY',x['security_id'])) if c['order_id'] in fmap]
  for f in ordered_fills:
   filled_by_parent[f['parent_id']]+=f['quantity']
   assert filled_by_parent[f['parent_id']]<=pmap[f['parent_id']]['quantity']
   gross=D(f['price'])*f['quantity'];cost=fee_for(gross,f['action'],extra)
   cash+=(-gross-cost) if f['action']=='BUY' else gross-cost
   assert cash>=0 and cash==D(f['cash_after'])
 assert seen==set(fmap)

def authenticate_parents(parents,intents):
 expected={}
 for intent in intents:
  for decision in intent['decisions']:
   if decision['action'] not in ('BUY','SELL'):continue
   key=digest({'decision':decision,'snapshot':intent['snapshot_sha256']})
   assert key not in expected
   expected[key]=(intent,decision)
 assert len({p['order_id'] for p in parents})==len(parents)
 assert len({p['decision_id'] for p in parents})==len(parents)
 assert {p['decision_id'] for p in parents}==set(expected)
 for parent in parents:
  intent,decision=expected[parent['decision_id']]
  assert all(parent[k]==decision[k] for k in ('action','security_id','quantity'))
  assert parent['submitted_at']==intent['as_of']
  eligible=datetime.fromisoformat(parent['eligible_at']).astimezone(ZoneInfo('Asia/Shanghai'))
  expiry=datetime.fromisoformat(parent['expires_at']).astimezone(ZoneInfo('Asia/Shanghai'))
  assert eligible.date().isoformat()==intent['execution_session'] and eligible.strftime('%H:%M:%S')=='09:30:00'
  assert expiry.date()==eligible.date() and expiry.strftime('%H:%M:%S')=='14:55:00'
  assert type(parent['quantity']) is int and parent['quantity']>0
  assert type(parent['remaining']) is int and parent['remaining']>=0
  assert type(parent['filled_quantity']) is int and parent['filled_quantity']>=0
  assert parent['remaining']+parent['filled_quantity']==parent['quantity']

def independently_rebuild_events(packets,proofs):
 """Original source row/proof identities, no production event compiler."""
 order=[(code,r['dividOperateDate']) for code,p in sorted(packets.items()) for r in p['distributions']]+[(x['instrument'],x['record']['dividOperateDate']) for x in proofs['supplementary_distributions']]
 packets=copy.deepcopy(packets);origins={};docs={d['file']:d for d in proofs['documents']}
 for supplement in proofs['supplementary_distributions']:
  code=supplement['instrument'];r=copy.deepcopy(supplement['record']);doc=docs[supplement['source_file']]
  need(doc['sha256']==supplement['source_sha256'] and doc['instrument']==code and doc['day']==r['dividPlanDate'],'literal primary supplementary provenance')
  need(not any(x['dividOperateDate']==r['dividOperateDate'] for x in packets[code]['distributions']),'supplement cannot replace vendor event');packets[code]['distributions'].append(r);origins[(code,r['dividOperateDate'])]=doc['sha256']
 result={};dates=set()
 for code,p in packets.items():
  for r in p['distributions']:
   pair=(code,r['dividOperateDate']);need(pair not in dates,'unique issuer/ex source event');dates.add(pair);need(r['code']==code[:2].lower()+'.'+code[2:],'literal source issuer')
   cash,stock,capital=D(r['dividCashPsBeforeTax']),D(r['dividStocksPs']),D(r['dividReserveToStockPs'] or '0');need(min(cash,stock,capital)>=0,'nonnegative original distribution')
   proofkey=code+'|'+r['dividOperateDate'];tax=proofs['stock_dividend_tax_bases'].get(proofkey);exemption=proofs['capital_tax'].get(proofkey);primary=[];income=D(0)
   if pair in origins:primary.append(origins[pair])
   for proof in (tax,exemption):
    if proof is None:continue
    doc=docs[proof['source_file']];need(doc['sha256']==proof['source_sha256'] and doc['instrument']==code and doc['day']==r['dividPlanDate'],'unchanged original source proof identity');primary.append(doc['sha256'])
   if tax:need(tax['verified'] is True and stock==D(tax['expected_stock_per_original_share'])>0,'original stock tax proof');income=D(tax['taxable_income_per_original_share']);need(income>0,'positive stock tax income')
   if exemption:need(exemption['verified_exempt'] is True and capital>0,'original capital proof unchanged')
   if not r['dividReserveToStockPs']:
    display=r['dividCashStock'];need('转' not in display and (stock==0 and cash>0 and display.startswith('10派') and '送' not in display and not r['dividStockMarketDate'] or stock>0 and tax and display.startswith('10送')),'original missing-capital-field interpretation')
   identity={'instrument':code,'source_kind':'PRIMARY_NOTICE_SUPPLEMENT' if pair in origins else 'VENDOR_DISTRIBUTION','source_distribution':r,'primary_source_sha256':sorted(set(primary)),'effective_stock_taxable_income_per_original_share':str(income),'capital_tax_exempt_verified':exemption is not None,'stock_tax_basis_verified':tax is not None};eid=digest(identity)
   result[eid]={'code':code,'record':r['dividRegistDate'],'ex':r['dividOperateDate'],'pay':r['dividPayDate'],'list':r['dividStockMarketDate'],'cash':cash,'capital':capital,'stock':stock,'stock_income':income,'capital_verified':exemption is not None,'stock_verified':tax is not None}
 bypair={(e['code'],e['ex']):eid for eid,e in result.items()}
 return {bypair[pair]:result[bypair[pair]] for pair in order}

class IndependentScenarioSource:
 """Independent source functions only; every cached access rehashes backing bytes."""
 def __init__(self,base,repo,scenario_dir,source_audit,source_audit_sha):
  self.base,self.repo,self.run=map(Path,(base,repo,scenario_dir));verify_sha(source_audit,source_audit_sha);self.anchor=read(source_audit);need(self.anchor['status']=='PASS_INDEPENDENT_ILLIQUIDITY_CONDITIONAL_ARCHIVE_SOURCE_AUDIT' and self.anchor['imports_project_code'] is False and self.anchor['admitted_for_account_replay'] is False,'successful bounded independent source anchor')
  self.paths={k:(self.repo/k[5:] if k.startswith('repo/') else self.base/k[7:] if k.startswith('source/') else None) for k in self.anchor['all_inputs_sha256']}
  self.hashes={k:v for k,v in self.anchor['all_inputs_sha256'].items() if k!='frozen_request'};self.paths.pop('frozen_request',None)
  self.outputs=self.anchor['all_output_sha256'];self.recheck();self.proofs=read(self.base/PROOF/'reviewed-manifest.json');self.packets={};rm=read(self.base/RAW/'manifest.json')
  for code,h in rm['per_code_sha256'].items():
   path=self.base/RAW/'codes'/(code+'.json');verify_sha(path,h);packet=read(path);need(packet['window']==['2023-12-29','2025-12-31'] and all(r['date']<='2025-12-31' for r in packet['bars']),'pre2026 original source only');self.packets[code]=packet
  self.bars={c:{r['date']:r for r in p['bars']} for c,p in self.packets.items()};self.events=independently_rebuild_events(self.packets,self.proofs);need(len(self.events)==302,'all302 independent source events');self.sessions=read(self.base/RAW/'calendar.json')['sessions'];self.targets=read(self.base/TARGET);self.cache={};self.accessed=set();self.index={};self.archive={};self.archivefiles={};self.projectionfiles={}
  for folder in (OLD,EXTRA):
   for name,h in read(self.base/folder/'manifest.json')['per_session_sha256'].items():
    key=tuple(name[:-5].split('-',1));need(key not in self.index,'unique original tape key');self.index[key]=(self.base/folder/'sessions'/name,h)
  details=read(self.run/'details.json');self.kinds={(r['instrument'],r['day']):r['source_kind'] for r in details['sessions']}
  for code in sorted({c for (c,d),kind in self.kinds.items() if kind=='CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION'}):
   path=self.base/ARCHIVE/(code+'-selected-development-rows.json');h=self.hashes['source/'+str(path.relative_to(self.base))];verify_sha(path,h)
   for r in read(path):
    key=(code,r['timestamp'][:10]);need('2024-01-01'<=key[1]<='2025-12-31','pre2026 selected archive source only');self.archive.setdefault(key,[]).append(r);self.archivefiles[key]=(path,h)
  for key in self.archive:
   name=key[0]+'-'+key[1]+'.json';self.projectionfiles[key]=(self.run/name,self.outputs[name])
  self.expected_zero={k for k,e in self.events.items() if e['capital']>0 and not e['capital_verified'] or e['stock']>0 and not e['stock_verified']}
  derived=read(self.base/EVENTS/'derived_events.json');need(len(derived)==302 and {e['event_id'] for e in derived}==set(self.events),'all302 independently reconstructed event IDs match immutable source')
  for item in derived:
   e=self.events[item['event_id']];need(item['instrument']==e['code'] and item['recorded']==e['record'] and item['ex_date']==e['ex'] and item['pay_date']==(e['pay'] or None) and item['listed']==(e['list'] or None),'independent original event economic dates')
   need(tuple(D(item[k]) for k in ('cash_per_share','capital_per_share','stock_per_share','stock_taxable_income_per_share'))==(e['cash'],e['capital'],e['stock'],e['stock_income']) and item['capital_tax_exempt_verified']==e['capital_verified'] and item['stock_tax_basis_verified']==e['stock_verified'],'all original per-share economics and limited tax proof flags unchanged')
  receipts=read(self.base/EVENTS/'event_source_receipts.json');need(len(receipts)==302 and {r['event_id'] for r in receipts}==set(self.events) and {r['event_id'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']}==self.expected_zero,'complete302 source receipt and unknown-tax guard mapping')
 def recheck(self):
  for k,h in self.hashes.items():verify_sha(self.paths[k],h)
  need({str(f.relative_to(self.run)):sha(f) for f in sorted(self.run.rglob('*')) if f.is_file()}==self.outputs,'all34 independently audited scenario source output bytes')
 def tape(self,code,day):
  key=(code,day);need(key in self.kinds and day<='2025-12-31','fixed source scope/no future tape');self.accessed.add(key);path,h=self.index[key];verify_sha(path,h)
  if self.kinds[key]=='CONDITIONAL_ARCHIVE_CENT_CLOCK_INTERSECTION':
   src,sh=self.archivefiles[key];verify_sha(src,sh);projection,ph=self.projectionfiles[key];verify_sha(projection,ph)
   if key not in self.cache:
    expected=archive_projection(code,day,self.archive[key],self.bars[code][day]);need(read(projection)==expected,'whole independent archive projection identical');self.cache[key]=expected['windows']
  else:
   if key not in self.cache:self.cache[key]=tdx_windows(code,day,read(path),self.bars[code][day])
  return self.cache[key]

def failure_schema_requirements():
 return {'state':['cash','positions','owned_shares','parent_instructions','child_orders','fills','entitlements','corporate_ledger','cash_claims','stock_claims','last_account_clock'],'completed_prefix':['days','intents','ownership','lifecycle_source_audit'],'trace':['attempted_day','phase','last_completed_day','last_account_clock','tape_accessed_pairs','error_type','error'],'checkpoint_alternative':'Each completed session must carry day and full wealth fields plus broker fill/order/corporate counts; intent submissions must carry full original intentions/snapshot/decision records. Counts alone cannot reconstruct failure.','failed_day_partial_mutations':'Retain all actual corporate/fill/order changes after last completed day. Their existence must not be hidden by a prior-close checkpoint.','failure_metrics':'No annual return/average exposure/drawdown/ending metric for invalid cases.'}


def audit_tape(context,code,day):
 return [{'start':datetime.fromisoformat(w['start']),'end':datetime.fromisoformat(w['end']),'volume':w['volume_lower_shares'],'buy':D(w['buy_price']) if w['buy_price'] is not None else None,'sell':D(w['sell_price']) if w['sell_price'] is not None else None,'evidence':w['evidence_id']} for w in context.tape(code,day)]

def reconstruct_completed_prefix(data,context,participation,extra_bps,capital,*,allowed_unsubmitted_execution=None):
 rows=data['days'];intents=data['intents'];orders=data['orders'];parents=data['parent_instructions'];need(all(type(o['quantity']) is int and 0<o['quantity']<=1000000 for o in orders),'strict integer1m child quantity bound');bars=context.bars;events=context.events;sessions=context.sessions;targets=context.targets;PROOFS=context.proofs;expected_zero=context.expected_zero;case_id=f'{participation}/{extra_bps}/{capital}'
 assert [r['day'] for r in rows]==sessions[:len(rows)] and list(data['ownership'])==[r['day'] for r in rows],'continuous completed prefix'
 assert rows,'at least one completed checkpoint needed for this ledger path'
 complete={r['day'] for r in rows};expected_intent_count=sum(target['as_of'] in complete for target in targets.values())
 if allowed_unsubmitted_execution is not None:
  need(allowed_unsubmitted_execution in targets and targets[allowed_unsubmitted_execution]['as_of']==rows[-1]['day'] and allowed_unsubmitted_execution not in {i['execution_session'] for i in intents},'only final formation can lack an intent after exact old formation-status guard')
  expected_intent_count-=1
 assert all(f['execution_at'][:10] in complete for f in data['fills']) and all(e['day'] in complete for e in data['corporate_ledger']),'all rows in explicit consumed completed prefix'
 assert len({o['order_id'] for o in orders})==len(orders) and len({f['order_id'] for f in data['fills']})==len(data['fills']),'unique complete stream identities'
 authenticate_parents(parents,intents)
 tape=lambda code,day:audit_tape(context,code,day)
 previous_equity=D(capital)
 by_intent={datetime.fromisoformat(i['as_of']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat():i for i in intents}
 assert len(by_intent)==len(intents)==expected_intent_count
 fills=data['fills'];ledger=data['corporate_ledger'];ownership=data['ownership']
 need(all(x['kind'] in {'RECORD_DATE_OWNERSHIP','EX_DATE_ENTITLEMENT','NET_DIVIDEND_CASH_AVAILABLE','CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED'} for x in ledger),'all corporate kinds independently consumed')
 by_fill=defaultdict(list);by_ledger=defaultdict(list)
 for f in fills:by_fill[datetime.fromisoformat(f['execution_at']).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()].append(f)
 for item in ledger:by_ledger[item['day']].append(item)
 cash=D(capital);lots=defaultdict(list);marks={};claims={};stockclaims={};registered={};nav={};ex_seen=set();record_seen=set();max_capacity=D(0)
 exposure_sum=D(0);exposure_days=0;total_fees=D(0);total_extra_cost=D(0);total_gross_dividend=D(0);total_reserve=D(0);by_year_turnover=defaultdict(lambda:D(0));by_year_fees=defaultdict(lambda:D(0))
 for row in rows:
  day=row['day'];entries=by_ledger[day];day_fee=D(0);paid=D(0)
  # Independently derive each due payment and capital credit, then compare source events.
  expected_pay={key for key,(available,net) in claims.items() if available==day}
  actual_pay=[x for x in entries if x['kind']=='NET_DIVIDEND_CASH_AVAILABLE']
  assert {x['event_id'] for x in actual_pay}==expected_pay and len(actual_pay)==len(expected_pay)
  for item in actual_pay:
   key=item['event_id'];available,net=claims.pop(key);assert D(item['cash_delta'])==net
   cash+=net;paid+=net
  actual_ex=[x for x in entries if x['kind']=='EX_DATE_ENTITLEMENT']
  expected_ex={key for key,e in events.items() if e['ex']==day}
  assert {x['event_id'] for x in actual_ex}==expected_ex and len(actual_ex)==len(expected_ex)
  for item in actual_ex:
   key=item['event_id'];e=events[key];q=registered.get(key,0);gross=cents(e['cash']*q);stock_income=cents(e['stock_income']*q);reserve=cents((gross+stock_income)*D('.2'));bonus=e['capital']*q;stock_bonus=e['stock']*q
   assert bonus==int(bonus) and stock_bonus==int(stock_bonus) and item['registered_quantity']==q
   assert reserve<=gross
   if key in expected_zero:assert q==0
   assert D(item['cash_gross'])==gross and D(item['stress_tax_reserve'])==reserve and item['capital_shares']==int(bonus)
   assert item['stock_shares']==int(stock_bonus) and D(item['taxable_stock_income'])==stock_income
   if gross:claims[key]=(next((x for x in sessions if x>e['pay']),None),gross-reserve)
   if bonus+stock_bonus:stockclaims[key]=(e['code'],int(bonus+stock_bonus),e['list'],e['record'])
   total_gross_dividend+=gross;total_reserve+=reserve;ex_seen.add(key)
  expected_stock={key for key,(_,_,at,_) in stockclaims.items() if at<=day}
  actual_stock=[x for x in entries if x['kind'] in ('CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED')]
  assert {x['event_id'] for x in actual_stock}==expected_stock and len(actual_stock)==len(expected_stock)
  for item in actual_stock:
   code,q,at,record=stockclaims.pop(item['event_id']);assert item['quantity']==q
   e=events[item['event_id']];assert not (e['capital'] and e['stock']), 'mixed share kinds need separate independent claims'
   assert item['kind']==('STOCK_DIVIDEND_SHARES_LISTED' if e['stock'] else 'CAPITAL_SHARES_LISTED')
   lots[code].append([q,record,D(0)])
  audit_children(day,orders,parents,by_fill[day],participation,extra_bps,cash,tape=tape,bars=bars)
  for f in by_fill[day]:
   code=f['security_id'];q=f['quantity'];price=D(f['price']);source=bars[code][day]
   assert type(q) is int and q>0 and source['tradestatus']=='1' and source['isST']=='0'
   assert price==cents(price)
   gross=price*q;fee=cents(max(D('5'),gross*D('.0005' if f['action']=='BUY' else '.0015')))
   extra=cents(gross*D(extra_bps)/10000);fee+=extra;total_extra_cost+=extra
   assert fee==D(f['cost'])
   if f['action']=='BUY':
    assert q%100==0 and price<D(source['preclose'])*D('1.095');cash-=gross+fee;lots[code].append([q,day,price])
   else:
    assert f['action']=='SELL' and price>D(source['preclose'])*D('.905')
    assert sum(n for n,at,_ in lots[code] if at<day)>=q
    left=q
    for lot in lots[code]:
     if lot[1]>=day:continue
     take=min(left,lot[0]);lot[0]-=take;left-=take
    assert left==0;cash+=gross-fee
   assert cash>=0 and cash==D(f['cash_after'])
   day_fee+=fee;by_year_turnover[day[:4]]+=gross;by_year_fees[day[:4]]+=fee
   max_capacity=max(max_capacity,D(q)/D(source['volume']))
  quantities={code:sum(q for q,_,_ in ls) for code,ls in lots.items() if sum(q for q,_,_ in ls)}
  owned_for_record=dict(quantities)
  for code,q,_,_ in stockclaims.values():owned_for_record[code]=owned_for_record.get(code,0)+q
  assert quantities==ownership[day], 'published ownership records listed broker inventory'
  for code,boundary in PROOFS['lifecycles'].items():
   outside=(boundary['kind']=='LISTING_BEGIN' and day<boundary['effective_date'] or boundary['kind']=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    assert owned_for_record.get(code,0)==0
    assert not any(p['security_id']==code and p['eligible_at'][:10]<=day<=p['expires_at'][:10] for p in parents)
    if day in by_intent:assert code not in targets[by_intent[day]['execution_session']]['weights']
  actual_record=[x for x in entries if x['kind']=='RECORD_DATE_OWNERSHIP']
  expected_record={key for key,e in events.items() if e['record']==day}
  assert {x['event_id'] for x in actual_record}==expected_record and len(actual_record)==len(expected_record)
  for item in actual_record:
   e=events[item['event_id']];assert not any(c==e['code'] for c,_,_,_ in stockclaims.values())
   q=quantities.get(e['code'],0);assert item['quantity']==q
   registered[item['event_id']]=q;record_seen.add(item['event_id'])
  for code,byday in bars.items():
   boundary=PROOFS['lifecycles'].get(code,{})
   outside=(boundary.get('kind')=='LISTING_BEGIN' and day<boundary['effective_date'] or boundary.get('kind')=='DELISTING_END' and day>=boundary['effective_date'])
   if outside:
    marks.pop(code,None);continue
   source=byday[day];assert source['date']==day and source['tradestatus'] in ('0','1')
   if source['tradestatus']=='1':marks[code]=D(source['close'])
   elif any(e['code']==code and e['ex']==day for e in events.values()):marks[code]=D(source['preclose'])
   elif code not in marks and source['close'] and D(source['close'])>0:marks[code]=D(source['close'])
  market=sum((q*marks[code] for code,q in quantities.items()),D(0))
  pending=sum((q*marks[code] for code,q,_,_ in stockclaims.values()),D(0))
  receivable=sum((net for _,net in claims.values()),D(0));equity=cash+market+pending+receivable
  assert (cash,market,pending,receivable,equity,day_fee,paid)==tuple(D(row[k]) for k in ('cash','market_value','pending_stock_value','cash_receivable','equity','fees','net_dividend_cash_available')),(capital,day,'daily mismatch')
  if day>='2024-01-02':exposure_sum+=(market+pending)/equity;exposure_days+=1
  if day in by_intent:
   intent=by_intent[day];following=sessions[sessions.index(day)+1]
   assert intent['execution_session']==following and targets[following]['as_of']==day
   assert intent['equity_at_decision']==str(equity)
   owned=dict(quantities)
   for code,q,_,_ in stockclaims.values():owned[code]=owned.get(code,0)+q
   assert intent['owned_integer_shares']==owned
   expected_orders=[];weights=targets[following]['weights']
   for code in sorted(set(owned)|set(weights)):
    held=owned.get(code,0);weight=D(str(weights.get(code,0)))
    if weight==0:
     if held:expected_orders.append(('SELL',code,held))
     continue
    desired=int(equity*weight/marks[code]/100)*100
    if desired>held:
     quantity=(desired-held)//100*100
     if quantity:expected_orders.append(('BUY',code,quantity))
    elif held>desired:expected_orders.append(('SELL',code,held-desired))
   expected_orders.sort(key=lambda item:(item[0]!='SELL',item[1]))
   actual=[(d['action'],d['security_id'],d['quantity']) for d in intent['decisions']]
   assert actual==expected_orders,(case_id,day,'feedback order sizing mismatch')
  assert D(row['net_return'])==equity/previous_equity-1 and D(row['exposure'])==(market+pending)/equity,'daily return/exposure exact';previous_equity=equity;nav[day]=equity;total_fees+=day_fee

 assert ex_seen=={k for k,e in events.items() if e['ex'] in complete} and record_seen=={k for k,e in events.items() if e['record'] in complete},'all due source records/exes consumed'
 assert len(ledger)==sum(len(v) for v in by_ledger.values()) and sum(len(v) for v in by_fill.values())==len(fills),'no unconsumed stream rows'
 positions={c:[{'quantity':q,'bought_on':at,'price':str(price)} for q,at,price in ls if q] for c,ls in lots.items() if any(q for q,_,_ in ls)}
 return {'days':len(rows),'intents':len(intents),'parents':len(parents),'children':len(orders),'fills':len(fills),'corporate_rows':len(ledger),'cash':cash,'positions':positions,'circulating_shares':quantities,'owned_shares':owned_for_record,'marks':marks,'cash_claims_unpaid':claims,'stock_claims_uncredited':stockclaims,'entitlements':registered,'nav':nav,'exposure_sum':exposure_sum,'exposure_days':exposure_days,'total_fees':total_fees,'total_extra_cost':total_extra_cost,'total_gross_dividend':total_gross_dividend,'total_stress_reserve':total_reserve,'max_whole_day_volume_fraction':max_capacity}

def no_failure_metrics(value):
 if isinstance(value,dict):
  for k,v in value.items():
   need(not ('return_pct' in k or k in ('ending_equity','average_exposure_pct','max_drawdown_pct')),'invalid case cannot publish annual/aggregate metrics');no_failure_metrics(v)
 elif isinstance(value,list):
  for item in value:no_failure_metrics(item)

def independently_check_terminal_state(state,partial,trace,context,participation,extra,capital):
 """Reconstruct every observed terminal stream; no invented failed-day daily row.

 Source timing comes from explicit completed account clock (start=0/end=1),
 not simply from the last daily row. Unknown-tax/fractional start failures are
 required to retain the preceding clock and create no attempted-day credits.
 """
 day=trace['attempted_day'];need(day in context.sessions and day<='2025-12-31','explicit pre2026 attempted source session');last=state['last_account_clock'];need(trace['last_account_clock']==last,'actual trace/account terminal clock')
 completed=partial['days'];lastcompleted=completed[-1]['day'] if completed else None;need(trace['last_completed_day']==lastcompleted,'last completed row is explicit')
 expected_processed=[]
 if last is not None:
  need(last[0] in context.sessions and type(last[1]) is int and last[1] in (0,1),'valid explicit terminal start/end clock')
  expected_processed=[[d,phase] for d in context.sessions if d<=last[0] for phase in (0,1) if d<last[0] or phase<=last[1]]
 need(state['processed_account_clocks']==expected_processed,'every processed account clock is a complete contiguous phase prefix')
 need(all(f['execution_at'][:10]<=day and f['execution_at'][:10] in context.sessions for f in state['fills']) and all(r['day']<=day and r['day'] in context.sessions for r in state['corporate_ledger']),'no future or unconsumed out-of-calendar terminal rows')
 parents=state['parent_instructions'];orders=state['child_orders'];fills=state['fills'];ledger=state['corporate_ledger'];events=context.events;byfill=defaultdict(list);bycorp=defaultdict(list)
 for f in fills:byfill[f['execution_at'][:10]].append(f)
 for r in ledger:bycorp[r['day']].append(r)
 cash=D(capital);lots=defaultdict(list);registered={};cashclaims=[];stockclaims=[];paidtotal=D(0);feetotal=D(0);signedtotal=D(0)
 allowed={'RECORD_DATE_OWNERSHIP','NET_DIVIDEND_CASH_AVAILABLE','EX_DATE_ENTITLEMENT','CAPITAL_SHARES_LISTED','STOCK_DIVIDEND_SHARES_LISTED'};need(all(r['kind'] in allowed for r in ledger),'all terminal corporate kinds consumed')
 for session in context.sessions:
  if session>day:break
  expected=[];started=(session<day or last is not None and last[0]==day and last[1]>=0);ended=(session<day or last is not None and last[0]==day and last[1]==1)
  # No sessions beyond the real terminal account clock can mutate state.
  if last is None or session>last[0]:started=ended=False
  if started:
   actions=[]
   for eid,e in events.items():
    if e['ex']!=session:continue
    q=registered.get(eid,0);cap=e['capital']*q;stock=e['stock']*q;gross=cents(e['cash']*q);income=cents(e['stock_income']*q);reserve=cents((gross+income)*D('.2'))
    need(not q or (not e['capital'] or e['capital_verified']) and (not e['stock'] or e['stock_verified']),'source tax guards must pass before attempted-day mutation');need(cap==int(cap) and stock==int(stock) and reserve<=gross,'original fractional/tax cash guard before mutation');actions.append((eid,e,q,int(cap),int(stock),gross,income,reserve))
   for cl in cashclaims:
    if not cl['paid'] and cl['available_on']==session:cash+=D(cl['net']);paidtotal+=D(cl['net']);cl['paid']=True;expected.append({'day':session,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':cl['event_id'],'cash_delta':cl['net']})
   for eid,e,q,cap,stock,gross,income,reserve in actions:
    if gross:cashclaims.append({'event_id':eid,'instrument':e['code'],'gross':str(gross),'reserve':str(reserve),'net':str(gross-reserve),'available_on':next((d for d in context.sessions if d>e['pay']),None),'paid':False})
    for amount,kind in ((cap,'CAPITAL_TRANSFER'),(stock,'STOCK_DIVIDEND')):
     if amount:stockclaims.append({'event_id':eid,'instrument':e['code'],'quantity':amount,'listed':e['list'],'recorded':e['record'],'credited':False,'share_kind':kind})
    expected.append({'day':session,'kind':'EX_DATE_ENTITLEMENT','event_id':eid,'instrument':e['code'],'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),'capital_shares':cap,'stock_shares':stock,'taxable_stock_income':str(income)})
   for cl in stockclaims:
    if not cl['credited'] and cl['listed']<=session:
     lots[cl['instrument']].append({'quantity':cl['quantity'],'bought_on':cl['recorded'],'price':'0'});cl['credited']=True;expected.append({'day':session,'kind':'CAPITAL_SHARES_LISTED' if cl['share_kind']=='CAPITAL_TRANSFER' else 'STOCK_DIVIDEND_SHARES_LISTED','event_id':cl['event_id'],'quantity':cl['quantity']})
  if byfill[session] or any(o['submitted_at'][:10]==session for o in orders):
   need(started,'no fill/child before account start');audit_children(session,orders,parents,byfill[session],participation,extra,cash,tape=lambda c,d:audit_tape(context,c,d),bars=context.bars)
  for f in byfill[session]:
   code=f['security_id'];q=f['quantity'];p=D(f['price']);raw=context.bars[code][session];need(type(q) is int and q>0 and raw['tradestatus']=='1' and raw['isST']=='0' and p==cents(p),'terminal ordinary positive cent physical fill');gross=q*p;fee=fee_for(gross,f['action'],extra);need(D(f['cost'])==fee,'terminal separate rounded base+extra fee');feetotal+=fee;signedtotal+=gross if f['action']=='BUY' else -gross
   if f['action']=='BUY':need(q%100==0,'terminal100lot buy');cash-=gross+fee;lots[code].append({'quantity':q,'bought_on':session,'price':str(p)})
   else:
    need(f['action']=='SELL' and q<=sum(l['quantity'] for l in lots[code] if l['bought_on']<session),'terminal T+1 available shares');left=q
    for lot in lots[code]:
     if lot['bought_on']>=session:continue
     taken=min(left,lot['quantity']);lot['quantity']-=taken;left-=taken
    need(left==0,'terminal FIFO consumption');lots[code]=[l for l in lots[code] if l['quantity']];cash+=gross-fee
   need(cash>=0 and cash==D(f['cash_after']),'terminal every-fill cash bridge')
  if ended:
   for eid,e in events.items():
    if e['record']!=session:continue
    need(not any(not cl['credited'] and cl['instrument']==e['code'] for cl in stockclaims),'record cannot ignore prior unlisted shares');q=sum(l['quantity'] for l in lots[e['code']]);registered[eid]=q;expected.append({'day':session,'kind':'RECORD_DATE_OWNERSHIP','event_id':eid,'instrument':e['code'],'quantity':q})
  need(expected==bycorp[session],'all source-driven corporate events/payments/listing/record exact terminal clock and order')
 finalpositions={c:ls for c,ls in lots.items() if ls};need(set(finalpositions)==set(state['positions']),'terminal lot issuers')
 for c,ls in finalpositions.items():
  need(len(ls)==len(state['positions'][c]),'terminal FIFO lot counts')
  for x,y in zip(ls,state['positions'][c]):need(x['quantity']==y['quantity'] and x['bought_on']==y['bought_on'] and D(x['price'])==D(y['price']),'terminal lot date/quantity/cost')
 owned={c:sum(l['quantity'] for l in ls) for c,ls in finalpositions.items()}
 for cl in stockclaims:
  if not cl['credited']:owned[cl['instrument']]=owned.get(cl['instrument'],0)+cl['quantity']
 need(owned==state['owned_shares'] and registered==state['entitlements'] and cash==D(state['cash']) and cash==D(capital)-signedtotal-feetotal+paidtotal,'terminal actual owned/registered/cash global conservation')
 def claims_equal(actual,expected,numeric):
  need(len(actual)==len(expected),'all terminal claims retained including paid/listed history')
  for x,y in zip(actual,expected):
   need(set(x)==set(y),'terminal claim schema')
   for key in x:need(D(x[key])==D(y[key]) if key in numeric else x[key]==y[key],'terminal claim exact source economics/status '+key)
 claims_equal(state['cash_claims'],cashclaims,{'gross','reserve','net'});claims_equal(state['stock_claims'],stockclaims,set())
 return {'all_observed_terminal_cash_FIFO_T1_fees_entitlements_claims_reconstructed':True,'last_account_clock':last,'attempted_day':day,'last_completed_day':lastcompleted,'terminal_cash_CNY':str(cash),'terminal_fills':len(fills),'terminal_corporate_rows':len(ledger),'failed_day_fills':len(byfill[day]),'failed_day_corporate_rows':len(bycorp[day]),'annual_ROI_computed':False}

def framework_self_test():
 from types import SimpleNamespace
 controls=synthetic_controls();ctx=SimpleNamespace(bars={},events={},sessions=['2023-12-29'],targets={},proofs={'lifecycles':{}},expected_zero=set())
 row={'day':'2023-12-29','cash':'1000000','market_value':'0','pending_stock_value':'0','cash_receivable':'0','equity':'1000000','fees':'0','net_dividend_cash_available':'0','net_return':'0','exposure':'0'}
 data={'days':[row],'intents':[],'orders':[],'parent_instructions':[],'fills':[],'corporate_ledger':[],'ownership':{'2023-12-29':{}}};state=reconstruct_completed_prefix(data,ctx,100,40,'1000000');need(state['cash']==D('1000000'),'synthetic independent cash unchanged')
 return {'status':'SYNTHETIC_SOURCE_AND_ZERO_FLOW_LEDGER_FRAMEWORK_PASS','negative_controls':controls,'imports_project_code':False,'real_source_or_account_read':False,'draft_requires_final_runner_request_schema':False}

SOURCE_DIR='illiquidity-archive-scenario-sources-20261022'
SOURCE_REQUEST=PUBLIC+'illiquidity-archive-scenario-source-request.json'
SOURCE_REQUEST_SHA='c917b4c4cde4a6ce13d626e0ccc8f1f80f6875c08b417e07d98b29c6ba4a191c'
SOURCE_AUDIT=PUBLIC+'illiquidity-archive-scenario-independent-source-audit.json'
SOURCE_VERIFY=PUBLIC+'illiquidity-archive-scenario-source-run-verification.json'
LEDGER_AUDIT=PUBLIC+'audit_sources/2026-10-22-illiquidity-source-scenario-development-ledger.py'
ACCOUNT_METHODS=METHODS|{'scripts/run_illiquidity_intraday_development.py','scripts/replay_stock_distribution_targets.py','scripts/illiquidity_scenario_tape.py','scripts/run_illiquidity_source_scenario_development.py'}
ACCOUNT_PUBLIC=(SOURCE_REQUEST,SOURCE_AUDIT,SOURCE_VERIFY,PUBLIC+'illiquidity-archive-scenario-source-results.json',PUBLIC+'audit_sources/2026-10-22-illiquidity-archive-scenario-independent-source-audit.py',PUBLIC+'illiquidity-pre2026-results.json',PUBLIC+'illiquidity-pre2026-independent-csv-audit.json',PUBLIC+'illiquidity-pre2026-plan.json',PUBLIC+'illiquidity-scenario-tape-code-review.json',PUBLIC+'illiquidity-source-scenario-development-code-review.json',LEDGER_AUDIT,'docs/research/illiquidity-source-scenario-development-contract-2026-10-22.md')
PARTICIPATIONS=(100,500,1000);COSTS=(0,5,10,20,40);CAPITALS=('100000','1000000','10000000','100000000')
PROFILES=[f'{p}/{c}/{a}' for p in PARTICIPATIONS for c in COSTS for a in CAPITALS]

def required_account_inputs(base,repo):
 paths=required_inputs(base,repo)
 for name in ACCOUNT_METHODS|set(ACCOUNT_PUBLIC):paths['repo/'+name]=repo/name
 outputs=read(repo/SOURCE_VERIFY)['all34_output_file_sha256'];need(len(outputs)==34,'exact independently verified source34 map')
 for name in outputs:need(Path(name).name==name,'safe source output filename');paths['source/'+SOURCE_DIR+'/'+name]=base/SOURCE_DIR/name
 return paths

def load_success(folder):
 data={k:read(folder/(k+'.json')) for k in ('intents','orders','parent_instructions','fills','corporate_ledger','ownership','lifecycle_source_audit')}
 with (folder/'daily.csv').open(newline='') as f:data['days']=list(csv.DictReader(f))
 return data

def lifecycle_prefix(context,days):
 expected=[]
 for day in days:
  for code,byday in sorted(context.bars.items()):
   proof=context.proofs['lifecycles'].get(code,{})
   outside=proof.get('kind')=='LISTING_BEGIN' and day<proof['effective_date'] or proof.get('kind')=='DELISTING_END' and day>=proof['effective_date']
   if outside:expected.append({'instrument':code,'session':day,'reason':'BEFORE_PRIMARY_LISTING_BOUNDARY' if proof['kind']=='LISTING_BEGIN' else 'AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY','original_row_present':day in byday,'primary_document_sha256':proof['primary_document_sha256'],'synthetic_price_created':False})
 return expected

def independent_metrics(rebuilt,capital):
 need(rebuilt['days']==486 and rebuilt['intents']==24,'only complete pre2026 accounts receive annual metrics');nav=rebuilt['nav'];r24=(nav['2024-12-31']/D(capital)-1)*100;r25=(nav['2025-12-31']/nav['2024-12-31']-1)*100
 return {'2024_return_pct':float(r24),'2025_return_pct':float(r25),'average_exposure_pct':float(rebuilt['exposure_sum']/rebuilt['exposure_days']*100),'2024_yearend_equity_CNY':str(nav['2024-12-31']),'2025_yearend_equity_CNY':str(nav['2025-12-31']),'continuous_2025_denominator_CNY':str(nav['2024-12-31'])}

def check_full_result(stated,data,rebuilt):
 for k,value in [('fills',len(data['fills'])),('orders',len(data['orders'])),('monthly_decisions',24),('unfilled_parents',sum(p['remaining']>0 for p in data['parent_instructions'])),('whole_day_volume_violations',sum(D(f['quantity'])>D(rebuilt['context'].bars[f['security_id']][f['execution_at'][:10]]['volume']) for f in data['fills']))]:need(stated[k]==value,'complete summary actual count '+k)
 for k in ('all_fills_integer','daily_cash_and_share_conservation','record_date_entitlements_verified','zero_entitlements_verified','actual_delisting_exit_verified'):need(stated[k] is True,'original complete gate '+k)
 need(stated['opening_auction_liquidity_verified'] is False,'no auction proof upgrade')
 need(math.isclose(stated['max_order_fraction_of_whole_day_volume'],float(rebuilt['max_whole_day_volume_fraction']),rel_tol=1e-12,abs_tol=1e-12),'observed necessary whole-day capacity fraction')
 parents={p['order_id']:p for p in data['parent_instructions']};per_parent=Counter()
 for f in data['fills']:per_parent[f['parent_id']]+=f['quantity']
 for key,p in parents.items():need(p['filled_quantity']==per_parent[key] and p['remaining']+p['filled_quantity']==p['quantity'] and p['status'] in ('FILLED','PARTIAL_DAY_EXPIRED','UNFILLED_DAY_EXPIRED','UNFILLED_HALTED_DAY'),'actual parent final residuals')


def original_failure_guard_evidence(state,partial,trace,context):
 day=trace['attempted_day'];error=trace['error'];clock=state['last_account_clock'];frame=trace['frame_context'];events=context.events;registered=state['entitlements'];hits=[]
 if frame:
  need(frame['original_replay_file']=='scripts/replay_stock_distribution_targets.py' and frame.get('day')==day,'exact attempted original replay frame and day')
  # Source code line evidence is authenticated by the externally frozen method map.
  file=context.repo/frame['original_replay_file'];lines=file.read_text().splitlines();line=frame['original_replay_line'];need(type(line) is int and 1<=line<=len(lines) and lines[line-1].strip()==frame['original_replay_source_line'],'original thrown frame source line SHA-bound to unchanged method')
 if error in ('fractional corporate entitlement needs registry allocation evidence','applicable capital transfer tax treatment is unverified','applicable stock dividend tax basis is unverified','stock tax stress exceeds cash distribution; liability settlement unsupported'):
  for eid,e in events.items():
   if e['ex']!=day:continue
   q=registered.get(eid,0);cap=e['capital']*q;stock=e['stock']*q;gross=cents(e['cash']*q);income=cents(e['stock_income']*q);reserve=cents((gross+income)*D('.2'))
   bad=(error.startswith('fractional') and (cap!=int(cap) or stock!=int(stock)) or error.startswith('applicable capital') and q>0 and e['capital']>0 and not e['capital_verified'] or error.startswith('applicable stock') and q>0 and e['stock']>0 and (not e['stock_verified'] or e['stock_income']<=0) or error.startswith('stock tax stress') and reserve>gross)
   if bad:hits.append({'event_id':eid,'instrument':e['code'],'registered_quantity':q,'capital_nominal_shares':str(cap),'stock_nominal_shares':str(stock),'cash_gross_CNY':str(gross),'tax_reserve_CNY':str(reserve),'tax_proof_upgraded':False})
  need(hits and (clock is None or clock[0]<day) and not any(r['day']==day for r in state['corporate_ledger']) and not any(f['execution_at'][:10]==day for f in state['fills']),'actual source/record arithmetic explains pre-mutation company-action guard')
 elif error.startswith('lifecycle interval still requires shares, orders or price: '):
  tail=error.split(': ',1)[1].split();need(len(tail)==2 and tail[1]==day,'exact lifecycle error issuer/day');code=tail[0];proof=context.proofs['lifecycles'][code];outside=proof['kind']=='LISTING_BEGIN' and day<proof['effective_date'] or proof['kind']=='DELISTING_END' and day>=proof['effective_date'];need(outside and proof['verified_primary_boundary'] is True,'actual primary lifecycle boundary applies')
  pending={p['security_id'] for p in state['parent_instructions'] if p['status']=='PENDING'};required=set(state['owned_shares'])|pending|{e['code'] for eid,e in events.items() if e['ex']==day and registered.get(eid,0)};idx=context.sessions.index(day);target=context.targets.get(context.sessions[idx+1]) if idx+1<len(context.sessions) else None
  if target:required.update(target['weights'])
  need(code in required and set(frame['required'])==required and (clock is None or clock[0]<day),'actual inventory/pending/entitlement/next-prior-close-target source dependency explains lifecycle guard before start')
  hits=[{'instrument':code,'primary_document_sha256':proof['primary_document_sha256'],'boundary_kind':proof['kind'],'effective_date':proof['effective_date'],'actual_owned_shares':state['owned_shares'].get(code,0),'pending_parent_dependency':code in pending,'nexttarget_dependency':bool(target and code in target['weights'])}]
 elif error=='execution data or supported ordinary-board state unknown':
  pending=[p for p in state['parent_instructions'] if p['status']=='PENDING' and p['eligible_at'][:10]==day]
  for p in pending:
   r=context.bars[p['security_id']].get(day)
   if r is None or r['date']!=day or r['tradestatus'] not in ('0','1') or r['isST']!='0':hits.append({'instrument':p['security_id'],'raw_isST':r.get('isST') if r else None,'raw_tradestatus':r.get('tradestatus') if r else None,'parent_id':p['order_id']})
  need(hits,'actual current pending source row explains unchanged ordinary execution guard')
 else:
  # Fail closed on reasons not explained by this bounded independent auditor.
  raise AssertionError('unclassified actual failure requires explicit independent evidence, not hash-only acceptance: '+error)
 if clock is not None:
  expected=[]
  for d in context.sessions:
   if d>clock[0]:break
   for phase in (0,1):
    if d<clock[0] or phase<=clock[1]:expected.append([d,phase])
  need(state['processed_account_clocks']==expected,'all processed start/end phases exact prefix without hidden advance')
 else:need(state['processed_account_clocks']==[],'unstarted account has no processed phases')
 if state['last_broker_end'] is not None:
  end=datetime.fromisoformat(state['last_broker_end']);need(end.tzinfo is not None and end.date().isoformat()<=day,'terminal broker cannot advance into a later day')
  need(all(datetime.fromisoformat(f['execution_at'])<=end for f in state['fills']),'last broker clock not behind observed fills')
 observed_days=[r['day'] for r in partial['days']];expected_lifecycle=lifecycle_prefix(context,observed_days)
 if day not in observed_days:expected_lifecycle_with_attempt=lifecycle_prefix(context,observed_days+[day])
 else:expected_lifecycle_with_attempt=expected_lifecycle
 need(partial['lifecycle_source_audit'] in (expected_lifecycle,expected_lifecycle_with_attempt),'failed attempt preserves exact completed/attempted source classifications')
 return {'source_guard_cause_independently_explained':True,'guards_changed_or_bypassed':False,'source_dependencies':hits}

def synthetic_physical_fixture():
 from types import SimpleNamespace
 code='SH600001';d0='2023-12-29';d1='2024-01-02';asof=d0+'T07:05:00+00:00';eligible=d1+'T01:30:00+00:00';expiry=d1+'T06:55:00+00:00';source={'date':d0,'tradestatus':'1','isST':'0','preclose':'10','open':'10','close':'10','low':'10','high':'10','volume':'10000000'};bars={code:{d0:source,d1:{**source,'date':d1}}}
 windows=[]
 for label in [x for x in labels() if int(x[-2:])%5==0]:
  end=datetime.fromisoformat(d1+'T'+label).replace(tzinfo=LOCAL);start=end-timedelta(minutes=5);windows.append({'security_id':code,'start':utc(start),'end':utc(end),'available_at':utc(end),'volume_lower_shares':10000,'buy_price':'10','sell_price':'10','evidence_id':digest({'synthetic_window_end':label})})
 ctx=SimpleNamespace(bars=bars,events={},sessions=[d0,d1],targets={d1:{'as_of':d0,'weights':{code:'.001'}}},proofs={'lifecycles':{}},expected_zero=set(),tape=lambda c,d:windows)
 decision={'action':'BUY','security_id':code,'quantity':100,'evidence_ids':['synthetic'],'reason':'synthetic fixed target'};snapshot='a'*64;did=digest({'decision':decision,'snapshot':snapshot});parent={'order_id':'synthetic-parent','decision_id':did,'security_id':code,'action':'BUY','quantity':100,'filled_quantity':100,'remaining':0,'submitted_at':asof,'eligible_at':eligible,'expires_at':expiry,'status':'FILLED'}
 current=windows[1];previous=windows[0];cid=digest({'parent':parent['order_id'],'start':current['start'],'end':current['end'],'quantity':100,'previous_volume':10000,'evidence_id':previous['evidence_id']});child={'order_id':cid,'parent_id':parent['order_id'],'security_id':code,'action':'BUY','quantity':100,'limit_price':'10.95','submitted_at':current['start'],'expires_at':current['end'],'status':'FILLED','filled_quantity':100,'source_volume_as_of':previous['end'],'source_evidence_id':previous['evidence_id'],'source_volume_lower_shares':10000,'reserved_cash':'1104.38'}
 fill={'order_id':cid,'parent_id':parent['order_id'],'security_id':code,'action':'BUY','quantity':100,'price':'10','cost':'9.00','cash_after':'998991.00','execution_at':current['end'],'current_evidence_id':current['evidence_id'],'current_volume_lower_shares':10000};warm={'day':d0,'cash':'1000000','market_value':'0','pending_stock_value':'0','cash_receivable':'0','equity':'1000000','fees':'0','net_dividend_cash_available':'0','net_return':'0','exposure':'0'};ending={**warm,'day':d1,'cash':'998991.00','market_value':'1000','equity':'999991.00','fees':'9.00','net_return':str(D('999991')/D('1000000')-1),'exposure':str(D(1000)/D('999991'))}
 data={'days':[warm,ending],'intents':[{'execution_session':d1,'as_of':asof,'snapshot_sha256':snapshot,'equity_at_decision':'1000000','owned_integer_shares':{},'decisions':[decision]}],'parent_instructions':[parent],'orders':[child],'fills':[fill],'corporate_ledger':[],'ownership':{d0:{},d1:{code:100}},'lifecycle_source_audit':[]}
 state={'cash':'998991.00','positions':{code:[{'quantity':100,'bought_on':d1,'price':'10'}]},'owned_shares':{code:100},'parent_instructions':[parent],'child_orders':[child],'fills':[fill],'corporate_ledger':[],'cash_claims':[],'stock_claims':[],'entitlements':{},'last_account_clock':[d1,1],'last_broker_end':expiry,'processed_account_clocks':[[d0,0],[d0,1],[d1,0],[d1,1]]};trace={'attempted_day':d1,'last_completed_day':d1,'last_account_clock':[d1,1]}
 return ctx,data,state,trace

def final_self_tests():
 result=framework_self_test();ctx,data,state,trace=synthetic_physical_fixture();rebuilt=reconstruct_completed_prefix(data,ctx,100,40,'1000000');need(rebuilt['cash']==D('998991') and rebuilt['positions']['SH600001'][0]['quantity']==100,'manually expected BUY100 shares/gross1000/base5/extra4/physicalcash998991')
 independently_check_terminal_state(state,{'days':data['days']},trace,ctx,100,40,'1000000');controls=result['negative_controls']
 changed=copy.deepcopy(data);changed['fills'][0]['cost']='8.99';controls['synthetic_physical_fee_tamper_rejected']=negative(lambda:reconstruct_completed_prefix(changed,ctx,100,40,'1000000'))
 changed=copy.deepcopy(state);changed['cash']='998992';controls['synthetic_failed_cash_tamper_rejected']=negative(lambda:independently_check_terminal_state(changed,{'days':data['days']},trace,ctx,100,40,'1000000'))
 changed=copy.deepcopy(state);changed['entitlements']['orphan']=100;controls['synthetic_failed_entitlement_tamper_rejected']=negative(lambda:independently_check_terminal_state(changed,{'days':data['days']},trace,ctx,100,40,'1000000'))
 changed=copy.deepcopy(state);changed['last_account_clock']=['2024-01-03',0];controls['synthetic_failed_clock_tamper_rejected']=negative(lambda:independently_check_terminal_state(changed,{'days':data['days']},trace,ctx,100,40,'1000000'))
 result.update(status='SYNTHETIC_PHYSICAL_LEDGER_AND_TERMINAL_FAILURE_AUDIT_PASS',manual_buy_quantity=100,manual_gross_CNY='1000',manual_base_fee_CNY='5',manual_extra40bp_CNY='4',manual_ending_cash_CNY='998991',manual_integer_inventory=100,real_source_or_account_read=False,draft_requires_final_runner_request_schema=False);return result

# New trial: independent formation reconstruction; prior audit remains immutable.
RISK_POLICY='amihud22_monthly_price_risk1'
RISK_CONTRACT='MONTHLY_RAW_CLOSE_1CNY_ORDINARY_GUARD_V1'
RISK_TARGET_DIR='amihud-monthly-price-risk-targets-20261022'
RISK_PRIMARY_DIR='amihud-monthly-price-risk-primary-20261022'
RISK_METHOD='src/stock_rsi/monthly_price_risk.py'
RISK_BUILDER='scripts/build_monthly_price_risk_targets.py'
RISK_RUNNER='scripts/run_monthly_price_risk_development.py'
RISK_LEDGER_AUDIT=PUBLIC+'audit_sources/2026-10-22-amihud-monthly-price-risk-development-ledger.py'
RISK_QUANTUM=10**24





def independent_risk_selftests():
 inherited=final_self_tests();seed={'as_of':'2024-04-30','weights':{'A':.475,'B':.475}};cells={c:{'date':seed['as_of'],'close':'1.00','tradestatus':'1','isST':'0'} for c in seed['weights']};before=copy.deepcopy((seed,cells));noop,receipt=independent_risk_target(seed,cells);need(noop['weights']==seed['weights'] and (seed,cells)==before and not receipt['blocked'],'exact no-op/nonmutation at1CNY')
 below=copy.deepcopy(cells);below['B']['close']='.99';filtered,r=independent_risk_target(seed,below);need(filtered['weights']=={'A':'0.95'} and r['blocked']=={'B':['FORMATION_RAW_CLOSE_BELOW_CNY1']},'strict below1 not equal1 cutoff')
 allblocked=copy.deepcopy(cells);allblocked['A'].update(tradestatus='0',close='');allblocked['B']['isST']='1';cash,r=independent_risk_target(seed,allblocked);need(cash['weights']=={'A':'0','B':'0'} and r['all_filtered_to_cash'] and r['blocked']['A']==['KNOWN_FORMATION_HALT'] and r['blocked']['B']==['KNOWN_FORMATION_ST_STATE'],'known halted/ST allblocked names retained aszero cash desires')
 uneven={'as_of':'2024-04-30','weights':{'A':'.2375','B':'.2375','C':'.2375','D':'.2375'}};uc={c:{'date':'2024-04-30','close':'.99' if c=='A' else '10.00','tradestatus':'1','isST':'0'} for c in uneven['weights']};weighted,_=independent_risk_target(uneven,uc);need(weighted['weights']=={'B':'0.316666666666666666666666','C':'0.316666666666666666666666','D':'0.316666666666666666666668'},'manual exact24place down and lastcode residual')
 calls=[]
 def reader(c,d):calls.append([c,d]);return copy.deepcopy(cells[c])
 seeds={'2024-05-06':seed};sessions=['2024-04-30','2024-05-06','2024-05-07'];targets,receipts,accesses=independent_risk_formations(seeds,sessions,reader);need(accesses==[['A','2024-04-30'],['B','2024-04-30']]==calls,'exact selected source access cadence/order')
 checked=check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,accesses);need(checked['all_targets_independently_reconstructed']==1,'synthetic source object audit')
 negatives=inherited['negative_controls'];changed=copy.deepcopy(cells);changed['A']['future_return']=999;negatives['extra_future_formation_field_rejected']=negative(lambda:independent_risk_target(seed,changed))
 changed=copy.deepcopy(cells);changed['A']['date']='2024-05-06';negatives['execution_day_price_cell_rejected']=negative(lambda:independent_risk_target(seed,changed))
 changed=copy.deepcopy(cells);changed['A']['isST']='';negatives['unknown_state_not_silently_filtered']=negative(lambda:independent_risk_target(seed,changed))
 changedtargets=copy.deepcopy(targets);changedtargets['2024-05-06']['weights']['A']='.95';negatives['changed_target_projection_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,changedtargets,receipts,accesses))
 changedreceipts=copy.deepcopy(receipts);changedreceipts[0]['formation_evidence_id']='0'*64;negatives['changed_formation_evidence_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,targets,changedreceipts,accesses))
 changedaccess=accesses+[['A','2024-05-07']];negatives['unexpected_future_access_receipt_rejected']=negative(lambda:check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,changedaccess))
 def forbidden(c,d):raise RuntimeError('invalid source clock reached provider')
 negatives['future_execution_rejected_before_provider']=negative(lambda:independent_risk_formations({'2026-01-05':{'as_of':'2025-12-31','weights':seed['weights']}},['2025-12-31','2026-01-05'],forbidden))
 # Renaming symbols leaves economics unchanged: no issuer blacklist.
 renamed={'as_of':seed['as_of'],'weights':{'X':.475,'Y':.475}};renamedcells={'X':below['A'],'Y':below['B']};other,_=independent_risk_target(renamed,renamedcells);need(list(other['weights'].values())==list(filtered['weights'].values()),'identity-independent eligibility')
 return {'status':'PASS_SYNTHETIC_MONTHLY_PRICE_RISK_AND_INHERITED_ACCOUNT_AUDIT','policy_id':RISK_POLICY,'contract':RISK_CONTRACT,'inherited_pure_physical_fixture':inherited,'formation_tests':{'one_yuan_boundary':True,'no_op_literal_economic_weights_preserved':True,'allblocked_cash_zero_original_names':True,'manual24decimal_residual':True,'exact_priorclose_accesses':True,'no_ticker_specific_filter':True},'semantic_negative_controls_rejected':negatives,'imports_project_code':False,'real_target_or_quote_or_outcome_read':False,'real_account_or_source_query_run':False,'2026_values_read':False,'draft_waiting_new_wrapper_plan_interface':True}


def all24_synthetic_risk_formations():
 # Explicit synthetic source sessions, not an inferred real exchange calendar.
 seeds={};calendar=set();cells={}
 for year in (2024,2025):
  for month in range(1,13):
   execution=f'{year}-{month:02d}-02';formation=(date(year,month,1)-timedelta(days=1)).isoformat()
   if execution=='2024-01-02':formation='2023-12-29'
   calendar.update((formation,execution));seeds[execution]={'as_of':formation,'weights':{'A':.475,'B':.475}}
   for code in ('A','B'):cells[code,formation]={'date':formation,'close':'.99' if code=='B' and month%2==0 else '1.00','tradestatus':'1','isST':'0'}
 calls=[]
 def read_cell(c,d):calls.append([c,d]);need((c,d) in cells,'synthetic formation cannot access absent/future row');return copy.deepcopy(cells[c,d])
 targets,receipts,accesses=independent_risk_formations(seeds,sorted(calendar),read_cell)
 need(len(targets)==len(receipts)==24 and len(accesses)==48 and accesses==calls,'all24 fixed synthetic formation clocks/48 selected-cell reads')
 need(sum(t['weights']!=seeds[d]['weights'] for d,t in targets.items())==12,'known12 synthetic guard months with no parameter scan')
 return {'all24_synthetic_formations_reconstructed':True,'receipt_count':24,'source_cell_reads':48,'synthetic_changed_months':12,'calendar_is_explicit_synthetic_only':True}



def independent_numeric(value):
 need(type(value) in (str,int,float),'finite explicit original JSON numeric value, no bool')
 try:result=D(str(value))
 except Exception:raise AssertionError('invalid decimal formation field')
 need(result.is_finite(),'no nonfinite formation price/weight');return result

def independent_risk_target(seed,cells):
 """Source-only monthly policy, independently using integer/Fraction weights.

 Exact Fraction arithmetic determines the 24-place downward proportions;
 cent-grid validation is explicit rather than binary floating tolerances.
 No ticker identity, future row, outcome, execution or statutory-day count.
 """
 need(type(seed) is dict and set(seed)=={'as_of','weights'} and type(seed['weights']) is dict and seed['weights'],'nonempty original seed target schema')
 asof=seed['as_of'];need(type(asof) is str and date.fromisoformat(asof).isoformat()==asof and '2023-12-29'<=asof<='2025-12-31','canonical capped formation date')
 weights={c:independent_numeric(v) for c,v in seed['weights'].items()};need(all(w>0 for w in weights.values()) and abs(sum(weights.values())-D('.95'))<=D('1e-12'),'original positive95percent seed total')
 need(type(cells) is dict and set(cells)==set(weights),'only exact seed-selected formation cells')
 blocked={}
 for code in sorted(weights):
  row=cells[code];need(type(row) is dict and set(row)=={'date','close','tradestatus','isST'} and row['date']==asof,'exact four-field current formation cell; no future/extra fields')
  need(row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'known source activity/ST state')
  reasons=[]
  if row['tradestatus']=='0':reasons.append('KNOWN_FORMATION_HALT')
  else:
   close=independent_numeric(row['close']);need(close>0 and close.adjusted()<=25 and F(close)*100==int(F(close)*100),'positive active exact cent price')
   if close<D('1.00'):reasons.append('FORMATION_RAW_CLOSE_BELOW_CNY1')
  if row['isST']=='1':reasons.append('KNOWN_FORMATION_ST_STATE')
  if reasons:blocked[code]=reasons
 retained=sorted(set(weights)-set(blocked))
 if not blocked:result=copy.deepcopy(seed['weights'])
 elif not retained:result={c:'0' for c in sorted(weights)}
 elif len(retained)==1:result={retained[0]:'0.95'}
 else:
  # Source module sums fixed JSON Decimal weights before its high-precision
  # division. Preserve that exact total; do not silently renormalize seed sum.
  total=F(sum(weights[c] for c in retained));units={}
  for code in retained[:-1]:
   ratio=F(95,100)*F(weights[code])*RISK_QUANTUM/total;units[code]=ratio.numerator//ratio.denominator
  units[retained[-1]]=95*10**22-sum(units.values());need(all(q>0 for q in units.values()) and sum(units.values())==95*10**22,'exact95percent positive residual allocation')
  result={c:str(q//RISK_QUANTUM)+'.'+str(q%RISK_QUANTUM).zfill(24) for c,q in units.items()}
 evidence={'contract':RISK_CONTRACT,'formation_asof':asof,'original_seed_target':copy.deepcopy(seed),'formation_cells':copy.deepcopy(cells),'minimum_raw_close_CNY':'1.00','blocked':blocked,'retained':retained};eid=digest(evidence)
 target={'as_of':asof,'weights':result,'risk_overlay':{'contract':RISK_CONTRACT,'formation_evidence_id':eid}}
 receipt={**evidence,'formation_evidence_id':eid,'result_weights':copy.deepcopy(result),'all_filtered_to_cash':not retained,'statutory_delisting_classifier':False,'historical_arrival_verified':False}
 return target,receipt

def independent_risk_formations(seeds,sessions,reader):
 need(type(sessions) is list and sessions==sorted(set(sessions)),'explicit unique source calendar');targets={};receipts=[];accesses=[]
 for execution,seed in sorted(seeds.items()):
  need('2024-01-02'<=execution<='2025-12-31' and execution in sessions,'fixed pre2026 execution clock before provider access');i=sessions.index(execution);need(i>0 and seed['as_of']==sessions[i-1],'immediate prior observed source session')
  ex=date.fromisoformat(execution);formation=date.fromisoformat(seed['as_of']);previous=(ex.year,ex.month-1) if ex.month>1 else (ex.year-1,12);need((formation.year,formation.month)==previous,'formation lies in immediately previous calendar month')
  cells={}
  for code in sorted(seed['weights']):accesses.append([code,seed['as_of']]);cells[code]=reader(code,seed['as_of'])
  target,receipt=independent_risk_target(seed,cells);targets[execution]=target;receipts.append({'execution_session':execution,**receipt})
 return targets,receipts,accesses

def check_risk_target_output_objects(seeds,sessions,reader,targets,receipts,accesses):
 expected_targets,expected_receipts,expected_access=independent_risk_formations(seeds,sessions,reader)
 need(targets==expected_targets and receipts==expected_receipts and accesses==expected_access,'all targets, complete receipts/evidence and exact access sequence independently reconstructed')
 need(set(targets)==set(seeds) and len(receipts)==len(seeds),'no skipped/extra formation')
 for day,target in targets.items():need(set(target['weights'])<=set(seeds[day]['weights']),'no added security/rank substitution')
 return {'all_targets_independently_reconstructed':len(targets),'all_receipts_independently_reconstructed':len(receipts),'formation_cell_reads':len(accesses),'changed_weight_months':sum(targets[d]['weights']!=seeds[d]['weights'] for d in targets),'blocked_reason_counts':dict(Counter(reason for r in receipts for reasons in r['blocked'].values() for reason in reasons)),'all_filtered_cash_months':sum(r['all_filtered_to_cash'] for r in receipts),'actual_exit_proven_by_target_generation':False,'statutory_delisting_classifier':False}

def audit_risk_target_directory(base,repo,folder,request_path,expected_request_sha,original_context):
 """Prepared interface, called only after source generation is explicitly allowed.

 No account replay. All source/cell accesses are reconstructed independently
 against the unchanged seed source, never against post-execution data.
 """
 base,repo,folder,request_path=map(Path,(base,repo,folder,request_path));verify_sha(request_path,expected_request_sha);request=read(request_path)
 need(request['status']=='FROZEN_BEFORE_MONTHLY_PRICE_RISK_REAL_TARGET_GENERATION' and request['contract']==RISK_CONTRACT and request['policy_id']==RISK_POLICY and request['candidate_budget']==1 and request['minimum_formation_raw_close_CNY']=='1.00' and request['surviving_target_budget']=='.95' and request['end']=='2025-12-31' and request['portfolio_returns_permitted'] is False and request['2026_evaluation_permitted'] is False,'one fixed pre2026 target-generation trial')
 expected={**request['input_sha256'],'frozen_risk_target_request':expected_request_sha};paths={k:(repo/k[5:] if k.startswith('repo/') else base/k[7:] if k.startswith('source/') else None) for k in request['input_sha256']};paths['frozen_risk_target_request']=request_path
 need(all(path is not None and path.resolve().is_relative_to(repo.resolve()) or path is not None and path.resolve().is_relative_to(base.resolve()) for path in paths.values()),'all frozen target inputs inside explicit roots')
 for k,path in paths.items():verify_sha(path,expected[k])
 for name,h in request['method_code_sha256'].items():verify_sha(repo/name,h);need(request['input_sha256']['repo/'+name]==h,'target method bound as actual input')
 before={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()};need(set(before)=={'targets.json','formation_receipts.json','formation_accesses.json','minute_requirements.json','input-before.json','input-postcheck.json','terminal.json','summary.json'},'exact8 target-generation artifacts');need(read(folder/'input-before.json')==expected,'full source-only target input map')
 post=read(folder/'input-postcheck.json');need(post=={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'risk_request_rehashed_after_processing':True},'complete target source/request postcheck')
 targets=read(folder/'targets.json');receipts=read(folder/'formation_receipts.json');accesses=read(folder/'formation_accesses.json');seeds=original_context.targets
 def reader(code,day):
  row=original_context.bars[code][day];return {k:row[k] for k in ('date','close','tradestatus','isST')}
 result=check_risk_target_output_objects(seeds,original_context.sessions,reader,targets,receipts,accesses);need(result['all_targets_independently_reconstructed']==24,'all24 actual formation objects required')
 active,skipped=scope_from_targets(targets,original_context.bars,original_context.proofs['lifecycles']);minute={'active_requests':active,'nonexecuting_source_intervals':skipped};need(read(folder/'minute_requirements.json')==minute,'full independent new cumulative minute source scope')
 old=read(repo/MINREQ);need(set(map(tuple,active))<=set(map(tuple,old['active_requests'])) and all(r in old['nonexecuting_source_intervals'] for r in skipped),'no new source pair beyond unchanged authenticated bank')
 terminal=read(folder/'terminal.json');need(terminal=={'status':'RISK_TARGET_GENERATION_TERMINAL','original_error':None,'completed':True,'formation_accesses':accesses,'postcheck':post,'persistence_errors':[],'portfolio_returns_computed':False},'complete source-only target terminal with exact access sequence')
 artifacts={k:sha(folder/k) for k in ('targets.json','formation_receipts.json','formation_accesses.json','minute_requirements.json')};summary=read(folder/'summary.json')
 expected_summary={'status':'MONTHLY_PRICE_RISK_TARGETS_BUILT_ACCOUNT_NOT_RUN','contract':RISK_CONTRACT,'policy_id':RISK_POLICY,'request_sha256':expected_request_sha,'method_code_sha256':request['method_code_sha256'],'seed_target_sha256':sha(base/TARGET),'months':24,'formation_cell_reads':len(accesses),'changed_weight_months':result['changed_weight_months'],'blocked_reason_counts':result['blocked_reason_counts'],'all_filtered_cash_months':result['all_filtered_cash_months'],'new_active_minute_requirements':len(active),'new_nonexecuting_source_intervals':len(skipped),'all_minute_sources_inside_original_bank':True,'artifacts_sha256':artifacts,'actual_positions_changed_by_target_generation':False,'actual_exit_verified':False,'original_targets_or_failed_results_changed':False,'original_account_or_broker_changed':False,'statutory_delisting_classifier':False,'historical_arrival_verified':False,'original_source_admission_overridden':False,'conditional_engineering_only':True,'separate_account_freeze_required':True,'portfolio_returns_computed':False,'2026_quote_or_return_values_read':False,'objective_achieved':False,'input_count':len(paths),'all_inputs_unchanged':True}
 need(summary==expected_summary,'entire independent target summary counts/flags/paths/SHAs')
 for k,path in paths.items():verify_sha(path,expected[k])
 need(before=={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()},'all8 target outputs unchanged after independent reconstruction')
 return targets,{**result,'target_request_sha256':expected_request_sha,'target_summary_sha256':sha(folder/'summary.json'),'target_all_output_sha256':before,'all_target_inputs_verified_before_after':True,'new_minute_active_pairs':len(active),'new_nonexecuting_intervals':len(skipped)}

BASE_PLAN=PUBLIC+'illiquidity-source-scenario-development-plan.json'

BASE_PLAN_SHA='7a164209327630135689ddfb6a3b4b4b4a3fd885692e6ae2e37500563e298471'

FAILED_DIR='illiquidity-source-scenario-development-20261022'

TARGET_METHODS=ACCOUNT_METHODS|{RISK_METHOD,RISK_BUILDER}

TARGET_PUBLIC=(BASE_PLAN,PUBLIC+'illiquidity-source-scenario-development-results.json',PUBLIC+'illiquidity-source-scenario-development-independent-ledger-audit.json',PUBLIC+'illiquidity-source-scenario-development-run-verification.json',PUBLIC+'illiquidity-source-scenario-development-failure-diagnostic.json',PUBLIC+'amihud-monthly-price-risk-primary-discovery.json',PUBLIC+'amihud-monthly-price-risk-primary-review.json',PUBLIC+'monthly-price-risk-module-code-review.json',PUBLIC+'monthly-price-risk-builder-code-review.json','docs/research/amihud-monthly-price-risk-plan-2026-10-22.md')

def skip_json_value(text,start):
 """Locate an immutable JSON value without decoding skipped price/ledger cells."""
 i=start
 while i<len(text) and text[i].isspace():i+=1
 need(i<len(text),'truncated JSON metadata')
 first=text[i]
 if first=='"':
  i+=1;escape=False
  while i<len(text):
   c=text[i];i+=1
   if escape:escape=False
   elif c=='\\':escape=True
   elif c=='"':return i
  raise AssertionError('unterminated JSON string')
 if first in '{[':
  stack=[first];i+=1
  while i<len(text) and stack:
   c=text[i]
   if c=='"':i=skip_json_value(text,i);continue
   if c in '{[':stack.append(c)
   elif c in '}]':need(stack[-1]+c in ('{}','[]'),'JSON bracket mismatch');stack.pop()
   i+=1
  need(not stack,'truncated JSON container');return i
 while i<len(text) and not text[i].isspace() and text[i] not in ',]}':i+=1
 need(i>start,'empty JSON metadata value');return i

def object_spans(text):
 i=0
 while i<len(text) and text[i].isspace():i+=1
 need(i<len(text) and text[i]=='{','JSON object metadata required');i+=1;out={};decoder=json.JSONDecoder()
 while True:
  while i<len(text) and text[i].isspace():i+=1
  need(i<len(text),'truncated JSON object')
  if text[i]=='}':return out
  key,end=decoder.raw_decode(text,i);need(type(key) is str and key not in out,'unique JSON metadata member');i=end
  while text[i].isspace():i+=1
  need(text[i]==':','JSON key delimiter');i+=1
  while text[i].isspace():i+=1
  end=skip_json_value(text,i);out[key]=(i,end);i=end
  while text[i].isspace():i+=1
  if text[i]==',':i+=1;continue
  need(text[i]=='}','JSON object separator');return out

def member_from_text(text,key):
 spans=object_spans(text);need(key in spans,'required metadata member '+key);a,b=spans[key];return json.loads(text[a:b])

def metadata_member(path,key):return member_from_text(Path(path).read_text(),key)

def four_cell_packet(path):
 """Decode date first and only four requested daily fields, never OHLC/volume.

 Corporate distributions/adjustments and all other quote fields are lexically
 skipped. A later date is rejected before its close can be JSON-decoded.
 """
 text=Path(path).read_text();spans=object_spans(text);instrument=member_from_text(text,'instrument');window=member_from_text(text,'window');need(window==['2023-12-29','2025-12-31'],'original pre2026 raw source window')
 a,b=spans['bars'];i=a+1;bars={}
 while True:
  while text[i].isspace():i+=1
  if text[i]==']':break
  end=skip_json_value(text,i);rowtext=text[i:end];day=member_from_text(rowtext,'date');need(type(day) is str and '2023-12-29'<=day<='2025-12-31' and date.fromisoformat(day).isoformat()==day and day not in bars,'canonical unique source date within pre2026 cap, before price decoding')
  row={key:member_from_text(rowtext,key) for key in ('date','close','tradestatus','isST')};bars[day]=row;i=end
  while text[i].isspace():i+=1
  if text[i]==',':i+=1;continue
  need(text[i]==']','raw bar array separator')
 need(list(bars)==sorted(bars),'ordered original raw source dates');return instrument,bars

def authenticated_primary_metadata_paths(base,repo):
 discovery=read(repo/(PUBLIC+'amihud-monthly-price-risk-primary-discovery.json'));reviewpath=repo/(PUBLIC+'amihud-monthly-price-risk-primary-review.json');review=read(reviewpath);directory=base/RISK_PRIMARY_DIR;manifestpath=directory/'manifest.json';manifest=read(manifestpath)
 verify_sha(manifestpath,discovery['source_manifest_sha256']);verify_sha(reviewpath,discovery['independent_review_sha256']);expected=discovery['formal_primary_file_sha256'];canonical={'capture-manifest.json','szse-listing-rules-2023-08.pdf','sse-delist-rule-2020-12-31.html','sse-delist-rule-2020-12-31.html.txt','sse-delist-2024-01-09.html','sse-delist-2024-01-09.html.txt','szse-page-113.png','szse-page-116.png'}|{'review-'+n for n in review['reading_page_artifact_sha256']}
 need(len(expected)==22 and len(review['reading_page_artifact_sha256'])==14 and set(expected)==canonical and manifest['file_sha256']==expected,'canonical22 primary documents/pages complete')
 need(expected['capture-manifest.json']==review['capture_manifest_sha256'] and len(review['sources'])==3 and {Path(d['local_path']).name for d in review['sources']}=={'szse-listing-rules-2023-08.pdf','sse-delist-rule-2020-12-31.html','sse-delist-2024-01-09.html'},'exact three primary source metadata anchors')
 for d in review['sources']:need(expected[Path(d['local_path']).name]==d['sha256'],'primary review immutable source SHA')
 for n,h in review['reading_page_artifact_sha256'].items():need(expected['review-'+n]==h,'all14 reviewed primary page SHA')
 need(manifest['portfolio_returns_computed'] is False and manifest['historical_arrival_verified'] is False,'primary metadata does not certify outcomes/arrival')
 paths={'source/'+RISK_PRIMARY_DIR+'/manifest.json':manifestpath}
 for n,h in expected.items():need(Path(n).name==n,'safe primary filename');verify_sha(directory/n,h);paths['source/'+RISK_PRIMARY_DIR+'/'+n]=directory/n
 return paths

def authenticated_old307_metadata_paths(base,repo):
 verification=repo/(PUBLIC+'illiquidity-source-scenario-development-run-verification.json');audit=repo/(PUBLIC+'illiquidity-source-scenario-development-independent-ledger-audit.json');expected=metadata_member(verification,'all307_local_output_file_sha256');audited=metadata_member(audit,'all_output_sha256')
 canonical={f'{p}/{c}/{capital}/{name}' for p in PARTICIPATIONS for c in COSTS for capital in CAPITALS for name in ('error.json','failed_account_state.json','failure_trace.json','partial_case.json','tape_accessed_pairs.json')}|{'summary.json','input-before.json','event_source_receipts.json','input-postcheck.json','derived_events.json','terminal.json','case_results.json'}
 need(len(expected)==307 and set(expected)==canonical and expected==audited,'canonical307 old failed account immutable file map')
 verify_sha(audit,metadata_member(verification,'independent_audit_sha256'));need(metadata_member(audit,'plan_sha256')==metadata_member(verification,'plan_sha256')==BASE_PLAN_SHA and metadata_member(audit,'completed_profiles')==0 and metadata_member(audit,'failed_profiles')==60 and metadata_member(audit,'raw_confirmation_passes_independently') is False,'old failed account independent metadata anchor')
 h=metadata_member(verification,'summary_sha256');need(h==metadata_member(audit,'summary_sha256')==expected['summary.json'],'old failure summary immutable hash anchor');verify_sha(repo/(PUBLIC+'illiquidity-source-scenario-development-results.json'),h)
 paths={}
 for n,h in expected.items():path=base/FAILED_DIR/n;verify_sha(path,h);paths['source/'+FAILED_DIR+'/'+n]=path
 return paths,expected

def target_required_paths(base,repo):
 paths=required_account_inputs(base,repo)
 for name in TARGET_METHODS|set(TARGET_PUBLIC):paths['repo/'+name]=repo/name
 paths.update(authenticated_primary_metadata_paths(base,repo));oldpaths,oldmap=authenticated_old307_metadata_paths(base,repo);paths.update(oldpaths);return paths,oldmap

def verify_complete_target_bindings(base,repo,requestfile,expected_sha):
 verify_sha(requestfile,expected_sha);request=read(requestfile)
 need(request['status']=='FROZEN_BEFORE_MONTHLY_PRICE_RISK_REAL_TARGET_GENERATION' and request['contract']==RISK_CONTRACT and request['policy_id']==RISK_POLICY and request['candidate_budget']==1 and request['minimum_formation_raw_close_CNY']=='1.00' and request['surviving_target_budget']=='.95' and request['end']=='2025-12-31' and request['portfolio_returns_permitted'] is False and request['2026_evaluation_permitted'] is False,'one fixed source-only pre2026 policy trial')
 need(set(request['method_code_sha256'])==TARGET_METHODS,'exact mandatory32 original plus risk source methods');paths,oldmap=target_required_paths(base,repo);need(set(paths)==set(request['input_sha256']),'complete source/primary/old307/target input identity set')
 for key,path in paths.items():verify_sha(path,request['input_sha256'][key])
 for name,h in request['method_code_sha256'].items():need(request['input_sha256']['repo/'+name]==h,'method/input identity agrees');verify_sha(repo/name,h)
 return request,paths,oldmap

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('repo-root','source-root','request','expected-request-sha256','run-dir','output'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--terminal-confirmed',action='store_true');a=parser.parse_args();need(a.terminal_confirmed,'root must authorize actual terminal account output audit')
 repo,base,run,out=map(lambda v:Path(v).resolve(),(a.repo_root,a.source_root,a.run_dir,a.output));requestfile=Path(a.request).resolve();need(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo) and not out.is_relative_to(run),'new external audit output only');verify_sha(requestfile,a.expected_request_sha256);request=read(requestfile)
 need(request['status']=='FROZEN_BEFORE_MONTHLY_PRICE_RISK_DEVELOPMENT_ACCOUNTS' and request['strategy']==RISK_POLICY and request['base_strategy']==request['decision_record_seed_policy_id']=='amihud22' and request['risk_contract']==RISK_CONTRACT and request['candidate_budget']==1 and request['phase']=='dev' and request['end']=='2025-12-31' and request['participation_bps']==list(PARTICIPATIONS) and request['extra_bps']==list(COSTS) and request['capitals']==list(CAPITALS) and request['profiles']==PROFILES,'all original fixed60 profiles and pre2026 interval')
 need(request['source_contract']==CONTRACT and request['source_scenario_dir']==SOURCE_DIR and request['source_request_sha256']==SOURCE_REQUEST_SHA and request['original_source_admission_overridden'] is False and request['conditional_engineering_only'] is True and request['2026_evaluation_permitted'] is False,'separate conditional source only unchanged alpha/execution matrix')
 need(request['registry_allocation_assumed'] is False,'no registry allocation interpretation added to new policy trial')
 need(set(request['method_code_sha256'])==RISK_ACCOUNT_METHODS,'exact mandatory unchanged account and versioned source method set')
 paths=required_risk_account_inputs(base,repo);need(set(paths)==set(request['input_sha256']),'exact complete input set before any account values');expected={**request['input_sha256'],'frozen_account_plan':a.expected_request_sha256};paths['frozen_account_plan']=requestfile
 for k,path in paths.items():verify_sha(path,expected[k])
 for name,h in request['method_code_sha256'].items():need(expected['repo/'+name]==h,'method/input binding');verify_sha(repo/name,h)
 need(sha(__file__)==expected['repo/'+RISK_LEDGER_AUDIT],'independent audit exact source frozen in request')
 sourceaudit=read(repo/SOURCE_AUDIT);verification=read(repo/SOURCE_VERIFY);need(verification['independent_audit_sha256']==sha(repo/SOURCE_AUDIT) and verification['root_audit_reproduced_byte_identically'] is True and verification['all34_output_file_sha256']==sourceaudit['all_output_sha256'] and request['source_summary_sha256']==sourceaudit['summary_sha256'],'source independent/report/output anchors actual exact bytes')
 context=IndependentScenarioSource(base,repo,base/SOURCE_DIR,repo/SOURCE_AUDIT,sha(repo/SOURCE_AUDIT));need(len(context.sessions)==486 and len(context.targets)==24,'full pre2026 source horizon');verify_sha(base/SOURCE_DIR/'summary.json',request['source_summary_sha256'])
 verify_sha(repo/BASE_PLAN,BASE_PLAN_SHA);need(request['source_summary_sha256']==read(repo/BASE_PLAN)['source_summary_sha256']==sha(base/SOURCE_DIR/'summary.json'),'new plan source summary equals original frozen plan and actual source bytes')
 targetrequest=repo/RISK_REQUEST;target_audit=read(repo/RISK_TARGET_AUDIT);verify_sha(targetrequest,request['risk_target_request_sha256']);targetreq,_,old307=verify_complete_target_bindings(base,repo,targetrequest,request['risk_target_request_sha256'])
 need(target_audit['status']=='PASS_INDEPENDENT_MONTHLY_PRICE_RISK_TARGET_AUDIT' and target_audit['request_sha256']==request['risk_target_request_sha256'] and target_audit['audit_code_sha256']==sha(repo/RISK_TARGET_AUDIT_CODE) and target_audit['all_input_sha256']=={**targetreq['input_sha256'],'frozen_risk_target_request':request['risk_target_request_sha256']} and target_audit['critical_or_important_findings']==[],'independent target audit identity/code/request/input anchor')
 newtargets,target_reconstruction=audit_risk_target_directory(base,repo,base/RISK_TARGET_DIR,targetrequest,request['risk_target_request_sha256'],context)
 need(target_reconstruction['target_all_output_sha256']==target_audit['all_output_sha256'] and target_reconstruction['target_summary_sha256']==request['risk_target_summary_sha256'],'all8 newtarget artifacts/summary match independent audit before account review');context.targets=newtargets
 summary=read(run/'summary.json');cases=read(run/'case_results.json');post=read(run/'input-postcheck.json');terminal=read(run/'terminal.json');need(read(run/'input-before.json')==expected,'entire actual input-before map equals request')
 need(post=={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'account_plan_rehashed_after_processing':True},'exhaustive source/account plan postcheck')
 need(terminal['status']=='MONTHLY_PRICE_RISK_ACCOUNT_RUN_TERMINAL' and terminal['original_error'] is None and terminal['completed_profiles']==60 and terminal['postcheck']==post and terminal['persistence_errors']==[],'complete60 profile terminal with no hidden I/O interrupt/postcheck error')
 need(summary['status']=='MONTHLY_PRICE_RISK_DEVELOPMENT_COMPLETE' and summary['strategy']==RISK_POLICY and summary['base_strategy']==summary['decision_record_seed_policy_id']=='amihud22' and summary['risk_contract']==RISK_CONTRACT and summary['phase']=='dev' and summary['source_warmup_start']=='2023-12-29' and summary['start']=='2024-01-02' and summary['end']=='2025-12-31' and summary['plan_sha256']==a.expected_request_sha256 and summary['results_by_profile']==cases and set(cases)==set(PROFILES),'complete actual60case summary/request binding')
 need(summary['method_code_sha256']==request['method_code_sha256'] and summary['source_contract']==CONTRACT and summary['source_request_sha256']==SOURCE_REQUEST_SHA and summary['source_summary_sha256']==request['source_summary_sha256'] and summary['source_scenario_dir']==SOURCE_DIR and summary['all_inputs_unchanged'] is True and summary['input_count']==len(paths),'actual source/method/input summary anchors')
 for k in ('original_source_admission_overridden','registry_allocation_assumed','original_account_guards_changed','queue_and_impact_calibrated','historical_arrival_verified','2026_strategy_returns_queried','sealed_evidence','objective_achieved'):need(summary[k] is False,'retained engineering/source/guard boundary '+k)
 need(summary['risk_target_request_sha256']==request['risk_target_request_sha256'] and summary['risk_target_summary_sha256']==request['risk_target_summary_sha256'] and summary['independent_target_audit_sha256']==sha(repo/RISK_TARGET_AUDIT) and summary['original_targets_or_failed_results_changed'] is False,'new target policy anchors/original failed evidence unchanged')
 need(summary['conditional_engineering_only'] is True and summary['reference_CNY']=='1000000','fixed reference capital and conditional premises')
 verify_sha(run/'derived_events.json',summary['derived_events_sha256']);verify_sha(run/'event_source_receipts.json',summary['event_source_receipts_sha256']);need(read(run/'derived_events.json')==read(base/EVENTS/'derived_events.json') and read(run/'event_source_receipts.json')==read(base/EVENTS/'event_source_receipts.json'),'original302 event and source receipt literal objects preserved')
 outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()};results={};deferred={};allaccess=set();firstsuccess=None;firstfailure=None
 for caseid in PROFILES:
  participation,extra,capital=caseid.split('/');participation=int(participation);extra=int(extra);folder=run/caseid;stated=cases[caseid];access=read(folder/'tape_accessed_pairs.json');need(access==[list(k) for k in sorted(set(map(tuple,access)))],'canonical per-case accessed pairs');need(set(map(tuple,access))<=set(context.kinds),'no access outside fixed pre2026 source scope');allaccess.update(map(tuple,access))
  actualmap={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
  if stated['status']=='NESTED_EXECUTION_ACCOUNT_RECONCILED':
   need(set(actualmap)=={'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json','lifecycle_source_audit.json','tape_accessed_pairs.json'} and actualmap==stated['artifact_sha256'],'exact9 success artifacts and all hashes')
   data=load_success(folder);verify_risk_intent_metadata(data['intents'],context);need([r['day'] for r in data['days']]==context.sessions and len(data['intents'])==24,'full486 day and24 intent success');need(data['lifecycle_source_audit']==lifecycle_prefix(context,context.sessions),'all original362 lifecycle exclusions retained exactly and dependency checked')
   rebuilt=reconstruct_completed_prefix(data,context,participation,extra,capital);rebuilt['context']=context;check_full_result(stated,data,rebuilt)
   expectedaccess={(p['security_id'],p['eligible_at'][:10]) for p in data['parent_instructions'] if context.bars[p['security_id']][p['eligible_at'][:10]]['tradestatus']=='1'};need(set(map(tuple,access))==expectedaccess,'every actual parent executable day accesses a source even with no child fill')
   deferred[caseid]=rebuilt;results[caseid]={'status':'INDEPENDENT_FULL_ACCOUNT_RECONSTRUCTED','sessions':486,'intents':24,'parents':len(data['parent_instructions']),'children':len(data['orders']),'fills':len(data['fills']),'corporate_rows':len(data['corporate_ledger']),'all_cash_FIFO_T1_claims_marks_equity_fees_reconstructed':True,'actual_zero_unverified_tax_entitlements':True,'actual_delisting_exit':True,'source_evidence_prices_caps_and_window_cash_reserves_verified':True,'tape_accessed_pairs':len(access),'artifact_sha256':actualmap}
   if firstsuccess is None:firstsuccess=(data,participation,extra,capital)
  else:
   need(stated['status']=='INVALID_SOURCE_OR_ACCOUNT' and actualmap==stated['failure_artifact_sha256'] and set(actualmap)=={'failed_account_state.json','partial_case.json','failure_trace.json','error.json','tape_accessed_pairs.json'} and stated['persistence_errors']==[],'exact5 failed evidence artifacts/hash map/no hidden persistence errors');no_failure_metrics(stated);error=read(folder/'error.json');need(error=={k:stated[k] for k in ('status','error_type','error')},'original failure error source preserved');state=read(folder/'failed_account_state.json');partial=read(folder/'partial_case.json');trace=read(folder/'failure_trace.json');need(trace['error_type']==error['error_type'] and trace['error']==error['error'] and trace['tape_accessed_pairs']==access,'actual error/frame/access trace binding')
   need(state is not None,'account factory failed before observable state: cannot certify physical failure ledger');need(set(state)=={'cash','positions','owned_shares','parent_instructions','child_orders','fills','corporate_ledger','cash_claims','stock_claims','entitlements','last_account_clock','last_broker_end','processed_account_clocks'},'complete failed physical account state retained')
   prefixdays={r['day'] for r in partial['days']};prefix={'days':partial['days'],'intents':partial['intents'],'ownership':partial['ownership'],'lifecycle_source_audit':partial['lifecycle_source_audit'],'parent_instructions':state['parent_instructions'],'orders':[o for o in state['child_orders'] if o['submitted_at'][:10] in prefixdays],'fills':[f for f in state['fills'] if f['execution_at'][:10] in prefixdays],'corporate_ledger':[r for r in state['corporate_ledger'] if r['day'] in prefixdays]}
   verify_risk_intent_metadata(prefix['intents'],context)
   allowed_unsubmitted=None
   if error['error']=='frozen signal eligibility contradicts independent formation-day status':
    current=trace['attempted_day'];idx=context.sessions.index(current);allowed_unsubmitted=context.sessions[idx+1] if idx+1<len(context.sessions) else None
   if prefixdays:reconstruct_completed_prefix(prefix,context,participation,extra,capital,allowed_unsubmitted_execution=allowed_unsubmitted)
   terminalresult=independently_check_terminal_state(state,partial,trace,context,participation,extra,capital);terminalresult['independent_guard_evidence']=failure_guard_evidence(state,partial,trace,context);results[caseid]={'status':'FAILED_ACCOUNT_TERMINAL_AND_COMPLETED_PREFIX_INDEPENDENTLY_RECONSTRUCTED','error_type':error['error_type'],'error':error['error'],'completed_sessions':len(partial['days']),'completed_intents':len(partial['intents']),'terminal_state':terminalresult,'annual_ROI_computed':False,'failure_artifact_sha256':actualmap}
   if firstfailure is None:firstfailure=(state,partial,trace,participation,extra,capital)
 need(len(results)==60 and summary['tape_accessed_sessions']==len(allaccess),'entire declared matrix and union source access telemetry')
 context.recheck()
 for k,path in paths.items():verify_sha(path,expected[k])
 need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all observed account output bytes immutable during independent audit')
 # No independent aggregate return is calculated until all60 ledgers/input/output checks above finish.
 for caseid,rebuilt in deferred.items():
  metrics=independent_metrics(rebuilt,caseid.split('/')[2]);stated=cases[caseid]
  for k in ('2024_return_pct','2025_return_pct','average_exposure_pct'):need(math.isclose(stated[k],metrics[k],rel_tol=1e-12,abs_tol=1e-10),'independent annual continuous denominator/exposure '+caseid+' '+k)
  results[caseid]['independent_metrics']=metrics
 reference=[results[f'{p}/40/1000000'] for p in PARTICIPATIONS];gate=all(r['status']=='INDEPENDENT_FULL_ACCOUNT_RECONSTRUCTED' and r['independent_metrics']['2024_return_pct']>0 and r['independent_metrics']['2025_return_pct']>0 and r['independent_metrics']['average_exposure_pct']>=90 and r['actual_zero_unverified_tax_entitlements'] and r['actual_delisting_exit'] for r in reference);need(gate==summary['raw_development_confirmation_passes'],'all three fixed40bp1m reference gate independently reproduced')
 controls=synthetic_controls()
 if firstsuccess and firstsuccess[0]['fills']:
  data,p,e,c=firstsuccess;changed=copy.deepcopy(data);changed['fills'][0]['cost']=str(D(changed['fills'][0]['cost'])+D('.01'));controls['actual_fee_tamper_rejected']=negative(lambda:reconstruct_completed_prefix(changed,context,p,e,c))
 if firstfailure:
  state,partial,trace,p,e,c=firstfailure;changed=copy.deepcopy(state);changed['cash']=str(D(changed['cash'])+D('.01'));controls['actual_failure_cash_tamper_rejected']=negative(lambda:independently_check_terminal_state(changed,partial,trace,context,p,e,c));changed=copy.deepcopy(state);changed['entitlements']['synthetic_orphan']=1;controls['actual_failure_registered_quantity_tamper_rejected']=negative(lambda:independently_check_terminal_state(changed,partial,trace,context,p,e,c))
 report={'status':'PASS_INDEPENDENT_MONTHLY_PRICE_RISK_DEVELOPMENT_LEDGER_AUDIT','policy_id':RISK_POLICY,'risk_contract':RISK_CONTRACT,'base_strategy':'amihud22','decision_record_seed_policy_id':'amihud22','target_reconstruction':target_reconstruction,'old307_failed_outputs_preserved':True,'original_targets_or_failed_results_changed':False,'audit_code_sha256':sha(__file__),'plan_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),'source_summary_sha256':request['source_summary_sha256'],'source_independent_audit_sha256':sha(repo/SOURCE_AUDIT),'imports_project_code':False,'stdlib_only':True,'production_account_broker_simulator_scorer_called':False,'all60_profiles_reconstructed':True,'completed_profiles':len(deferred),'failed_profiles':60-len(deferred),'all_bound_inputs_checked_before_after':True,'input_count':len(paths),'all_input_sha256':expected,'all_output_sha256':outputs,'results_by_profile':results,'reference_profiles':[f'{p}/40/1000000' for p in PARTICIPATIONS],'raw_confirmation_passes_independently':gate,'semantic_negative_controls_rejected':controls,'original_source_admission_overridden':False,'conditional_engineering_only':True,'registry_allocation_assumed':False,'original_account_guards_changed':False,'2026_quote_or_return_values_read':False,'network_or_new_queries':False,'Parquet_values_decoded':False,'queue_and_impact_calibrated':False,'historical_arrival_verified':False,'actual_FIFO_tax_liability_verified':False,'sealed_evidence':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Independent physical bookkeeping of observed60pre2026 outcomes; original financial methods and all failures remain unchanged.','Source execution remains conditional on cent-grid/binary32 and the START/END interval hypotheses. Original240 admission is still false.','Daily trade status/whole-day necessary capacity and sampled intraday price/volume scenarios do not certify real order queues, impact or executable liquidity.','Flat20% tax stress is not actual FIFO tax settlement. Lifecycle source exceptions require actual account dependency proofs, not ticker removal.','The monthly CNY1/ordinary/activity policy is a fixed research heuristic, not a statutory10/20day classification or actual exit proof. Decision records retain the unchanged amihud22 base ID while target risk metadata and summary identify the new composite policy.','This audit makes no2026 investment performance or full-October/sealed-evidence claim.']}
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'output':str(out),'audit_code_sha256':sha(__file__),'report_sha256':sha(out),'complete':len(deferred),'failed':60-len(deferred),'reference_gate':gate}))


RISK_REQUEST=PUBLIC+'amihud-monthly-price-risk-target-request.json'
RISK_TARGET_AUDIT=PUBLIC+'amihud-monthly-price-risk-independent-target-audit.json'
RISK_TARGET_AUDIT_CODE=PUBLIC+'audit_sources/2026-10-22-amihud-monthly-price-risk-target-audit.py'
RISK_ACCOUNT_METHODS=TARGET_METHODS|{RISK_RUNNER}
RISK_ACCOUNT_PUBLIC=(RISK_REQUEST,RISK_TARGET_AUDIT,RISK_TARGET_AUDIT_CODE,RISK_LEDGER_AUDIT,PUBLIC+'monthly-price-risk-account-code-review.json')

def required_risk_account_inputs(base,repo):
 paths,_=target_required_paths(base,repo)
 for name in RISK_ACCOUNT_METHODS|set(RISK_ACCOUNT_PUBLIC):paths['repo/'+name]=repo/name
 for name in ('targets.json','formation_receipts.json','formation_accesses.json','minute_requirements.json','input-before.json','input-postcheck.json','terminal.json','summary.json'):paths['source/'+RISK_TARGET_DIR+'/'+name]=base/RISK_TARGET_DIR/name
 return paths

def verify_risk_intent_metadata(intents,context):
 for intent in intents:
  execution=intent['execution_session'];need(execution in context.targets,'fixed24 intended execution session');target=context.targets[execution];asof=target['as_of'];need(intent['as_of']==asof+'T07:05:00+00:00','unchanged base priorclose15:05 clock')
  need(target['risk_overlay']['contract']==RISK_CONTRACT,'target metadata identifies composite policy');eid=digest({'policy':'amihud22','formation':asof,'target':target})
  for decision in intent['decisions']:need(decision['evidence_ids']==[eid] and decision['reason']=='frozen monthly amihud22 target, physical-share execution','unchanged base policy reason/recordID binds full new risk target metadata')

def failure_guard_evidence(state,partial,trace,context):
 if trace['error']!='frozen signal eligibility contradicts independent formation-day status':return original_failure_guard_evidence(state,partial,trace,context)
 day=trace['attempted_day'];idx=context.sessions.index(day);need(idx+1<len(context.sessions),'formation failure needs next explicit execution');execution=context.sessions[idx+1];target=context.targets[execution];need(target['as_of']==day and state['last_account_clock']==[day,1] and partial['days'][-1]['day']==day,'old formation-status guard occurs after completed physical day')
 bad=[{'instrument':c,'formation_tradestatus':context.bars[c][day]['tradestatus'],'desired_weight':str(w)} for c,w in target['weights'].items() if context.bars[c][day]['tradestatus']!='1'];need(bad and not any(i['execution_session']==execution for i in partial['intents']) and not any(p['submitted_at']==day+'T07:05:00+00:00' for p in state['parent_instructions']),'known formation halt explains original all-key status guard; no new pending intent was submitted')
 frame=trace['frame_context'];file=context.repo/frame['original_replay_file'];need(frame['original_replay_file']=='scripts/replay_stock_distribution_targets.py' and file.read_text().splitlines()[frame['original_replay_line']-1].strip()==frame['original_replay_source_line'],'unchanged exact original thrown source line')
 need(partial['lifecycle_source_audit']==lifecycle_prefix(context,[r['day'] for r in partial['days']]),'completed source exclusions exact')
 return {'source_guard_cause_independently_explained':True,'guards_changed_or_bypassed':False,'unique_last_formation_intent_not_submitted':execution,'source_dependencies':bad}

def risk_account_synthetic_tests():
 r=independent_risk_selftests();r['all24_synthetic_fixture']=all24_synthetic_risk_formations();need(len(RISK_ACCOUNT_METHODS)==33 and len(PROFILES)==60,'exact33 methods/60 immutable matrix identities')
 # The original snapshot base ID remains amihud22; full overlay metadata must
 # still participate in the actual decision-evidence hash.
 seed={'as_of':'2024-04-30','weights':{'A':.475,'B':.475}};cells={c:{'date':'2024-04-30','close':'1.00','tradestatus':'1','isST':'0'} for c in seed['weights']};target,_=independent_risk_target(seed,cells);eid=digest({'policy':'amihud22','formation':seed['as_of'],'target':target});ctx=type('SyntheticContext',(),{'targets':{'2024-05-06':target}})();intent={'execution_session':'2024-05-06','as_of':'2024-04-30T07:05:00+00:00','decisions':[{'evidence_ids':[eid],'reason':'frozen monthly amihud22 target, physical-share execution'}]};verify_risk_intent_metadata([intent],ctx)
 changed=copy.deepcopy(intent);changed['decisions'][0]['evidence_ids']=['0'*64];r['semantic_negative_controls_rejected']['changed_composite_target_evidence_rejected']=negative(lambda:verify_risk_intent_metadata([changed],ctx))
 r.update(status='PASS_SYNTHETIC_MONTHLY_PRICE_RISK_ACCOUNT_AUDIT_READY',draft_waiting_new_wrapper_plan_interface=False,real_target_or_quote_or_outcome_read=False,real_account_or_source_query_run=False,terminal_confirmation_required_for_actual_main=True);return r


def last_formation_failure_synthetic_test():
 from types import SimpleNamespace
 d0='2023-12-29';d1='2024-01-02';seed={'as_of':d0,'weights':{'A':.475,'B':.475}};cells={c:{'date':d0,'close':'','tradestatus':'0','isST':'0'} for c in seed['weights']};target,_=independent_risk_target(seed,cells)
 row={'day':d0,'cash':'1000000','market_value':'0','pending_stock_value':'0','cash_receivable':'0','equity':'1000000','fees':'0','net_dividend_cash_available':'0','net_return':'0','exposure':'0'};data={'days':[row],'intents':[],'parent_instructions':[],'orders':[],'fills':[],'corporate_ledger':[],'ownership':{d0:{}},'lifecycle_source_audit':[]}
 ctx=SimpleNamespace(targets={d1:target},sessions=[d0,d1],bars={c:{d0:r} for c,r in cells.items()},events={},proofs={'lifecycles':{}},expected_zero=set())
 need(negative(lambda:reconstruct_completed_prefix(data,ctx,100,40,'1000000')),'missing formation intent cannot pass ordinary success path')
 reconstruct_completed_prefix(data,ctx,100,40,'1000000',allowed_unsubmitted_execution=d1)
 with tempfile.TemporaryDirectory(prefix='risk-audit-frame-synthetic-') as td:
  ctx.repo=Path(td);file=ctx.repo/'scripts/replay_stock_distribution_targets.py';file.parent.mkdir();line="raise ValueError('frozen signal eligibility contradicts independent formation-day status')";file.write_text(line+'\n')
  state={'last_account_clock':[d0,1],'parent_instructions':[]};trace={'error':'frozen signal eligibility contradicts independent formation-day status','attempted_day':d0,'frame_context':{'original_replay_file':'scripts/replay_stock_distribution_targets.py','original_replay_line':1,'original_replay_source_line':line}};proof=failure_guard_evidence(state,data,trace,ctx);need(proof['source_guard_cause_independently_explained'] and proof['unique_last_formation_intent_not_submitted']==d1,'exact old halt formation guard explains missing last intent without treating it as successful cash exit')
 return True

if __name__=='__main__':
 if sys.argv[1:]==['--self-test']:
  result=risk_account_synthetic_tests();result['exact_last_halt_formation_failure_fixture']=last_formation_failure_synthetic_test();print(json.dumps(result,indent=2))
 else:main()
