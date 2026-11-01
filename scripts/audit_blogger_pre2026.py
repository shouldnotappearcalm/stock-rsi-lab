"""Same-researcher independent rule arithmetic and source/ledger cross-checks."""
import argparse,csv,hashlib,json,math,struct
from decimal import Decimal,ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path
from scripts.audit_published_strategies import audit_case


def need(v,msg):
    if not v:raise ValueError(msg)


def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(Path(p).rglob('*')) if f.is_file()}
def rows(p):
    with Path(p).open() as f:return list(csv.DictReader(f))
def near(a,b,msg):need(math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-7),msg)


def derived_fields(code,raw,adjusted,previous,first):
    """Separate Decimal reconstruction, followed by literal float32 comparison."""
    norm=Decimal(adjusted['close'])/first;factor=norm/Decimal(raw['close'])
    fields={k:Decimal(raw[k])*factor for k in ('open','high','low','close')}
    fields.update(factor=factor,volume=Decimal(raw['volume_provider_units'])/factor,
                  change=norm/previous-1 if previous is not None else 0,buyblock=0,sellblock=0)
    if code not in ('SH000016','SH000300','SH000905') and previous is not None:
        reference=previous/factor;rate=Decimal('.2') if code=='SZ159915' else Decimal('.1')
        low=(reference*(1-rate)).quantize(Decimal('.001'),rounding=ROUND_HALF_UP)
        high=(reference*(1+rate)).quantize(Decimal('.001'),rounding=ROUND_HALF_UP)
        op=Decimal(raw['open']);need(low<=op<=high,'source open inside declared reference band')
        fields.update(buyblock=int(op>=high),sellblock=int(op<=low))
    return fields,norm


def audit_source(data,calendar,value):
    funds=('SH518880','SZ159915','SH510050','SH510300','SH510500');indices=('SH000016','SH000300','SH000905')
    manifest=read(data/'capture/manifest.json');packets={};cells=0
    identities=[(c,m) for c in funds for m in ('raw','hfq')]+[(c,'raw') for c in indices]
    need(set(manifest['receipts'])=={c+'-'+m for c,m in identities} and not manifest['errors'],'exact13 successful source identities')
    for code,mode in identities:
        key=code+'-'+mode;wire=data/'capture'/(key+'-wire.json');receipt=manifest['receipts'][key]
        need(sha(wire)==receipt['sha256'],'raw HTTP source receipt')
        packet=read(data/'capture'/(key+'.json'));body=read(wire);field='hfqday' if mode=='hfq' else 'day'
        need(body['code']==0 and packet['instrument']==code and packet['mode']==mode,'wire and parsed security/adjustment identity')
        bars=body['data'][code.lower()][field]
        expected=[dict(zip(('date','open','close','high','low','volume_provider_units'),r)) for r in bars]
        need(packet['bars']==expected and [r['date'] for r in expected]==calendar,'raw HTTP to exact parsed session bars')
        need(receipt['rows']==len(calendar),'complete source row count');packets[key]=expected
    for code in funds+indices:
        raw=packets[code+'-raw'];adjusted=packets[code+'-hfq'] if code in funds else raw
        previous=None;first=Decimal(adjusted[0]['close'])
        for r,h in zip(raw,adjusted):
            fields,previous=derived_fields(code,r,h,previous,first)
            for f,v in fields.items():
                expected=struct.unpack('<f',struct.pack('<f',float(v)))[0]
                need(value(code,f,r['date'])==expected,'literal normalized source '+code+'/'+r['date']+'/'+f);cells+=1
    return {'captured_source_identities':len(identities),'raw_rows_checked':len(calendar)*len(identities),
            'derived_provider_values_checked':cells,'source_mix':False,'historical_arrival_verified':False}


