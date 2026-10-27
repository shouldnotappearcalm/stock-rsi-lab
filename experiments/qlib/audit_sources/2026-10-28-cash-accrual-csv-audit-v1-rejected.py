"""Separate CSV arithmetic audit; not raw-share or primary-source assurance."""
import argparse,csv,hashlib,json,math
from collections import defaultdict
from fractions import Fraction
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
            need(math.isfinite(q) and q>=0 and fee>=0 and math.isfinite(fee),'finite nonnegative fills/fees')
            need(o['signal_date']<at,'prior-session signal');need((value>=0 if o['side']=='BUY' else value<=0),'signed trade direction')
            if q:close(q*float(o['normalized_price']),abs(value),'fill price/units/trade value')
            else:need(value==0 and fee==0,'unfilled order cannot spend cash')
            expected[o['instrument']]=expected.get(o['instrument'],0)+(q if o['side']=='BUY' else -q)
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
    marks=read(folder/'suspension_mark_audit.json');need(sum(v['verified'] is not True for v in marks)==metrics['unverified_held_marks'],'explicit unresolved held marks')
    return {**computed,'days':len(days),'orders':len(orders),'holding_rows':len(holdings),'unverified_held_marks':metrics['unverified_held_marks']}

def audit(base,root,request,expected):
    need(sha(request)==expected,'frozen request');req=read(request);out=base/req['output_subdir'];t=read(out/'terminal.json');before=tree(out)
    need(t['complete'] is True and t['request_sha256']==expected and t['all_inputs_unchanged'] and t['all_outputs_unchanged'],'complete unchanged development run')
    need(before=={**t['capture_sha256'],'terminal.json':sha(out/'terminal.json')},'entire output closure')
    known={**req['input_sha256'],str(request.resolve()):expected,str(Path(__file__).resolve()):sha(__file__)}
    need(all(sha(p)==h for p,h in known.items()),'all input hashes before audit')
    receipts=read(out/'formation_receipts.json');targets=read(out/'targets.json');docs={d['capture_key']:d for d in req['documents']}
    need(len(receipts)==len(req['formations'])==24,'all24formations')
    for r,q in zip(receipts,req['formations']):
        need(r['execution_session']==q['execution_session'] and r['coverage_pass'] and r['eligible']>=100,'complete fixed structural gate')
        scores={}
        for c,e in r['ranked_source'].items():
            doc=docs[e['capture_key']];case=read(base/'cash-accrual-cfo-corpus-v3-20261027/cases'/(e['capture_key']+'.json'));report=case['report'];p=report['parsed'];y=doc['effective_fiscal_year'];at=f'{y}-12-31';prior=f'{y-1}-12-31'
            need(report['record_id']==req['approved_record_ids'][e['capture_key']]==e['record_id'] and report['source_sha256']==e['source_sha256'],'approved source identity')
            ni=Fraction(p['income'][at]['net_profit']['value_CNY']);cfo=Fraction(p['cashflows'][at]['operating_cashflow']['value_CNY']);a=Fraction(p['balances'][prior]['value_CNY']);b=Fraction(p['balances'][at]['value_CNY'])
            score=(ni-cfo)/((a+b)/2);need(score==Fraction(e['score_fraction']),'separate exact financial ratio');scores[c]=score
            visible=[d for d in req['documents'] if d['instrument']==c and d['day']<r['formation_asof']]
            need((y,doc['day'])==max((d['effective_fiscal_year'],d['day']) for d in visible),'no older source fallback')
        for name,selection in r['selections'].items():
            ordered=sorted(scores,key=lambda c:(scores[c],c)) if name==req['candidate'] else sorted(scores,key=lambda c:(-scores[c],c))
            expected_codes=sorted(scores) if name=='eligible_equal_weight' else ordered[:len(scores)//10]
            need(list(selection)==expected_codes,'exact frozen primary/control selection')
            v=targets[name][r['execution_session']];need(v['as_of']==r['formation_asof'] and list(v['weights'])==expected_codes,'unaltered target clock/selection')
            for w in v['weights'].values():need(math.isclose(w,.95/len(selection),rel_tol=1e-12,abs_tol=1e-12),'95percent equal targets')
    sessions=[s for s in (base/req['provider_relative']/'calendars/day.txt').read_text().splitlines() if '2024-01-02'<=s<='2025-12-31'];need(len(sessions)==485,'actual485sessions')
    cases={k:audit_case(out/k,v,sessions) for k,v in t['results_by_extra_bps'].items()};p=cases['40/'+req['candidate']]
    passes=min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90 and p['unverified_held_marks']==0
    need(t['selected_development_lead']==(req['candidate'] if passes else None),'primary-only higher-cost acceptance')
    need(all(sha(p)==h for p,h in known.items()) and tree(out)==before,'all inputs/outputs unchanged after audit')
    proof={'status':'PASS_SEPARATE_CSV_ARITHMETIC_AND_EXACT_FACTOR_TARGET_CHECKS','request_sha256':expected,'cases':cases,
           'development_screen_passes':passes,'all_input_sha256':known,'all_output_sha256':before,
           'all_inputs_outputs_unchanged':True,'raw_share_execution_verified':False,'historical_arrival_verified':False,'2026_values_read':False,'objective_achieved':False,
           'limits':'Same-author audit of saved normalized CSVs and prior source cases; not independent primary/execution/account or raw-share assurance'}
    folder=base/'cash-accrual-development-root-audit-v1-20261028';need(not folder.exists(),'fresh audit only');folder.mkdir();(folder/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':proof['status'],'development_screen_passes':passes,'primary40':p}),flush=True)
    return proof

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args();audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.request).resolve(),a.expected_request_sha256)
if __name__=='__main__':main()
