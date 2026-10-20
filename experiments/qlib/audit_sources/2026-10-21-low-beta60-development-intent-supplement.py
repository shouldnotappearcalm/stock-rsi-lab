"""Independent stdlib intent boundary and tamper audit; no strategy execution."""
import argparse
import copy
import csv
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

PLAN_SHA='75f1398abbe5c177e7164b2f7247eea444534f97ce45f6893798b2cb68a7068f'
BASE_AUDITOR_SHA='cf16d01041e95415c90469ab7ecd12846b8f3f3f50e2b12c1f31769685df7ba5'

def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def near(a,b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-6),(a,b)
def rows(path):
    with Path(path).open() as stream:return list(csv.DictReader(stream))

class Source:
    def __init__(self,path):
        self.root=Path(path);self.calendar=(self.root/'calendars/day.txt').read_text().splitlines()
        self.indices={d:i for i,d in enumerate(self.calendar)};self.cache={};self.max_read=''
    def value(self,code,field,day):
        assert day<='2025-12-31';self.max_read=max(self.max_read,day);key=code,field
        if key not in self.cache:self.cache[key]=(self.root/'features'/code.lower()/(field+'.day.bin')).read_bytes()
        raw=self.cache[key];start=struct.unpack_from('<f',raw)[0];assert int(start)==start
        offset=self.indices[day]-int(start);assert 0<=offset<len(raw)//4-1
        value=struct.unpack_from('<f',raw,4*(offset+1))[0];assert math.isfinite(value) and value>0
        return value

def verify(packet,targets,source,extra):
    """Checks only decoded data and independent arithmetic; no hash checks here."""
    days,orders,holdings,intents=(packet[k] for k in ('days','orders','holdings','intents'))
    expected=[d for d in source.calendar if '2024-01-02'<=d<='2025-12-31']
    assert [d['session'] for d in days]==expected
    byday={r['session']:r for r in days};held=defaultdict(dict);byorder=defaultdict(list)
    for row in holdings:
        assert row['instrument'] not in held[row['session']]
        held[row['session']][row['instrument']]=float(row['normalized_units'])
    for row in orders:byorder[row['session']].append(row)
    cash=1000000.;inventory=defaultdict(float);nav={}
    for day in days:
        d=day['session'];daily_fee=0.
        for order in byorder[d]:
            q=abs(float(order['filled_normalized_units']));side=order['side'];assert side in ('BUY','SELL')
            sign=1 if side=='BUY' else -1;gross=float(order['signed_trade_value']);fee=float(order['cost'])
            if q:
                price=source.value(order['instrument'],'open',d);near(gross,sign*q*price)
                rate=(.0005 if side=='BUY' else .0015)+extra/10000
                near(fee,max(5.,abs(gross)*rate));inventory[order['instrument']]+=sign*q
                assert inventory[order['instrument']]>=-1e-6
            else:near(gross,0.);near(fee,0.)
            cash-=gross+fee;daily_fee+=fee
        near(cash,float(day['cash']));near(daily_fee,float(day['cost']))
        for c in set(inventory)|set(held[d]):near(inventory[c],held[d].get(c,0.))
        value=sum(float(r['value']) for r in holdings if r['session']==d)
        nav[d]=cash+value;near(nav[d],float(day['account_value']))
    assert len(intents)==24 and [i['execution_session'] for i in intents]==list(targets)
    count=0
    for it in intents:
        day=it['execution_session'];prior=source.calendar[source.indices[day]-1]
        equity=nav[prior] if prior in nav else 1000000.;owned=held[prior];weights=targets[day]['weights']
        assert targets[day]['as_of']==prior and it['target_weights']==weights
        near(it['equity_at_decision'],equity);assert set(it['holdings_at_decision'])==set(owned)
        for c,q in owned.items():near(it['holdings_at_decision'][c],q)
        assert it['as_of_close_convention']==prior+'T15:05:00+08:00'
        assert it['latest_decision_price_read']==prior and it['execution_exchange_queried_for_decision'] is False
        actual={o['instrument']:o for o in it['orders']};assert len(actual)==len(it['orders']);expected_orders={}
        for c in sorted(set(owned)|set(weights)):
            q=owned.get(c,0.);w=weights.get(c,0.)
            if q>0 and w==0:expected_orders[c]=('SELL',q,None,None,'KNOWN_INVENTORY_FULL_EXIT');continue
            price,factor=source.value(c,'close',prior),source.value(c,'factor',prior)
            target=math.floor(equity*w/price*factor/100+1e-10)*100/factor;diff=target-q
            if abs(diff)<=1e-8*max(1.,q,target):continue
            qty=math.floor(diff*factor/100+1e-10)*100/factor if diff>0 else -diff
            if qty>0:expected_orders[c]=('BUY' if diff>0 else 'SELL',qty,price,factor,'PRIOR_CLOSE_TARGET')
        assert set(actual)==set(expected_orders)
        for c,(side,q,price,factor,basis) in expected_orders.items():
            o=actual[c];assert o['side']==side and o['as_of']==prior and o['quantity_basis']==basis
            near(o['normalized_units'],q);assert o['known_normalized_close']==price and o['known_factor']==factor
        count+=len(actual)
    return {'sessions':len(days),'intents':len(intents),'intended_orders':count,'unfilled_orders':sum(o['fill_status']=='UNFILLED' for o in orders)}