def rule(config,histories,held):
    scores={}
    for c,h in histories.items():
        p=[Fraction(str(v)) for _,v in h]
        denominator=sum(p[:3],Fraction(0))/3 if config['id']=='fengji_mean' else p[0]
        scores[c]=p[-1]/denominator-1
    if config['id']=='plus2047':
        mapping=dict(zip(config['signal_symbols'],config['symbols']))
        if held:
            s=next(s for s,c in mapping.items() if c==held[0]);leader=held[0] if scores[s]>0 else None
        else:
            leaders=[s for s in scores if scores[s]>0 and min(scores[s]-scores[t] for t in scores if t!=s)>Fraction(1,100)]
            need(len(leaders)<=1,'at most one strict-margin leader');leader=mapping[leaders[0]] if leaders else None
    else:
        highest=max(scores.values());tied=[c for c in config['symbols'] if scores[c]==highest]
        leader=(held[0] if held and held[0] in tied else tied[0]) if highest>0 else None
    return scores,leader


def audit(root,data,request,expected,folder):
    need(sha(request)==expected,'frozen request hash');req=read(request);terminal=read(folder/'terminal.json');before=tree(folder)
    need(terminal['complete'] and terminal['all_inputs_unchanged'] and terminal['request_sha256']==expected,'complete unchanged six-account run')
    need(terminal['2026_candidate_returns_computed'] is False and terminal['average_exposure_is_hard_gate'] is False,'no2026 result and no invented allocation veto')
    need(before=={**terminal['artifact_sha256'],'terminal.json':sha(folder/'terminal.json')},'whole output identity')
    def unchanged():return (tree(data)==req['data_sha256'] and all(sha(root/n)==h for n,h in req['method_and_source_sha256'].items()) and all(sha(p)==h for p,h in req['captured_article_sha256'].items()))
    need(unchanged(),'all frozen inputs before');provider=data/'provider';calendar=(provider/'calendars/day.txt').read_text().splitlines();need(calendar[-1]=='2025-12-31','physically pre2026 prices')
    index={d:i for i,d in enumerate(calendar)};sessions=[d for d in calendar if d>='2024-01-02'];need(len(sessions)==485,'complete485-session outcomes');cache={}
    def value(c,f,d):
        if (c,f) not in cache:
            raw=(provider/'features'/c.lower()/(f+'.day.bin')).read_bytes();p=struct.unpack('<'+str(len(raw)//4)+'f',raw);cache[c,f]=(int(p[0]),p[1:])
        start,values=cache[c,f];j=index[d]-start
        return values[j] if 0<=j<len(values) else None
    source=audit_source(data,calendar,value);results={}
    for label,metric in terminal['results'].items():
        extra,name=label.split('/');config=req['configs'][name];case=folder/label;ledger=audit_case(case,metric,sessions)
        intents=read(case/'decision_intents.json');need(len(intents)==485,'all daily wakes');day_rows={r['session']:r for r in rows(case/'days.csv')};byhold={}
        for h in rows(case/'holdings.csv'):
            byhold.setdefault(h['session'],{})[h['instrument']]=float(h['normalized_units'])
            near(h['normalized_price'],value(h['instrument'],'close',h['session']),'source close mark')
        by_intent={};cells=0
        for execution,i in zip(sessions,intents):
            previous=calendar[index[execution]-1];need(i['execution_session']==execution and i['as_of']==previous+'T15:05:00+08:00','actual prior close clock')
            payload={k:v for k,v in i.items() if k!='snapshot_sha256'}
            need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'exact snapshot hash')
            need(i['latest_decision_price_read']==previous and i['execution_exchange_queried_for_decision'] is False,'no execution-day field in decision')
            prior=day_rows.get(previous);near(i['equity_at_decision'],prior['account_value'] if prior else 1000000,'prior actual NAV');near(i['cash_at_decision'],prior['cash'] if prior else 1000000,'prior actual cash')
            held=byhold.get(previous,{})
            need(set(held)==set(i['holdings_at_decision']) and len(held)<=1,'actual single-fund inventory')
            for c,q in held.items():near(q,i['holdings_at_decision'][c],'actual prior quantity')
            expected_hist={}
            for c in config['signal_symbols']:
                dates=calendar[max(0,index[execution]-config['history']):index[execution]]
                h=[[d,value(c,'close',d)] for d in dates];need(len(h)==config['history'] and h==i['histories'][c],'all source history values and exact window')
                expected_hist[c]=h;cells+=len(h)
            scores,leader=rule(config,expected_hist,list(held));need(leader==i['observation']['leader'],'independently calculated source investment rule')
            for c,s in scores.items():need([str(s.numerator),str(s.denominator)]==i['observation']['scores_exact_ratio'][c],'exact source score arithmetic')
            for c in config['symbols']:
                near(i['known_closes'][c],value(c,'close',previous),'known fund close');near(i['known_factors'][c],value(c,'factor',previous),'known fund factor')
            exits=[c for c in held if c!=leader];orders=i['orders'];by_intent[execution]=i
            if exits:
                need(len(orders)==len(exits) and all(o['side']=='SELL' and o['instrument'] in exits for o in orders),'exit first, no simultaneous unfunded buy')
                for o in orders:near(o['normalized_units'],held[o['instrument']],'full exit amount')
            elif leader is None or leader in held:need(not orders,'no forced rebalance or held-positive rotation')
            else:
                need(len(orders)<=1 and all(o['side']=='BUY' and o['instrument']==leader for o in orders),'new visible leader only')
                if orders:
                    o=orders[0];notional=o['normalized_units']*i['known_closes'][leader]
                    need(notional<=min(.95*i['equity_at_decision'],max(0,i['cash_at_decision']-.05*i['equity_at_decision']))+1e-6,'known cash budget only')
        for o in rows(case/'orders.csv'):
            intent=by_intent[o['session']];planned=[p for p in intent['orders'] if p['instrument']==o['instrument'] and p['side']==o['side']];need(len(planned)==1,'executed order must have prior intent')
            near(abs(float(o['requested_normalized_units'])),planned[0]['normalized_units'],'requested size identity')
            q=abs(float(o['filled_normalized_units']));need(q<=planned[0]['normalized_units']+1e-7,'strict fill quantity cap')
            if q:
                near(o['normalized_price'],value(o['instrument'],'open',o['session']),'literal source open')
                flag='buyblock' if o['side']=='BUY' else 'sellblock';need(value(o['instrument'],flag,o['session'])==0,'declared reference band does not block fill')
            notional=abs(float(o['signed_trade_value']));near(o['cost'],max(5,notional*(5+int(extra))/10000) if notional else 0,'ETF fee formula, no stock sell tax')
        results[label]={**ledger,'snapshots_checked':len(intents),'source_history_values_checked':cells,'source_rule_recomputed':True,'opening_capacity_verified':False}
    passed=[n for n in req['candidates'] if min(results['40/'+n]['2024_return_pct'],results['40/'+n]['2025_return_pct'])>0 and results['40/'+n]['unverified_held_marks']==0]
    need(passed==terminal['passed_numerical_two_year_screen'],'same profit-only development screen')
    need(unchanged() and tree(folder)==before,'all inputs/outputs unchanged after')
    return {'status':'PASS_ALL_SIX_BLOGGER_ACCOUNTS_RULES_SNAPSHOTS_AND_SOURCE_PRICES','request_sha256':expected,'terminal_sha256':sha(folder/'terminal.json'),
            'cases':results,'source_checks':source,'passed_numerical_two_year_screen':passed,'all_inputs_outputs_unchanged':True,'same_researcher_not_independent_assurance':True,
            '2026_candidate_returns_computed':False,'investment_qualified':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('data','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1];result=audit(root,Path(a.data),Path(a.request),a.expected_sha256,Path(a.run_dir))
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])


if __name__=='__main__':main()
