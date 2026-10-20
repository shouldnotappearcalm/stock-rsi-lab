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
args = parser.parse_args()
root = Path(args.run_dir)
summary = json.loads((root/'summary.json').read_text())
plan_path = Path('experiments/qlib/budgeted-residual-pre2026-plan.json')
plan = json.loads(plan_path.read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(__file__)==plan['independent_csv_audit_code_sha256']
assert summary['plan_sha256'] == sha(plan_path)
assert summary['candidate_budget'] == plan['candidate_budget'] == 1
assert summary['2026_market_values_queried'] is False
assert all(sha(n) == h for n, h in plan['method_code_sha256'].items())
assert sha(root/'targets.json') == plan['initial_targets_sha256'] == summary['targets_sha256']
assert sha(root/'formation_receipts.json') == plan['initial_receipts_sha256'] == summary['formation_receipts_sha256']
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
assert sha(plan['baseline_plan_file'])==plan['baseline_plan_sha256']
assert sha(plan['baseline_summary_file'])==plan['baseline_summary_sha256']

def bounded_float_bytes(raw):
    start=struct.unpack('<f',raw[:4])[0]
    assert start==int(start)
    return raw[:4+4*max(0,calendar.index('2025-12-31')+1-int(start))]

factor_cache = {}


def execution_factor(code, day):
    if code not in factor_cache:
        raw = (provider/'features'/code.lower()/'factor.day.bin').read_bytes()
        raw=bounded_float_bytes(raw)
        values = struct.unpack('<'+'f'*(len(raw)//4), raw)
        factor_cache[code] = (int(values[0]), values[1:])
    start, values = factor_cache[code]
    value = values[calendar.index(day)-start]
    assert math.isfinite(value) and value > 0
    return value


expected_days = [d for d in calendar if '2024-01-02' <= d <= '2025-12-31']
targets = json.loads((root/'targets.json').read_text())
assert set(summary['results_by_extra_bps_and_family']) == {
    f'{e}/{n}' for e in (20, 40) for n in ('market_residual_mom36_12_2', 'eligible_equal_weight', 'total_mom12_2_control')}


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
    assert day<=asof
    key=(code,field)
    if key not in source_cache:
        raw=(provider/'features'/code.lower()/(field+'.day.bin')).read_bytes()
        raw=bounded_float_bytes(raw)
        values=struct.unpack('<'+'f'*(len(raw)//4),raw);assert int(values[0])==values[0]
        source_cache[key]=(int(values[0]),values[1:])
    begin,values=source_cache[key];offset=date_indices[day]-begin
    if not 0<=offset<len(values):return None
    value=values[offset];return value if math.isfinite(value) else None
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
    endpoints=list(by_month.values())[-37:]
    ordinals=[int(d[:4])*12+int(d[5:7]) for d in endpoints]
    assert len(endpoints)==37 and endpoints[-1]==prior and all(b-a==1 for a,b in zip(ordinals,ordinals[1:]))
    market_prices=[field_at('SH000905','close',d,prior) for d in endpoints]
    assert all(v is not None and v>0 for v in market_prices)
    market_returns=[b/a-1 for a,b in zip(market_prices,market_prices[1:])]
    names=sorted(c for c,spans in intervals.items() if any(a<=prior<=b for a,b in spans));scores={};excluded={};coefficients={};total_scores={}
    for code in names:
        current=[field_at(code,f,prior,prior) for f in ('factor','volume','close')]
        if any(v is None or v<=0 for v in current):excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
        closes=[field_at(code,'close',d,prior) for d in endpoints]
        if any(v is None or v<=0 for v in closes):excluded[code]='INCOMPLETE_OR_DEGENERATE_36_MONTH_HISTORY';continue
        ys=[b/a-1 for a,b in zip(closes,closes[1:])];xs=market_returns;n=36
        assert all(math.isfinite(v) for v in (*xs,*ys))
        sx=math.fsum(xs);sy=math.fsum(ys)
        # Independent normal equations rather than the strategy's centered loop.
        denominator=math.fsum(x*x for x in xs)-sx*sx/n
        if not math.isfinite(denominator) or denominator<=1e-24:
            excluded[code]='INCOMPLETE_OR_DEGENERATE_36_MONTH_HISTORY';continue
        beta=(math.fsum(x*y for x,y in zip(xs,ys))-sx*sy/n)/denominator
        alpha=sy/n-beta*sx/n
        adjusted=[ys[j]-beta*xs[j] for j in range(24,35)]
        sigma=statistics.stdev(adjusted)
        if not math.isfinite(sigma) or sigma<=1e-12:
            excluded[code]='INCOMPLETE_OR_DEGENERATE_36_MONTH_HISTORY';continue
        scores[code]=statistics.mean(adjusted)/sigma;coefficients[code]={'beta':beta,'alpha':alpha}
        total_scores[code]=closes[35]/closes[24]-1
    assert len(names)>=200 and len(scores)>=100 and len(scores)>=.8*len(names)
    chosen=sorted(scores,key=lambda c:(-scores[c],c))[:len(scores)//10]
    control=sorted(total_scores,key=lambda c:(-total_scores[c],c))[:len(scores)//10]
    stated=by_execution[day]
    expected={'execution_session':day,'formation_asof':prior,'market_instrument':'SH000905',
        'regression_begin_close':endpoints[0],'regression_return_months':[d[:7] for d in endpoints[1:]],
        'ranking_return_months':[d[:7] for d in endpoints[-12:-1]],'skipped_ranking_month':endpoints[-1][:7],
        'regression_includes_skipped_ranking_month':True,'alpha_subtracted_from_ranking_return':False,
        'historical_members':len(names),'eligible':len(scores),'excluded':excluded,'selected':chosen,
        'control_selected':control,'latest_factor_price_read':prior}
    assert all(stated[k]==v for k,v in expected.items())
    assert set(stated)==set(expected)|{'scores','regression_coefficients','control_total_return_scores'}
    assert set(stated['scores'])==set(scores)==set(stated['regression_coefficients'])==set(stated['control_total_return_scores'])
    for c in scores:
        assert math.isclose(stated['scores'][c],scores[c],rel_tol=1e-10,abs_tol=1e-12)
        assert math.isclose(stated['control_total_return_scores'][c],total_scores[c],rel_tol=1e-10,abs_tol=1e-12)
        for field in ('alpha','beta'):assert math.isclose(stated['regression_coefficients'][c][field],coefficients[c][field],rel_tol=1e-10,abs_tol=1e-12)
    for family,selected in (('market_residual_mom36_12_2',chosen),('eligible_equal_weight',sorted(scores)),('total_mom12_2_control',control)):
        assert targets[family][day]=={'as_of':prior,'weights':{c:.95/len(selected) for c in selected}}
assert all(set(v)==set(expected_execution) for v in targets.values())

# Own currency-space allocation reconstruction; no strategy/planner imports.
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
    rounding_excesses = []
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
    assert sum(not r['verified'] for r in marks) == stated['unverified_held_marks']
    intents=json.loads((folder/'decision_intents.json').read_text())
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
        equivalent(intent['allocation_receipt'],allocation)
        assert intent['latest_decision_price_read']==asof
        assert intent['execution_exchange_queried_for_decision'] is False
    audited[label] = {'status': 'NORMALIZED_CSV_LEDGER_RECONSTRUCTED', **returns,
        'independent_allocation_intents_reconstructed':len(intents),
        'sessions': len(days), 'orders': len(orders), 'unverified_held_marks_preserved': stated['unverified_held_marks'],
        'cash_inventory_fees_market_value_reconciled': True,
        'qlib_guard_rounding_request_excess_count': len(rounding_excesses),
        'max_qlib_raw_equivalent_request_excess': max(rounding_excesses, default=0.),
        'strict_fill_not_above_requested_quantity_verified': not rounding_excesses}
reference = audited['40/market_residual_mom36_12_2']
eligible = (reference['2024_return_pct'] > 0 and reference['2025_return_pct'] > 0
            and reference['average_exposure_pct'] >= 90 and reference['unverified_held_marks_preserved'] == 0)
assert summary['selected_development_lead'] == ('market_residual_mom36_12_2' if eligible else None)
output = Path(args.output); assert not output.exists()
output.write_text(json.dumps({'status': 'INDEPENDENT_BUDGETED_NORMALIZED_CSV_DEVELOPMENT_AUDIT_COMPLETE',
    'audit_script_sha256': sha(Path(__file__)), 'summary_sha256': sha(root/'summary.json'),
    'results_by_profile': audited, 'development_gate_passes_independently': eligible,
    'imports_project_account_code': False, 'raw_share_execution_verified': False,
    'binary_source_formations_independently_reconstructed':len(receipts),
    'scope': 'Independent144priorcloseaccount/lotallocation/orderreceipts and36monthly OLS market beta/intercept, standardized11month beta-adjusted scores excludinglatestmonth, common-pool totalmomentum control, exclusions/ranks/targets fromfloat32source; CSV cash, normalized inventory, fill notional, Qlib fees, held market value, NAV, interval metrics and declared gate; quote truth and raw-share executions not certified',
    '2026_outcomes_read': False, 'objective_achieved': False}, indent=2)+'\n')
print('independent normalized CSV audit', len(audited), 'profiles; passes', eligible)