def main():
    parser=argparse.ArgumentParser()
    for name in ('run-dir','provider-uri','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();root=Path(args.run_dir);provider=Path(args.provider_uri);output=Path(args.output)
    assert not output.exists();planpath=Path('experiments/qlib/low-beta60-pre2026-plan.json');plan=read(planpath)
    assert sha(planpath)==PLAN_SHA and plan['independent_csv_audit_code_sha256']==BASE_AUDITOR_SHA
    assert sha('experiments/qlib/audit_sources/2026-10-21-low-beta60-development-csv-audit.py')==BASE_AUDITOR_SHA
    summary=read(root/'summary.json');assert summary['plan_sha256']==PLAN_SHA
    for n,h in plan['method_code_sha256'].items():assert sha(n)==h
    for n,h in plan['input_sha256'].items():
        if n!='price_files':assert sha(provider/n)==h
    codes=set()
    for line in (provider/'instruments/csi500.txt').read_text().splitlines():
        c,a,b=line.split()
        if c.startswith(('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')) and a<='2025-12-31' and b>='2023-12-29':codes.add(c)
    files=[Path('instruments/all.txt')]
    for c in sorted(codes):files.extend(Path('features')/c.lower()/(f+'.day.bin') for f in ('open','high','low','close','volume','factor','amount','adjclose'))
    files.append(Path('features/sh000905/adjclose.day.bin'));digest=hashlib.sha256()
    for file in files:digest.update(file.as_posix().encode()+b'\0');digest.update((provider/file).read_bytes());digest.update(b'\0')
    assert digest.hexdigest()==plan['input_sha256']['price_files']
    assert sha(root/'targets.json')==plan['initial_targets_sha256'];targets=read(root/'targets.json')
    source=Source(provider);results={};packets={}
    for label,stated in summary['results_by_extra_bps_and_family'].items():
        folder=root/label
        for name,h in stated['artifact_sha256'].items():assert sha(folder/name)==h
        packet={name:rows(folder/(name+'.csv')) for name in ('days','orders','holdings')};packet['intents']=read(folder/'decision_intents.json')
        extra,family=label.split('/');results[label]=verify(packet,targets[family],source,int(extra));packets[label]=packet
    def fee_mutation(packet):
        row=next(o for o in packet['orders'] if float(o['filled_normalized_units'])!=0)
        row['cost']=str(float(row['cost'])+1)
    rejected=[]
    for name,mutation in [
        ('prior_equity',lambda p:p['intents'][1].update(equity_at_decision=p['intents'][1]['equity_at_decision']+1000)),
        ('fixed_quantity',lambda p:p['intents'][0]['orders'][0].update(normalized_units=p['intents'][0]['orders'][0]['normalized_units']+100)),
        ('future_asof',lambda p:p['intents'][0].update(as_of_close_convention='2024-01-02T15:05:00+08:00')),
        ('fee',fee_mutation),
        ('daily_cash',lambda p:p['days'][0].update(cash=str(float(p['days'][0]['cash'])+1))),
    ]:
        modified=copy.deepcopy(packets['40/low_beta60']);mutation(modified)
        try:verify(modified,targets['low_beta60'],source,40)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('undetected mutation: '+name)
    result={'status':'INDEPENDENT_PRIOR_CLOSE_INTENT_AND_TAMPER_AUDIT_PASSED','script_sha256':sha(__file__),
        'frozen_plan_sha256':PLAN_SHA,'frozen_base_auditor_sha256':BASE_AUDITOR_SHA,'summary_sha256':sha(root/'summary.json'),
        'profiles':results,'total_intents':sum(r['intents'] for r in results.values()),'negative_controls_rejected':rejected,
        'negative_controls_use_hash_gate':False,'negative_control_method':'Mutate decoded in-memory evidence after authenticating original files; verify() has no hashes and independently recomputes arithmetic.',
        'latest_decoded_source_date':source.max_read,'date_indexed_2026_values_read':False,'new_strategy_runs':0,'network_queries':0,
        'imports_project_code':False,'raw_share_execution_verified':False,'discrepancies':[]}
    with output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))
if __name__=='__main__':main()
