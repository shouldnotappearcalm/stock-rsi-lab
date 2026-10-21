"""Independent issued-A-size source, allocation and normalized CSV output audit.
Only stdlib; does not unpickle reports, import strategy/account code, or query sources.
All decoded binary market values are bounded through2025-12-31.
"""
import argparse,copy,csv,hashlib,json,math,re,struct,unicodedata
from collections import defaultdict
from decimal import Decimal
from html import unescape
from pathlib import Path
if not __debug__:raise RuntimeError('Do not disable audit assertions with -O')
CANDIDATE='szse_monthly_small_issued_cap'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
def close(a,b,*,money=False):
 assert math.isfinite(a) and math.isfinite(b)
 assert math.isclose(a,b,rel_tol=1e-9,abs_tol=.01 if money else 1e-6),(a,b)
def read(folder,name):
 with (folder/name).open() as stream:return list(csv.DictReader(stream))
def plain(s):return unescape(re.sub(r'<[^>]*>','',s)).strip()
def numeric(s):
 s=unicodedata.normalize('NFKC',s).replace(',','').strip()
 if s in ('','-','--','—'):return None
 v=Decimal(s);assert v.is_finite();return str(v)
def parse_original(raw,month):
 try:html=raw.decode('utf-8-sig');encoding='utf-8-sig'
 except UnicodeDecodeError:html=raw.decode('gb18030');encoding='gb18030'
 title=re.search(r'TRANSACTIONS?\s+OF\s+SECURITIES\s*[-—]?\s*[（(]\s*(\d{4})[./-](\d{1,2})',plain(html),re.I)
 assert title and f'{int(title[1]):04d}-{int(title[2]):02d}'==month
 rows=[]
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr\s*>',html,re.I|re.S):
  cells=[]
  for c in re.finditer(r'<t[dh]\b([^>]*?)(?:/\s*>|>(.*?)</t[dh]\s*>)',row,re.I|re.S):
   cells.append((plain(c[2] or ''),c[1]))
  if cells:rows.append(cells)
 compact=lambda x:re.sub(r'\s','',unicodedata.normalize('NFKC',x))
 assert '发行量IssuedVolume10,000' in compact(rows[0][2][0])
 assert '流通量ListedVolume10,000' in compact(rows[0][3][0])
 assert '收市价Close'==compact(rows[1][7][0])
 stocks={};allrows=0
 for row in rows:
  code=row[0][0]
  if not re.fullmatch(r'\d{6}',code):continue
  allrows+=1
  if not code.startswith(('000','001','002','003')):continue
  assert len(row)==16
  expected=[f'c{i}' for i in range(1,9)]+['separator']+[f'c{i}' for i in range(9,16)]
  assert all(re.search(r'class=[\"\']'+re.escape(k)+r'[\"\']',attrs) for k,(_,attrs) in zip(expected,row))
  c='SZ'+code;assert c not in stocks;r=[v for v,_ in row]
  name=unicodedata.normalize('NFKC',re.sub(r'\s','',r[1])).upper()
  issued,listed,price=(numeric(r[i]) for i in (2,3,11))
  for v in (issued,listed,price):assert v is None or Decimal(v)>=0
  if issued is not None and listed is not None:assert Decimal(listed)<=Decimal(issued)
  stocks[c]={'name':r[1],'issued_10k_shares':issued,'listed_10k_shares':listed,'close':price,'pe':numeric(r[15]),'reported_special_name':'ST' in name or '退' in name}
 assert len(stocks)>=1000
 return {'month':month,'encoding':encoding,'all_security_rows':allrows,'stocks':stocks}
def month_shift(month,offset):
 y,m=map(int,month.split('-'));y,m=divmod(y*12+m-1+offset,12);return f'{y:04d}-{m+1:02d}'
def buildday(url):
 stamp=re.search(r'(?:/t|/W0)(\d{8})',url)[1];return stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:]
