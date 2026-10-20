"""Decompose saved pre2026 order-rounding shortfalls; no new portfolio returns."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import struct
from collections import Counter
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--run-dir',required=True);p.add_argument('--provider-uri',required=True);p.add_argument('--output',required=True)
a=p.parse_args();root=Path(a.run_dir);provider=Path(a.provider_uri);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(root/'summary.json')=='734b4b22f18530623dee5d7efeb54ea5d37f67183ac2e14a0a912b53415437c9'
summary=json.loads((root/'summary.json').read_text());label='40/market_residual_mom36_12_2';folder=root/label
for name,h in summary['results_by_extra_bps_and_family'][label]['artifact_sha256'].items():assert sha(folder/name)==h
calendar=(provider/'calendars/day.txt').read_text().splitlines();indices={d:i for i,d in enumerate(calendar)}
cache={};hashes={'calendars/day.txt':sha(provider/'calendars/day.txt')}
def quote(code,field,day):
    assert day<='2025-12-31'
    relative=f'features/{code.lower()}/{field}.day.bin'
    if relative not in cache:
        raw=(provider/relative).read_bytes();hashes[relative]=sha(provider/relative)
        start=struct.unpack('<f',raw[:4])[0];assert start==int(start)
        raw=raw[:4+4*max(0,indices['2025-12-31']+1-int(start))]
        values=struct.unpack('<'+'f'*(len(raw)//4),raw)
        cache[relative]=(int(start),values[1:])
    start,values=cache[relative];offset=indices[day]-start
    assert 0<=offset<len(values)
    v=values[offset]
    assert math.isfinite(v) and v>0
    return v
intents=json.loads((folder/'decision_intents.json').read_text())
days={r['session']:r for r in csv.DictReader((folder/'days.csv').open())}
orders=list(csv.DictReader((folder/'orders.csv').open()));rows=[]
for i in intents:
    d=i['execution_session'];asof=i['as_of_close_convention'][:10]
    assert '2024-01-02'<=d<='2025-12-31' and asof==calendar[indices[d]-1]
    equity=i['equity_at_decision'];post=dict(i['holdings_at_decision'])
    for o in i['orders']:post[o['instrument']]=post.get(o['instrument'],0)+(1 if o['side']=='BUY' else -1)*o['normalized_units']
    ideal=floor=planned=0.
    for c,w in i['target_weights'].items():
        price=quote(c,'close',asof);factor=quote(c,'factor',asof)
        ideal+=equity*w;floor+=math.floor(equity*w/price*factor/100+1e-10)*100/factor*price
        planned+=post.get(c,0.)*price
    rows.append({'execution_session':d,'formation_asof':asof,'target_notional_pct':100*ideal/equity,
        'target_floor_shortfall_pct':100*(ideal-floor)/equity,
        'incremental_buy_floor_shortfall_pct':100*(floor-planned)/equity,
        'planned_target_notional_pct':100*planned/equity,
        'recorded_execution_close_exposure_pct':100*float(days[d]['stock_value'])/float(days[d]['account_value']),
        'zero_fill_buy_orders':sum(o['session']==d and o['side']=='BUY' and float(o['filled_normalized_units'])==0 for o in orders)})
assert len(rows)==24
counts=Counter(o['side'] for o in orders if float(o['filled_normalized_units'])==0)
result={'status':'PRE2026_SAVED_ORDER_LOT_SHORTFALL_DECOMPOSITION_COMPLETE','audit_code_sha256':sha(__file__),
    'summary_sha256':sha(root/'summary.json'),'profile':label,'source_files_sha256':hashes,'formations':rows,
    'mean_target_floor_shortfall_pct':statistics.mean(r['target_floor_shortfall_pct'] for r in rows),
    'mean_incremental_buy_floor_shortfall_pct':statistics.mean(r['incremental_buy_floor_shortfall_pct'] for r in rows),
    'mean_planned_target_notional_pct':statistics.mean(r['planned_target_notional_pct'] for r in rows),
    'mean_recorded_execution_close_exposure_pct':statistics.mean(r['recorded_execution_close_exposure_pct'] for r in rows),
    'zero_fill_orders_by_side':dict(counts),'new_portfolio_returns_computed':False,'2026_values_decoded':False,
    'source_or_original_experiment_changed':False,'objective_achieved':False,
    'scope':'Saved pre2026 target-name order intentions at priorclose; executionclose exposure and zero fills only descriptive, not an additive causal PnL attribution; outside-target inventory and intramonth drift not assigned to rounding'}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print(result['status'],result['mean_target_floor_shortfall_pct'],result['mean_incremental_buy_floor_shortfall_pct'])
