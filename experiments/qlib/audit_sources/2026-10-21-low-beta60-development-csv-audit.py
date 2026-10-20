"""Stdlib-only CSV ledger reconstruction; not a raw-share execution audit."""
import argparse
import csv
import hashlib
import json
import math
import struct
import statistics
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--run-dir', required=True)
parser.add_argument('--provider-uri', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--formations-only', action='store_true')
parser.add_argument('--gap-states')
args = parser.parse_args()
root = Path(args.run_dir)
summary = json.loads((root/'summary.json').read_text())
plan_path = Path('experiments/qlib/low-beta60-pre2026-formations-request.json' if args.formations_only else 'experiments/qlib/low-beta60-pre2026-plan.json')
plan = json.loads(plan_path.read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not Path(args.output).exists(), 'preserve audit outputs'
if args.formations_only:
    assert sha(plan_path) == '07a91056c263e112f7d0bc6fa52b6f6bb73ddbd34b526ef2138e0e62dd543656'
    assert summary['status'] == 'LOW_BETA60_FORMATIONS_ONLY_NO_PORTFOLIO_ROI'
    assert summary['request_sha256'] == sha(plan_path) and summary['portfolio_returns_computed'] is False
    assert sha(root/'targets.json') == summary['target_sha256']
    assert sha(root/'formation_receipts.json') == summary['receipt_sha256']
else:
    assert plan['status'] == 'FROZEN_BEFORE_LOW_BETA60_OUTCOMES' and plan['families'] == ['low_beta60']
    assert plan['capital_CNY'] == 1000000 and plan['extra_bps'] == [20,40]
    assert sha(__file__) == plan['independent_csv_audit_code_sha256']
    assert summary['plan_sha256'] == sha(plan_path)
    assert sha(root/'targets.json') == plan['initial_targets_sha256'] == summary['targets_sha256']
    assert sha(root/'formation_receipts.json') == plan['initial_receipts_sha256'] == summary['formation_receipts_sha256']
assert summary['candidate_budget'] == plan['candidate_budget'] == 1
assert summary['2026_market_values_queried'] is False
assert all(sha(n) == h for n,h in plan['method_code_sha256'].items())
assert sha(plan['design_file']) == plan['design_sha256']
calendar_file = Path(args.provider_uri)/'calendars/day.txt'
assert sha(calendar_file) == plan['input_sha256']['calendars/day.txt']
calendar = calendar_file.read_text().splitlines()
provider = Path(args.provider_uri)
for relative, expected in plan['input_sha256'].items():
    if relative != 'price_files': assert sha(provider/relative) == expected
codes = set()
for line in (provider/'instruments/csi500.txt').read_text().splitlines():
    code, first, last = line.split()
    if (code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003'))
            and first <= '2025-12-31' and last >= '2023-12-29'): codes.add(code)
files = [Path('instruments/all.txt')]
for code in sorted(codes):
    files.extend(Path('features')/code.lower()/(f+'.day.bin')
                 for f in ('open', 'high', 'low', 'close', 'volume', 'factor', 'amount', 'adjclose'))
files.append(Path('features/sh000905/adjclose.day.bin'))
prices_digest = hashlib.sha256()
for relative in files:
    prices_digest.update(relative.as_posix().encode()+b'\0')
    prices_digest.update((provider/relative).read_bytes()); prices_digest.update(b'\0')
assert prices_digest.hexdigest() == plan['input_sha256']['price_files']
expected_days = [d for d in calendar if '2024-01-02' <= d <= '2025-12-31']
targets = json.loads((root/'targets.json').read_text())


def close(a, b, *, money=False):
    assert math.isfinite(a) and math.isfinite(b)
    assert math.isclose(a, b, rel_tol=1e-9, abs_tol=.01 if money else 1e-6), (a, b)


def read(folder, name):
    with (folder/name).open() as stream:
        return list(csv.DictReader(stream))


# Independent formation from original float32 files; no project strategy imports.
assert sha(provider/'features/sh000905/close.day.bin')==plan['market_close_sha256']
source_cache={};date_indices={d:i for i,d in enumerate(calendar)};intervals=defaultdict(list)
for line in (provider/'instruments/csi500.txt').read_text().splitlines():
    c,a,b=line.split()
    if c in codes:intervals[c].append((a,b))
def field_at(code,field,day,asof):
    assert day <= asof <= '2025-12-31', 'future date-indexed values forbidden'
    key=(code,field)
    if key not in source_cache:
        raw=(provider/'features'/code.lower()/(field+'.day.bin')).read_bytes()
        assert len(raw) % 4 == 0 and len(raw) >= 8
        begin = struct.unpack_from('<f', raw, 0)[0]; assert int(begin) == begin
        source_cache[key]=(int(begin),raw)
    begin,raw=source_cache[key];offset=date_indices[day]-begin
    if not 0 <= offset < len(raw)//4-1:return None
    # Decode ONLY the specifically requested pre2026 scalar; full bytes are hashed for binding.
    value=struct.unpack_from('<f',raw,4*(offset+1))[0]
    return value if math.isfinite(value) else None

def execution_factor(code,day):
    value=field_at(code,'factor',day,day)
    assert value is not None and value>0
    return value

receipts=json.loads((root/'formation_receipts.json').read_text());by_execution={r['execution_session']:r for r in receipts}
expected_execution=[d for i,d in enumerate(calendar) if '2024-01-02'<=d<='2025-12-31' and d[:7]!=calendar[i-1][:7]]
assert len(receipts)==len(by_execution)==len(expected_execution)==24
for day in expected_execution:
    index=date_indices[day];prior=calendar[index-1]
    year,month=int(day[:4]),int(day[5:7])
    expected=(year,month-1) if month>1 else (year-1,12)
    assert (int(prior[:4]),int(prior[5:7]))==expected
    by_month={}
    for d in calendar[:index]:by_month[d[:7]]=d
    endpoints=list(by_month.values())[-61:]
    ordinals=[int(d[:4])*12+int(d[5:7]) for d in endpoints]
    assert len(endpoints)==61 and endpoints[-1]==prior and all(b-a==1 for a,b in zip(ordinals,ordinals[1:]))
    market_prices=[field_at('SH000905','close',d,prior) for d in endpoints]
    assert all(v is not None and v>0 for v in market_prices)
    market_returns=[b/a-1 for a,b in zip(market_prices,market_prices[1:])]
    names=sorted(c for c,spans in intervals.items() if any(a<=prior<=b for a,b in spans));scores={};excluded={};coefficients={};total_scores={}
    for code in names:
        current=[field_at(code,f,prior,prior) for f in ('factor','volume','close')]
        if any(v is None or v<=0 for v in current):excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
        closes=[field_at(code,'close',d,prior) for d in endpoints]
        if any(v is None or v<=0 for v in closes):excluded[code]='INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY';continue
        ys=[b/a-1 for a,b in zip(closes,closes[1:])];xs=market_returns;n=60
        assert all(math.isfinite(v) for v in (*xs,*ys))
        sx=math.fsum(xs);sy=math.fsum(ys)
        # Independent normal equations rather than the strategy's centered loop.
        denominator=math.fsum(x*x for x in xs)-sx*sx/n
        if not math.isfinite(denominator) or denominator<=1e-24:
            excluded[code]='INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY';continue
        beta=(math.fsum(x*y for x,y in zip(xs,ys))-sx*sy/n)/denominator
        alpha=sy/n-beta*sx/n
        stock_variance=math.fsum(y*y for y in ys)-sy*sy/n
        if not math.isfinite(stock_variance) or stock_variance<=1e-24:
            excluded[code]='INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY';continue
        vol=math.sqrt(stock_variance/59*12)
        if not all(math.isfinite(v) for v in (beta,alpha,vol)):
            excluded[code]='INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY';continue
        scores[code]=beta;coefficients[code]={'beta':beta,'alpha':alpha}
        total_scores[code]=vol
    assert len(names)>=200 and len(scores)>=100 and len(scores)>=.5*len(names)
    chosen=sorted(scores,key=lambda c:(scores[c],c))[:len(scores)//10]
    control=sorted(total_scores,key=lambda c:(total_scores[c],c))[:len(scores)//10]
    stated=by_execution[day]
    expected={'execution_session':day,'formation_asof':prior,'market_instrument':'SH000905',
        'regression_begin_close':endpoints[0],'return_months':[d[:7] for d in endpoints[1:]],
        'historical_members':len(names),'eligible':len(scores),'excluded':excluded,'selected':chosen,
        'control_selected':control,'latest_factor_price_read':prior}
    assert all(stated[k]==v for k,v in expected.items())
    assert set(stated)==set(expected)|{'scores','regression_coefficients','control_volatility_scores'}
    assert set(stated['scores'])==set(scores)==set(stated['regression_coefficients'])==set(stated['control_volatility_scores'])
    for c in scores:
        assert math.isclose(stated['scores'][c],scores[c],rel_tol=1e-10,abs_tol=1e-12)
        assert math.isclose(stated['control_volatility_scores'][c],total_scores[c],rel_tol=1e-10,abs_tol=1e-12)
        for field in ('alpha','beta'):assert math.isclose(stated['regression_coefficients'][c][field],coefficients[c][field],rel_tol=1e-10,abs_tol=1e-12)
    for family,selected in (('low_beta60',chosen),('eligible_equal_weight',sorted(scores)),('low_vol60_control',control)):
        assert targets[family][day]=={'as_of':prior,'weights':{c:.95/len(selected) for c in selected}}
assert all(set(v)==set(expected_execution) for v in targets.values())

assert set(targets) == {'low_beta60','eligible_equal_weight','low_vol60_control'}
if args.formations_only:
    report={'status':'INDEPENDENT_LOW_BETA60_FORMATIONS_AUDIT_PASSED',
        'audit_script_sha256':sha(__file__), 'request_sha256':sha(plan_path),
        'summary_sha256':sha(root/'summary.json'), 'targets_sha256':sha(root/'targets.json'),
        'receipts_sha256':sha(root/'formation_receipts.json'), 'formations':len(receipts),
        'eligible_range':[min(r['eligible'] for r in receipts),max(r['eligible'] for r in receipts)],
        'independent_equations':'60 monthly normal-equation OLS with intercept; annualized sample variance; signed ascending beta; code ties',
        'source_method_design_bindings_verified':True, 'all_exclusions_ranks_controls_weights_match':True,
        'date_indexed_2026_values_read':False, 'physical_full_source_bytes_hashed':True,
        'portfolio_returns_computed':False,'imports_project_code':False,'network_queries':0,'discrepancies':[]}
    with Path(args.output).open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report));raise SystemExit(0)
assert set(summary['results_by_extra_bps_and_family']) == {
    f'{e}/{n}' for e in (20,40) for n in ('low_beta60','eligible_equal_weight','low_vol60_control')}
assert args.gap_states, 'source gap states required for the account audit'
gapdir=Path(args.gap_states);assert sha(gapdir/'manifest.json')==plan['gap_state_manifest_sha256']
gapmanifest=json.loads((gapdir/'manifest.json').read_text())
assert gapmanifest['window']==['2023-12-29','2025-12-31'] and gapmanifest['2026_market_values_queried'] is False
states={}
for code,h in gapmanifest['per_code_sha256'].items():
    packetpath=gapdir/'codes'/(code+'.json');assert sha(packetpath)==h
    packet=json.loads(packetpath.read_text());assert packet['instrument']==code
    states[code]={r['date']:r for r in packet['rows']}
    assert len(states[code])==len(packet['rows']) and all('2023-12-29'<=d<='2025-12-31' for d in states[code])

def source_mark(code,day,mark):
    result={'instrument':code,'session':day,'marked_normalized_price':mark,'verified':False}
    rows=states.get(code,{})
    if rows.get(day,{}).get('tradestatus')!='0':return result|{'reason':'NO_INDEPENDENT_SUSPENDED_STATE'}
    prior=next((d for d in reversed(calendar[:date_indices[day]]) if (field_at(code,'close',d,day) or 0)>0),None)
    if prior is None:return result|{'reason':'NO_PRIOR_VISIBLE_CLOSE'}
    value=field_at(code,'close',prior,day);factor=field_at(code,'factor',prior,day)
    try:anchor=float(rows.get(prior,{}).get('close',''))
    except (ValueError,TypeError):anchor=math.nan
    if (factor is None or factor<=0 or not math.isfinite(anchor)
        or not math.isclose(value/factor,anchor,abs_tol=.005,rel_tol=1e-6)):
        return result|{'reason':'CROSS_SOURCE_LAST_VISIBLE_PRICE_NOT_VERIFIED'}
    if not math.isfinite(mark) or not math.isclose(mark,value,abs_tol=1e-8,rel_tol=1e-8):
        return result|{'reason':'MARK_DIFFERS_FROM_LAST_VISIBLE_CLOSE'}
    return result|{'verified':True,'classification':'INDEPENDENT_HALT_LAST_VISIBLE_MARK',
        'last_visible_close_date':prior,'last_visible_normalized_close':value,'source_tradestatus':'0',
        'actual_quote_on_suspended_day_created':False}

audited = {}
for label, stated in summary['results_by_extra_bps_and_family'].items():
    extra, name = label.split('/'); folder = root/label
    for filename, h in stated['artifact_sha256'].items():
        assert sha(folder/filename) == h
    days = read(folder, 'days.csv'); orders = read(folder, 'orders.csv'); holdings = read(folder, 'holdings.csv')
    assert [r['session'] for r in days] == expected_days
    by_order, by_held = defaultdict(list), defaultdict(list)
    for row in orders: by_order[row['session']].append(row)
    for row in holdings: by_held[row['session']].append(row)
    cash = initial = float(plan['capital_CNY']); inventory = defaultdict(float)
    nav = {}; exposures = []; fees = turnover = 0.; peak = initial; dd = 0.
    rounding_excesses = []; reconstructed_marks=[]
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
            if q:
                price = float(order['normalized_price']); sign = 1 if order['side'] == 'BUY' else -1
                close(price,field_at(order['instrument'],'open',d,d))
                close(amount, sign*q*price, money=True)
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
            quote=field_at(held['instrument'],'close',d,d)
            if quote is None or quote<=0:reconstructed_marks.append(source_mark(held['instrument'],d,float(held['normalized_price'])))
            else:close(float(held['normalized_price']),quote)
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
    marks = json.loads((folder/'suspension_mark_audit.json').read_text())
    assert marks == reconstructed_marks, 'source gap mark classifications changed'
    assert sum(not r['verified'] for r in marks) == stated['unverified_held_marks']
    audited[label] = {'status': 'NORMALIZED_CSV_LEDGER_RECONSTRUCTED', **returns,
        'sessions': len(days), 'orders': len(orders), 'unverified_held_marks_preserved': stated['unverified_held_marks'],
        'cash_inventory_fees_market_value_reconciled': True,
        'qlib_guard_rounding_request_excess_count': len(rounding_excesses),
        'max_qlib_raw_equivalent_request_excess': max(rounding_excesses, default=0.),
        'strict_fill_not_above_requested_quantity_verified': not rounding_excesses}
reference = audited['40/low_beta60']
eligible = (reference['2024_return_pct'] > 0 and reference['2025_return_pct'] > 0
            and reference['average_exposure_pct'] >= 90 and reference['unverified_held_marks_preserved'] == 0)
assert summary['selected_development_lead'] == ('low_beta60' if eligible else None)
output = Path(args.output); assert not output.exists()
output.write_text(json.dumps({'status': 'INDEPENDENT_NORMALIZED_CSV_DEVELOPMENT_AUDIT_COMPLETE',
    'audit_script_sha256': sha(Path(__file__)), 'summary_sha256': sha(root/'summary.json'),
    'results_by_profile': audited, 'development_gate_passes_independently': eligible,
    'imports_project_account_code': False, 'raw_share_execution_verified': False,
    'binary_source_formations_independently_reconstructed':len(receipts),
    'scope': 'Independent60monthly signed OLS beta/intercept, same60month volatility control, exclusions/ranks/targets fromfloat32source; CSV cash, normalized inventory, fill notional, Qlib fees, held market value, NAV, interval metrics and declared gate; quote truth and raw-share executions not certified',
    'source_gap_marks_independently_reconstructed':True, 'date_indexed_2026_values_read':False, 'physical_full_source_bytes_hashed':True, '2026_outcomes_read': False, 'objective_achieved': False}, indent=2)+'\n')
print('independent normalized CSV audit', len(audited), 'profiles; passes', eligible)
