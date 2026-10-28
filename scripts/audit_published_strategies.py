"""Separate stdlib CSV and source-window audit. Same author, not independent assurance.

Arithmetic ledger checks reuse the previously fixed signed-SELL audit algorithm.
Production strategy, Qlib, signal and account modules are never imported.
"""
import argparse,csv,hashlib,json,math,struct
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

def need(v,why):
    if not v:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(Path(p).rglob('*')) if f.is_file()}
def read(p):return json.loads(Path(p).read_text())
def close(a,b,why):need(math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=.02),why)
def rows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))

def audit_case(folder,metrics,sessions,initial=1000000):
    days=rows(folder/'days.csv');orders=rows(folder/'orders.csv');holdings=rows(folder/'holdings.csv')
    need([r['session'] for r in days]==sessions,'complete ordered account calendar')
    by_order=defaultdict(list);by_holding=defaultdict(list)
    for v in orders:by_order[v['session']].append(v)
    for v in holdings:by_holding[v['session']].append(v)
    need(set(by_order)<=set(sessions) and set(by_holding)<=set(sessions),'no extra account dates')
    cash=float(initial);owned={};nav=initial;peak=initial;dd=0;exposure=[];year_end={};total_cost=0;turnover=0
    for d in days:
        at=d['session'];cost=0;signed=0;today=by_order[at];expected=dict(owned)
        for o in today:
            need(o['side'] in ('BUY','SELL'),'typed side');q=float(o['filled_normalized_units']);value=float(o['signed_trade_value']);fee=float(o['cost'])
            need(math.isfinite(q) and (q>=0 if o['side']=='BUY' else q<=0) and fee>=0 and math.isfinite(fee),'finite side-consistent signed units and nonnegative fees')
            need(o['signal_date']<at,'prior-session signal');need((value>=0 if o['side']=='BUY' else value<=0),'signed trade direction')
            if q:close(abs(q)*float(o['normalized_price']),abs(value),'fill price/units/trade value')
            else:need(value==0 and fee==0,'unfilled order cannot spend cash')
            expected[o['instrument']]=expected.get(o['instrument'],0)+q
            cost+=fee;signed+=value;turnover+=abs(value)
        close(cost,d['cost'],'daily fee sum');close(cash-signed-cost,d['cash'],'cash conservation');cash=float(d['cash']);total_cost+=cost
        held=by_holding[at];need(len(held)==len({h['instrument'] for h in held}),'unique daily holding')
        current={h['instrument']:float(h['normalized_units']) for h in held};stock=0
        for c in set(expected)|set(current):
            need(math.isclose(expected.get(c,0),current.get(c,0),rel_tol=1e-8,abs_tol=1e-6),'normalized inventory conservation')
        for h in held:
            need(float(h['normalized_units'])>=0 and float(h['normalized_price'])>0,'nonnegative long holding/positive mark')
            close(float(h['normalized_units'])*float(h['normalized_price']),h['value'],'holding mark arithmetic');stock+=float(h['value'])
        close(stock,d['stock_value'],'daily stock value');close(cash+stock,d['account_value'],'daily NAV')
        owned=current;nav=float(d['account_value']);need(nav>0 and math.isfinite(nav),'positive finite NAV')
        exposure.append(stock/nav*100);peak=max(peak,nav);dd=min(dd,(nav/peak-1)*100);year_end[at[:4]]=nav
    computed={'2024_return_pct':(year_end['2024']/initial-1)*100,'2025_return_pct':(year_end['2025']/year_end['2024']-1)*100,
              'average_exposure_pct':sum(exposure)/len(exposure),'max_drawdown_pct':dd,'final_account_CNY':nav,
              'cost_pct_initial':total_cost/initial*100,'turnover_x_initial':turnover/initial}
    for k,v in computed.items():close(v,metrics[k],'independent metric '+k)
    marks=read(folder/'missing-held-marks.json');need(len(marks)==metrics['unverified_held_marks'],'explicit unresolved held marks')
    return {**computed,'days':len(days),'orders':len(orders),'holding_rows':len(holdings),'unverified_held_marks':metrics['unverified_held_marks']}


def gate(row):
    return row['2024_return_pct']>0 and row['2025_return_pct']>0 and row['average_exposure_pct']>=90 and row['unverified_held_marks']==0