def field_at(code,field,day,asof):
 assert day<=asof<='2025-12-31'
 key=(code,field)
 if key not in source_cache:
  with (provider/'features'/code.lower()/(field+'.day.bin')).open('rb') as stream:
   head=stream.read(4);begin=struct.unpack('<f',head)[0];assert begin==int(begin);begin=int(begin)
   raw=stream.read(4*max(0,date_indices['2025-12-31']+1-begin))
  assert len(raw)%4==0;source_cache[key]=(begin,struct.unpack('<'+'f'*(len(raw)//4),raw))
 begin,values=source_cache[key];offset=date_indices[day]-begin
 if not 0<=offset<len(values):return None
 value=values[offset];return value if math.isfinite(value) else None
def execution_factor(code,day):
 v=field_at(code,'factor',day,day);assert v is not None and v>0;return v
def independent_mark(code,day,mark):
 result={'instrument':code,'session':day,'marked_normalized_price':mark,'verified':False};states=gapstates.get(code,{})
 if states.get(day,{}).get('tradestatus')!='0':return result|{'reason':'NO_INDEPENDENT_SUSPENDED_STATE'}
 for prior in reversed(calendar[:date_indices[day]]):
  value=field_at(code,'close',prior,day)
  if value is None or value<=0:continue
  factor=field_at(code,'factor',prior,day)
  try:raw=float(states.get(prior,{}).get('close',''))
  except (ValueError,TypeError):raw=float('nan')
  if factor is None or factor<=0 or not math.isfinite(raw) or not math.isclose(value/factor,raw,abs_tol=.005,rel_tol=1e-6):return result|{'reason':'CROSS_SOURCE_LAST_VISIBLE_PRICE_NOT_VERIFIED'}
  if not math.isfinite(mark) or not math.isclose(mark,value,abs_tol=1e-8,rel_tol=1e-8):return result|{'reason':'MARK_DIFFERS_FROM_LAST_VISIBLE_CLOSE'}
  return result|{'verified':True,'classification':'INDEPENDENT_HALT_LAST_VISIBLE_MARK','last_visible_close_date':prior,'last_visible_normalized_close':value,'source_tradestatus':'0','actual_quote_on_suspended_day_created':False}
 return result|{'reason':'NO_PRIOR_VISIBLE_CLOSE'}
def reconstruct_formations(published,targets,receipts):
 assert set(targets)=={CANDIDATE,'eligible_equal_weight'} and len(receipts)==24
 by_execution={r['execution_session']:r for r in receipts};assert len(by_execution)==24
 assert all(set(t)==set(expected_execution) for t in targets.values())
 for day in expected_execution:
  prior=calendar[date_indices[day]-1];month=month_shift(day[:7],-2);report=published[month]
  assert prior[:7]==month_shift(month,1) and max(report['article_build_day'],report['table_build_day'])<=prior
  names=sorted(c for c,spans in intervals.items() if c.startswith(('SZ000','SZ001','SZ002','SZ003')) and any(a<=prior<=b for a,b in spans))
  assert len(names)>=100;covered=[c for c in names if c in report['stocks']];assert len(covered)>=.95*len(names)
  scores={}
  for c in covered:
   r=report['stocks'][c]
   if any(r.get(k) is None for k in ('issued_10k_shares','listed_10k_shares','close')):continue
   issued,listed,price=(Decimal(r[k]) for k in ('issued_10k_shares','listed_10k_shares','close'))
   assert all(v.is_finite() and v>=0 for v in (issued,listed,price)) and listed<=issued
   if r['reported_special_name'] or issued<=0 or price<=0:continue
   current=[field_at(c,f,prior,prior) for f in ('close','factor','volume')]
   if any(v is None or v<=0 for v in current):continue
   scores[c]=issued*Decimal(10000)*price
  assert len(scores)>=50 and len(scores)>=.5*len(names)
  chosen=sorted(scores,key=lambda c:(scores[c],c))[:len(scores)//10]
  expected={'execution_session':day,'formation_asof':prior,'source_month':month,'source_article_build_day':report['article_build_day'],'source_table_build_day':report['table_build_day'],
   'source_table_sha256':report['table_sha256'],'availability_convention':'complete following trading month ends at formation close','historical_arrival_verified':False,
   'historical_members':len(names),'published_member_rows':len(covered),'eligible':len(scores),'selected':chosen,
   'published_A_cap_CNY':{c:str(v) for c,v in scores.items()},'scores':{c:str(-v) for c,v in scores.items()},'latest_factor_price_read':prior}
  assert by_execution[day]==expected,(day,'exact source/rank receipt')
  for family,selected in ((CANDIDATE,chosen),('eligible_equal_weight',sorted(scores))):
   assert targets[family][day]=={'as_of':prior,'weights':{c:.95/len(selected) for c in selected}},(day,family,'frozen target')
 assert len({c for t in targets[CANDIDATE].values() for c in t['weights']})==68

def equivalent(actual, expected):
    if isinstance(expected, dict):
        assert set(actual)==set(expected), (set(actual),set(expected))
        for key in expected:equivalent(actual[key],expected[key])
    elif isinstance(expected, (list,tuple)):
        assert len(actual)==len(expected)
        for a,b in zip(actual,expected):equivalent(a,b)
    elif isinstance(expected,bool) or expected is None or isinstance(expected,str):
        assert actual==expected and type(actual)==type(expected)
    else:close(float(actual),float(expected))


def independent_allocation(equity, held, weights, asof):
    budget=equity*math.fsum(weights.values());q={};quotes={};desired={};options=[]
    for c in sorted(c for c,w in weights.items() if w>0):
        p=field_at(c,'close',asof,asof);f=field_at(c,'factor',asof,asof)
        assert p is not None and p>0 and f is not None and f>0
        lot=100/f;lot_value=100*p/f;v=equity*weights[c];current=held.get(c,0.)
        desired[c]=v;quotes[c]=(p,f,lot)
        if current*p<=v:
            count=math.floor((v-current*p)/lot_value+1e-10)
            q[c]=current+count*lot
        else:q[c]=math.floor(v/lot_value+1e-10)*lot
        trial=q[c]+lot;action='ONE_BUY_LOT'
        if current*p>v:
            trial=min(trial,current)
            action='CANCEL_REMAINING_SELL' if trial==current else 'REDUCE_SELL_ONE_LOT'
        expense=(trial-q[c])*p
        gap=v-q[c]*p
        improvement=gap**2-(v-trial*p)**2
        if expense>0 and improvement>0:
            options.append((float(format(improvement,'.12g')),c,trial,expense,improvement,action))
    initial=math.fsum(q[c]*quotes[c][0] for c in q)
    before=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    remaining=budget-initial;steps=[]
    for _,c,trial,expense,improvement,action in sorted(options,key=lambda r:(-r[0],r[1])):
        if expense<=remaining+max(1e-8,equity*1e-10):
            steps.append({'instrument':c,'normalized_units_added':trial-q[c],
                'notional_added':expense,'squared_error_reduction':improvement,'action':action})
            q[c]=trial;remaining-=expense
    orders=[]
    for c,current in held.items():
        if current>0 and weights.get(c,0.)==0:
            orders.append({'instrument':c,'side':'SELL','normalized_units':current,
                'known_normalized_close':None,'known_factor':None,'as_of':asof,
                'quantity_basis':'KNOWN_INVENTORY_FULL_EXIT'})
    for c in sorted(q):
        current=held.get(c,0.);change=q[c]-current;p,f,lot=quotes[c]
        if abs(change)<=1e-8*max(1.,current,q[c]):continue
        if change>0:assert math.isclose(change*f/100,round(change*f/100),rel_tol=1e-10,abs_tol=1e-8)
        orders.append({'instrument':c,'side':'BUY' if change>0 else 'SELL',
            'normalized_units':abs(change),'known_normalized_close':p,'known_factor':f,
            'as_of':asof,'quantity_basis':'PRIOR_CLOSE_BUDGETED_LOT_TARGET'})
    final=math.fsum(q[c]*quotes[c][0] for c in q)
    after=math.fsum((desired[c]-q[c]*quotes[c][0])**2 for c in q)
    assert final<=budget+max(1e-8,equity*1e-10) and after<=before+max(1e-8,before*1e-10)
    receipt={'as_of':asof,'target_notional_budget':budget,'initial_planned_notional':initial,
        'final_planned_notional':final,'unallocated_notional_budget':budget-final,
        'squared_tracking_error_before':before,'squared_tracking_error_after':after,
        'post_order_normalized_positions':q,'allocation_steps':steps,
        'execution_prices_or_returns_used':False,'future_cash_or_fill_guaranteed':False}
    return sorted(orders,key=lambda o:(o['side']!='SELL',o['instrument'])),receipt

def audit_case(label,stated,days,orders,holdings,intents,marks):
    extra,name=label.split('/')
    assert stated['status']=='DAILY_PROXY_DEVELOPMENT_RECONCILED'
    assert [r['session'] for r in days]==expected_days
    by_order,by_held=defaultdict(list),defaultdict(list)
    for row in orders:by_order[row['session']].append(row)
    for row in holdings:by_held[row['session']].append(row)
    cash = initial = float(plan['capital_CNY']); inventory = defaultdict(float)
    nav = {}; exposures = []; fees = turnover = 0.; peak = initial; dd = 0.
    rounding_excesses = [];expected_marks=[]
    assert set(by_order)<=set(expected_days) and set(by_held)<=set(expected_days)
    for day in days:
        d = day['session']; cost = gross = 0.
        assert day['signal_date'] == calendar[calendar.index(d)-1]
        assert (day['signal_present'] == 'True') == (d in targets[name])
        for order in by_order[d]:
            assert d in targets[name] and order['signal_date'] == targets[name][d]['as_of'] < d
            raw_q = float(order['filled_normalized_units']); raw_request = float(order['requested_normalized_units'])
            q, requested = abs(raw_q), abs(raw_request)
            amount = float(order['signed_trade_value']); fee = float(order['cost'])
            assert order['side'] in ('BUY', 'SELL')
            # Qlib indicators use signed SELL quantities. Its exchange rounds
            # with (amount*factor+0.1)//100, which can slightly exceed a request.
            assert (raw_q >= 0 and raw_request >= 0) if order['side'] == 'BUY' else (raw_q <= 0 and raw_request <= 0)
            if q > requested + 1e-5:
                excess = (q-requested)*execution_factor(order['instrument'], d)
                assert excess <= .100001, ('beyond Qlib 0.1-share rounding guard', order)
                rounding_excesses.append(excess)
            assert (order['fill_status']=='UNFILLED')==(q==0 and amount==0 and fee==0)
            if q:
                price = float(order['normalized_price']); sign = 1 if order['side'] == 'BUY' else -1
                close(amount, sign*q*price, money=True)
                sourceopen=field_at(order['instrument'],'open',d,d)
                assert sourceopen is not None and sourceopen>0;close(price,sourceopen)
                rate = (.0005 if sign == 1 else .0015) + int(extra)/10000
                close(fee, max(5., abs(amount)*rate), money=True)
                inventory[order['instrument']] += sign*q
                assert inventory[order['instrument']] >= -1e-6
            else:
                close(amount, 0., money=True); close(fee, 0., money=True)
            cash -= amount + fee; cost += fee; gross += abs(amount)
        assert cash >= -.01
        close(cash, float(day['cash']), money=True)
        assert len(by_order[d]) == int(day['orders'])
        close(cost, float(day['cost']), money=True); close(gross, float(day['turnover']), money=True)
        active = {h['instrument']: h for h in by_held[d]}
        assert len(active) == len(by_held[d])
        for code in set(inventory) | set(active):
            close(inventory.get(code, 0.), float(active[code]['normalized_units']) if code in active else 0.)
        market = 0.
        for held in active.values():
            assert float(held['normalized_units'])>0
            visible=field_at(held['instrument'],'close',d,d)
            if visible is not None and visible>0:close(float(held['normalized_price']),visible)
            else:expected_marks.append(independent_mark(held['instrument'],d,float(held['normalized_price'])))
            value = float(held['value'])
            close(value, float(held['normalized_units'])*float(held['normalized_price']), money=True)
            market += value
        nav[d] = cash + market
        close(market, float(day['stock_value']), money=True)
        close(nav[d], float(day['account_value']), money=True)
        for held in active.values(): close(float(held['weight']), float(held['value'])/nav[d])
        exposures.append(market/nav[d]); fees += cost; turnover += gross
        peak = max(peak, nav[d]); dd = min(dd, nav[d]/peak - 1)
    returns = {'2024_return_pct': (nav['2024-12-31']/initial-1)*100,
               '2025_return_pct': (nav['2025-12-31']/nav['2024-12-31']-1)*100,
               'net_compound_return_pct': (nav['2025-12-31']/initial-1)*100,
               'average_exposure_pct': sum(exposures)/len(exposures)*100,
               'max_drawdown_pct': dd*100, 'cost_pct_initial': fees/initial*100,
               'turnover_x_initial': turnover/initial}
    for key, value in returns.items(): close(value, stated[key])
    assert len(days) == stated['sessions'] and len(orders) == stated['orders']
    close(sum(r['fill_status'] == 'UNFILLED' for r in orders), stated['unfilled_orders'])
    equivalent(marks,expected_marks)
    assert sum(not r['verified'] for r in marks) == stated['unverified_held_marks']
    assert len(intents)==len(expected_execution)==24
    assert [i['execution_session'] for i in intents]==expected_execution
    for intent in intents:
        d=intent['execution_session'];asof=calendar[calendar.index(d)-1]
        assert intent['as_of_close_convention']==asof+'T15:05:00+08:00'
        prior_equity=nav[asof] if asof in nav else initial
        prior_held={h['instrument']:float(h['normalized_units']) for h in by_held.get(asof,[])}
        close(float(intent['equity_at_decision']),prior_equity,money=True)
        equivalent(intent['holdings_at_decision'],prior_held)
        equivalent(intent['target_weights'],targets[name][d]['weights'])
        expected_orders,allocation=independent_allocation(prior_equity,prior_held,targets[name][d]['weights'],asof)
        equivalent(intent['orders'],expected_orders)
        requests={(o['instrument'],o['side']):abs(float(o['requested_normalized_units'])) for o in by_order[d]}
        assert len(requests)==len(by_order[d])
        equivalent(requests,{(o['instrument'],o['side']):o['normalized_units'] for o in expected_orders})
        equivalent(intent['allocation_receipt'],allocation)
        assert intent['latest_decision_price_read']==asof
        assert intent['execution_exchange_queried_for_decision'] is False
    return {'status': 'NORMALIZED_CSV_LEDGER_RECONSTRUCTED', **returns,
        'independent_allocation_intents_reconstructed':len(intents),
        'sessions': len(days), 'orders': len(orders), 'unverified_held_marks_preserved': stated['unverified_held_marks'],
        'cash_inventory_fees_market_value_reconciled': True,
        'qlib_guard_rounding_request_excess_count': len(rounding_excesses),
        'max_qlib_raw_equivalent_request_excess': max(rounding_excesses, default=0.),
        'strict_fill_not_above_requested_quantity_verified': not rounding_excesses}

def main(argv=None):
 global plan,calendar,provider,date_indices,source_cache,intervals,gapstates,targets,expected_execution,expected_days
 parser=argparse.ArgumentParser()
 for n in ('run-dir','provider-uri','source-capture-dir','gap-states','repo-root','plan','expected-plan-sha256','output'):parser.add_argument('--'+n,required=True)
 args=parser.parse_args(argv);root=Path(args.run_dir);repo=Path(args.repo_root);provider=Path(args.provider_uri);out=Path(args.output);planfile=Path(args.plan)
 assert not out.exists() and sha(planfile)==args.expected_plan_sha256;plan=load(planfile)
 assert plan['candidate_budget']==1 and plan['families']==[CANDIDATE] and plan['extra_bps']==[20,40] and plan['capital_CNY']==1000000
 assert plan['status']=='FROZEN_BEFORE_EXCHANGE_SIZE_OUTCOMES' and plan['account_window']==['2024-01-02','2025-12-31']
 assert plan['2026_market_values_queried'] is False and plan['2026_feedback_to_rule_changes'] is False
 assert sha(repo/plan['design_file'])==plan['design_sha256']
 for name,h in plan['method_code_sha256'].items():assert sha(repo/name)==h,name
 fieldfile=repo/'experiments/qlib/szse-issued-size-source-fields.json';assert sha(fieldfile)==plan['source_field_review_sha256'];fields=load(fieldfile)
 summary=load(root/'summary.json');assert summary['plan_sha256']==sha(planfile) and summary['candidate_budget']==1
 assert summary['source_field_review_sha256']==sha(fieldfile) and summary['method_code_sha256']==plan['method_code_sha256']
 for k in ('2026_market_values_queried','sealed_evidence','objective_achieved','raw_share_execution_verified','historical_arrival_verified'):assert summary[k] is False
 assert summary['start']=='2024-01-02' and summary['end']=='2025-12-31'
 assert sha(root/'targets.json')==plan['initial_targets_sha256']==summary['targets_sha256']
 assert sha(root/'formation_receipts.json')==plan['initial_receipts_sha256']==summary['formation_receipts_sha256']
 calendar=(provider/'calendars/day.txt').read_text().splitlines();assert calendar==sorted(set(calendar));date_indices={d:i for i,d in enumerate(calendar)}
 assert '2025-12-31' in date_indices;source_cache={}
 for relative,h in plan['input_sha256'].items():
  if relative!='price_files':assert sha(provider/relative)==h,relative
 intervals=defaultdict(list);codes=set()
 for line in (provider/'instruments/csi500.txt').read_text().splitlines():
  c,a,b=line.split();intervals[c].append((a,b))
  if c.startswith(('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')) and a<='2025-12-31' and b>='2023-12-29':codes.add(c)
 files=[Path('instruments/all.txt')]
 for c in sorted(codes):files.extend(Path('features')/c.lower()/(f+'.day.bin') for f in ('open','high','low','close','volume','factor','amount','adjclose'))
 files.append(Path('features/sh000905/adjclose.day.bin'));digest=hashlib.sha256()
 for relative in files:digest.update(relative.as_posix().encode()+b'\0');digest.update((provider/relative).read_bytes());digest.update(b'\0')
 assert digest.hexdigest()==plan['input_sha256']['price_files']
 source=Path(args.source_capture_dir);manifest=load(source/'manifest.json')
 assert sha(source/'manifest.json')==plan['source_capture_manifest_sha256']==summary['source_capture_manifest_sha256']==fields['source_manifest_sha256']
 assert manifest['status']=='PRE2026_SZSE_MONTHLY_ORIGINAL_TABLES_CAPTURED' and sha(source/'request.json')==manifest['request_sha256']
 assert manifest['source_reader_sha256']==sha(repo/'src/stock_rsi/szse_monthly.py')
 assert set(manifest['months'])=={month_shift('2023-11',n) for n in range(24)}
 for name,h in manifest['journal_artifact_sha256'].items():assert sha(source/name)==h
 published={};rowcount=0;missing=0
 for month,item in manifest['months'].items():
  for kind in ('article','table','normalized'):assert sha(source/item[kind+'_file'])==item[kind+'_sha256']
  for receipt in item['query_receipts']:
   for kind in ('request','reserved','response'):assert sha(source/receipt[kind+'_file'])==receipt[kind+'_sha256']
  parsed=parse_original((source/item['table_file']).read_bytes(),month);normalized=load(source/item['normalized_file'])
  assert all(normalized[k]==v for k,v in parsed.items()),month
  assert normalized['article_build_day']==buildday(item['article_url']) and normalized['table_build_day']==buildday(item['table_url'])
  rowcount+=len(parsed['stocks']);missing+=sum(any(r[k] is None for k in ('issued_10k_shares','listed_10k_shares','close')) for r in parsed['stocks'].values())
  assert fields['per_month'][month]=={'table_sha256':item['table_sha256'],'mainboard_rows':len(parsed['stocks']),'header_encoding':parsed['encoding']}
  published[month]={**parsed,'article_build_day':normalized['article_build_day'],'table_build_day':normalized['table_build_day'],'table_sha256':item['table_sha256']}
 assert rowcount==fields['mainboard_rows']==35821 and missing==fields['missing_fields']==0 and fields['inconsistent_listed_issued_rows']==0 and fields['all24_headers_reviewed'] is True
 gaproot=Path(args.gap_states);assert sha(gaproot/'manifest.json')==plan['gap_state_manifest_sha256'];gm=load(gaproot/'manifest.json');gapstates={}
 assert gm['window']==['2023-12-29','2025-12-31'] and gm['2026_market_values_queried'] is False
 for c,h in gm['per_code_sha256'].items():
  f=gaproot/'codes'/(c+'.json');assert sha(f)==h;p=load(f);assert p['instrument']==c and all('2023-12-29'<=r['date']<='2025-12-31' for r in p['rows']);gapstates[c]={r['date']:r for r in p['rows']}
 expected_days=[d for d in calendar if '2024-01-02'<=d<='2025-12-31'];expected_execution=[d for d in expected_days if d[:7]!=calendar[date_indices[d]-1][:7]];assert len(expected_execution)==24
 targets=load(root/'targets.json');receipts=load(root/'formation_receipts.json');reconstruct_formations(published,targets,receipts)
 assert set(summary['results_by_extra_bps_and_family'])=={f'{e}/{n}' for e in (20,40) for n in (CANDIDATE,'eligible_equal_weight')}
 audited={};cases={}
 for label,stated in summary['results_by_extra_bps_and_family'].items():
  folder=root/label
  assert {'days.csv','orders.csv','holdings.csv','decision_intents.json','suspension_mark_audit.json'}<=set(stated['artifact_sha256'])
  for name,h in stated['artifact_sha256'].items():assert sha(folder/name)==h
  cases[label]=(read(folder,'days.csv'),read(folder,'orders.csv'),read(folder,'holdings.csv'),load(folder/'decision_intents.json'),load(folder/'suspension_mark_audit.json'))
  audited[label]=audit_case(label,stated,*cases[label])
 reference=audited['40/'+CANDIDATE];eligible=reference['2024_return_pct']>0 and reference['2025_return_pct']>0 and reference['average_exposure_pct']>=90 and reference['unverified_held_marks_preserved']==0
 assert summary['selected_development_lead']==(CANDIDATE if eligible else None)
 negatives={};label='40/'+CANDIDATE
 for mode in ('cash','equity','fee','inventory','allocation_budget','allocation_holdings','source_units','source_rank','target_weight'):
  if mode.startswith('source_') or mode=='target_weight':
   p,t,r=copy.deepcopy((published,targets,receipts));first=expected_execution[0]
   if mode=='source_units':p[r[0]['source_month']]['stocks'][r[0]['selected'][0]]['issued_10k_shares']='999999999999'
   elif mode=='source_rank':r[0]['selected']=list(reversed(r[0]['selected']))
   else:t[CANDIDATE][first]['weights'][next(iter(t[CANDIDATE][first]['weights']))]=.5
   try:reconstruct_formations(p,t,r)
   except (AssertionError,KeyError):negatives[mode]=True
   else:raise AssertionError('formation semantic mutation accepted:'+mode)
   continue
  v=copy.deepcopy(cases[label])
  if mode=='cash':v[0][0]['cash']=str(float(v[0][0]['cash'])+1)
  elif mode=='equity':v[0][-1]['account_value']=str(float(v[0][-1]['account_value'])+1)
  elif mode=='fee':next(o for o in v[1] if float(o['cost'])>0)['cost']='0'
  elif mode=='inventory':v[2][-1]['normalized_units']=str(float(v[2][-1]['normalized_units'])+100)
  elif mode=='allocation_budget':v[3][0]['allocation_receipt']['target_notional_budget']+=100
  else:v[3][0]['holdings_at_decision']={'SZ000001':100}
  try:audit_case(label,summary['results_by_extra_bps_and_family'][label],*v)
  except (AssertionError,KeyError):negatives[mode]=True
  else:raise AssertionError('financial semantic mutation accepted:'+mode)
 assert sha(planfile)==args.expected_plan_sha256
 result={'status':'INDEPENDENT_PRE2026_ISSUED_A_SIZE_SOURCE_FORMATIONS_ALLOCATIONS_AND_CSV_FINANCIALS_VERIFIED','audit_code_sha256':sha(__file__),
  'plan_sha256':sha(planfile),'summary_sha256':sha(root/'summary.json'),'all24_original_HTML_headers_units_and_A_rows_reconstructed':True,'original_mainboard_rows_reconstructed':rowcount,
  'all24_Decimal_rankings_and_targets_receipts_reconstructed':True,'candidate_union_names':68,'all96_prior_close_allocation_intents_reconstructed':True,
  'all_four_CSV_accounts_financially_reconstructed':True,'results_by_profile':audited,'development_gate_passes_independently':eligible,'selected_development_lead':CANDIDATE if eligible else None,
  'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,'imports_project_account_code':False,'source_queries_performed':0,'2026_outcomes_read':False,
  'raw_share_execution_verified':False,'historical_publication_or_arrival_verified':False,'objective_achieved':False,
  'limitations':['Published issue volume uses rounded10000share A-security rows; no company-level A/B/H summation, exact-share or float-cap certification.',
   'Full-following-month lag and filename/build dates do not prove historical publication/arrival.',
   'Qlib normalized inventory, daily-open fills, combined commission+extra rates and at-most0.1raw-equivalent request rounding guard differ from physical intraday execution and split-rounded child fees.',
   'Held marks are checked against frozen normalized quotes and independent suspension-state/last-visible-anchor evidence where absent; this certifies reconstruction, not quote truth or complete corporate-action entitlements.',
   'Candidate-only40bps gate is reconstructed; descriptive control and20bps profile cannot replace it. Any retained candidate requires independent pre2026 physical confirmation before a separately frozen2026 diagnostic.']}
 with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
 print('Independent issued-size audit:24 original sources/ranks,96 prior-close allocations,4 CSV accounts; development gate',eligible)
 return 0
if __name__=='__main__':raise SystemExit(main())