def audit(root,provider,folder,request,expected):
    need(sha(request)==expected,'frozen request SHA256')
    req=read(request);terminal=read(folder/'terminal.json');before=tree(folder)
    need(terminal['complete'] is True and terminal['all_inputs_unchanged'] is True and terminal['request_sha256']==expected,'complete unchanged run')
    need(terminal['2026_values_read'] is False and terminal['2026_return_pct'] is None and not terminal['investment_admitted'],'no forward results or investment qualification')
    need(before=={**terminal['artifact_sha256'],'terminal.json':sha(folder/'terminal.json')},'whole actual output identity')
    need(tree(provider)==req['provider_sha256'],'whole frozen physically capped provider')
    need(all(sha(root/n)==h for n,h in req['method_and_source_sha256'].items()),'all frozen methods/source/skills')
    calendar=(provider/'calendars/day.txt').read_text().splitlines();need(calendar[-1]=='2025-12-31','no2026quote calendar')
    days=[d for d in calendar if '2024-01-02'<=d<='2025-12-31'];need(len(days)==485,'485actual account sessions')
    indices={d:i for i,d in enumerate(calendar)};cache={}
    def value(c,f,d):
        key=(c,f)
        if key not in cache:
            raw=(provider/'features'/c.lower()/(f+'.day.bin')).read_bytes();vals=struct.unpack('<'+str(len(raw)//4)+'f',raw);cache[key]=(int(vals[0]),vals[1:])
        start,values=cache[key];offset=indices[d]-start
        v=values[offset] if 0<=offset<len(values) else float('nan')
        return v if math.isfinite(v) else None
    checks={}
    for label,metric in terminal['results'].items():
        case=folder/label;cfg=req['configs'][label.split('/')[1]];ledger=audit_case(case,metric,days)
        intents=read(case/'decision_intents.json');need(len(intents)==485,'all daily snapshots retained')
        dayrows=rows(case/'days.csv');heldrows=rows(case/'holdings.csv');by_hold=defaultdict(dict)
        for h in heldrows:by_hold[h['session']][h['instrument']]=float(h['normalized_units'])
        prior={d['session']:d for d in dayrows};rows_checked=0
        for execution,intent in zip(days,intents):
            asof=calendar[indices[execution]-1]
            need(intent['execution_session']==execution and intent['as_of']==asof+'T15:05:00+08:00' and intent['latest_decision_price_read']==asof,'exact prior-close wake')
            need(intent['execution_exchange_queried_for_decision'] is False,'no execution-day sizing')
            payload={k:v for k,v in intent.items() if k!='snapshot_sha256'}
            encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
            need(hashlib.sha256(encoded).hexdigest()==intent['snapshot_sha256'],'actual snapshot identity')
            expected_equity=float(prior[asof]['account_value']) if asof in prior else 1000000
            expected_cash=float(prior[asof]['cash']) if asof in prior else 1000000
            close(intent['equity_at_decision'],expected_equity,'prior equity');close(intent['cash_at_decision'],expected_cash,'prior cash')
            expected_held=by_hold.get(asof,{})
            need(set(expected_held)==set(intent['holdings_at_decision']),'prior actual inventory identities')
            for c,q in expected_held.items():close(intent['holdings_at_decision'][c],q,'prior actual inventory')
            for c in cfg['symbols']:
                history=[]
                for d in reversed(calendar[:indices[execution]]):
                    v=value(c,'close',d);volume=value(c,'volume',d)
                    if v is not None and v>0 and volume is not None and volume>0:
                        history.append([d,v])
                        if len(history)==cfg['history']:break
                history.reverse();need(history==intent['histories'][c] and all(d<=asof for d,_ in history),'literal complete source history/no future')
                close(intent['known_closes'][c],value(c,'close',asof),'known close');close(intent['known_factors'][c],value(c,'factor',asof),'known factor')
                rows_checked+=len(history)
            # The indicator math has separately generated TA-Lib witnesses;
            # this audit verifies their actual data/clock binding, not a second
            # independently implemented MACD algorithm.
        bps=int(label.split('/')[0])
        for order in rows(case/'orders.csv'):
            amount=abs(float(order['signed_trade_value']));fee=float(order['cost'])
            if amount:
                rate=(5 if order['side']=='BUY' else 15)/10000+bps/10000
                close(fee,max(5,amount*rate),'registered side/minimum/stress fee')
        checks[label]={**ledger,'snapshots_checked':len(intents),'literal_history_values_checked':rows_checked,'snapshot_sha256_checked':True,'fee_formula_checked':True}
    passed=[n for n in req['candidates'] if gate(checks['40/'+n])]
    need(passed==terminal['passed_development_screen'],'same higher-cost screening decision')
    need(tree(folder)==before and tree(provider)==req['provider_sha256'] and all(sha(root/n)==h for n,h in req['method_and_source_sha256'].items()),'all inputs/outputs unchanged after audit')
    return {'status':'PASS_ALL_SIX_CSV_LEDGERS_AND_PRIOR_CLOSE_SOURCE_SNAPSHOTS_NOT_RAW_QUALIFICATION',
        'request_sha256':expected,'terminal_sha256':sha(folder/'terminal.json'),'cases':checks,
        'passed_development_screen':passed,'2026_values_read':False,'all_inputs_outputs_unchanged':True,
        'imports_production_signal_account_or_qlib':False,'same_researcher_not_independent_assurance':True}


def main():
    p=argparse.ArgumentParser()
    for name in ('provider','run-dir','request','expected-sha256','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    result=audit(root,Path(a.provider),Path(a.run_dir),Path(a.request),a.expected_sha256)
    with Path(a.out).open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(result['status'])


if __name__=='__main__':main()
