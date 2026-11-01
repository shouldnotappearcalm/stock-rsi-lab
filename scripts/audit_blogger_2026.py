"""Separate source, rule and CSV arithmetic for all baseline/2026 accounts."""
import argparse,hashlib,json,math,struct
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from scripts.audit_blogger_pre2026 import need,read,sha,tree,rows,near,rule,derived_fields
from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategies_2026 import independent_periods,assert_prefix
from scripts.published_replay_float_comparison import compare_original

FUNDS=('SH518880','SZ159915','SH510050','SH510300','SH510500')
INDEXES=('SH000016','SH000300','SH000905')


def source_reader(provider):
    cal=(provider/'calendars/day.txt').read_text().splitlines();indices={d:i for i,d in enumerate(cal)};cache={}
    def value(c,f,d):
        if (c,f) not in cache:
            raw=(provider/'features'/c.lower()/(f+'.day.bin')).read_bytes();values=struct.unpack('<'+str(len(raw)//4)+'f',raw);cache[c,f]=(int(values[0]),values[1:])
        first,values=cache[c,f];i=indices[d]-first
        return values[i] if 0<=i<len(values) else None
    return cal,value


def reference_flags(op,pre,code):
    rate=Decimal('.2') if code=='SZ159915' else Decimal('.1');tick=Decimal('.001')
    high=(pre*(1+rate)).quantize(tick,rounding=ROUND_HALF_UP);low=(pre*(1-rate)).quantize(tick,rounding=ROUND_HALF_UP)
    need(low<=op<=high,'raw reported reference band');return int(op>=high),int(op<=low)


def sources(old,data):
    calendar,value=source_reader(data/'provider');packets={};overlap=0;raw_rows=0
    identities=[(c,m) for c in FUNDS for m in ('raw','hfq')]+[(c,'raw') for c in INDEXES]
    for c,m in identities:
        key=c+'-'+m;field='hfqday' if m=='hfq' else 'day';segments=[]
        for source in (old,data):
            receipt=read(source/'capture/manifest.json')['receipts'][key];wire=source/'capture'/(key+'-wire.json')
            need(sha(wire)==receipt['sha256'],'raw HTTP identity');body=read(wire)
            need(body['code']==0,'successful wire')
            raw=body['data'][c.lower()][field]
            bars=[dict(zip(('date','open','close','high','low','volume_provider_units'),r)) for r in raw]
            packet=read(source/'capture'/(key+'.json'))
            need(packet['instrument']==c and packet['mode']==m and packet['bars']==bars,'literal HTTP to parsed identity')
            need([r['date'] for r in bars]==[d for d in calendar if (d<='2025-12-31' if source==old else d>='2025-12-01')],'complete source session window')
            segments.append(bars);raw_rows+=len(bars)
        before,after=segments;byday={r['date']:r for r in before}
        for r in after:
            if r['date']<='2025-12-31':
                need(all(Decimal(r[k])==Decimal(byday[r['date']][k]) for k in r if k!='date'),'exact source overlap');overlap+=1
        combined=read(data/'combined'/(key+'.json'))['bars']
        need(combined==before+[r for r in after if r['date']>'2025-12-31'],'literal original source prefix and new tail');packets[key]=combined
    references={};ref_count=0
    for c in FUNDS:
        packet=read(data/'reference-source'/(c+'.json'));q=packet['query'];rr=[dict(zip(packet['fields'],r)) for r in packet['rows']]
        need(packet['error_code']=='0' and q['adjustflag']=='3' and q['code']==c[:2].lower()+'.'+c[2:],'unadjusted reference identity')
        need([r['date'] for r in rr]==[d for d in calendar if d>'2025-12-31'],'all2026 reference sessions')
        prices={r['date']:r for r in packets[c+'-raw']}
        for r in rr:
            need(r['code']==q['code'] and r['adjustflag']=='3' and r['tradestatus']=='1','raw active reference')
            need(all(Decimal(r[f])==Decimal(prices[r['date']][f]) for f in ('open','high','low','close')),'all reference OHLC matches primary')
            pre=Decimal(r['preclose']);need(pre.is_finite() and pre>0,'positive reported raw preclose');references[c,r['date']]=pre;ref_count+=1
    cells=0
    for c in FUNDS+INDEXES:
        raw=packets[c+'-raw'];adj=packets[c+'-hfq'] if c in FUNDS else raw;previous=None;first=Decimal(adj[0]['close'])
        for r,h in zip(raw,adj):
            # Reconstruct normalized prices without asking inverse HFQ for a2026 price band.
            norm=Decimal(h['close'])/first;factor=norm/Decimal(r['close'])
            if r['date']<='2025-12-31':fields,_=derived_fields(c,r,h,previous,first)
            else:
                fields={f:Decimal(r[f])*factor for f in ('open','high','low','close')}
                flags=reference_flags(Decimal(r['open']),references[c,r['date']],c) if c in FUNDS else (0,0)
                fields.update(factor=factor,volume=Decimal(r['volume_provider_units'])/factor,change=norm/previous-1,buyblock=flags[0],sellblock=flags[1])
            for f,v in fields.items():
                expected=struct.unpack('<f',struct.pack('<f',float(v)))[0]
                need(value(c,f,r['date'])==expected,'literal derived provider '+c+'/'+f+'/'+r['date']);cells+=1
            previous=norm
    return {'identities':13,'wire_rows_checked_including_overlap':raw_rows,'overlap_rows_identical':overlap,
            'reported_reference_rows':ref_count,'cross_provider_raw_OHLC_values_checked':ref_count*4,
            'derived_provider_values_checked':cells,'primary_quote_provider':'TENCENT','execution_reference_provider_2026':'BAOSTOCK',
            'exchange_official_reference_or_open_capacity_certified':False}


def check_case(provider,case,config,metric,extra):
    calendar,value=source_reader(provider);index={d:i for i,d in enumerate(calendar)};sessions=[d for d in calendar if d>='2024-01-02']
    ledger=audit_case(case,metric,sessions);dayrows=rows(case/'days.csv');byday={r['session']:r for r in dayrows};held={}
    for r in dayrows:need(float(r['cash'])>=-.000001,'no account borrowing')
    for r in rows(case/'holdings.csv'):
        held.setdefault(r['session'],{})[r['instrument']]=float(r['normalized_units']);near(r['normalized_price'],value(r['instrument'],'close',r['session']),'literal source holding close')
    intents=read(case/'decision_intents.json');need(len(intents)==len(sessions),'all daily wakes');byintent={};cells=0
    for day,i in zip(sessions,intents):
        prior=calendar[index[day]-1];need(i['execution_session']==day and i['as_of']==prior+'T15:05:00+08:00','prior actual session wake')
        payload={k:v for k,v in i.items() if k!='snapshot_sha256'}
        need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'exact snapshot hash')
        need(i['latest_decision_price_read']==prior and i['execution_exchange_queried_for_decision'] is False,'no future decision market')
        row=byday.get(prior);near(i['equity_at_decision'],row['account_value'] if row else 1000000,'prior NAV');near(i['cash_at_decision'],row['cash'] if row else 1000000,'prior actual cash')
        owned=held.get(prior,{})
        need(set(owned)==set(i['holdings_at_decision']) and len(owned)<=1,'actual single-fund inventory')
        for c,q in owned.items():near(i['holdings_at_decision'][c],q,'actual prior units')
        histories={}
        for c in config['signal_symbols']:
            dates=calendar[index[day]-config['history']:index[day]];history=[[d,value(c,'close',d)] for d in dates]
            need(history==i['histories'][c] and len(history)==config['history'],'literal source window, no future');histories[c]=history;cells+=len(history)
        scores,leader=rule(config,histories,list(owned));need(leader==i['observation']['leader'],'independent investment rule')
        for c,s in scores.items():need([str(s.numerator),str(s.denominator)]==i['observation']['scores_exact_ratio'][c],'exact scores')
        for c in config['symbols']:
            near(i['known_closes'][c],value(c,'close',prior),'known close');near(i['known_factors'][c],value(c,'factor',prior),'known factor')
        exits=[c for c in owned if c!=leader];orders=i['orders'];byintent[day]=i
        if exits:
            need(len(orders)==len(exits) and all(o['side']=='SELL' and o['instrument'] in exits for o in orders),'sell first; no unfilled proceeds')
            for o in orders:near(o['normalized_units'],owned[o['instrument']],'full actual exit')
        elif leader is None or leader in owned:need(not orders,'hold or cash; no daily top-up')
        else:
            need(len(orders)<=1 and all(o['side']=='BUY' and o['instrument']==leader for o in orders),'new leader only')
            for o in orders:
                price=i['known_closes'][leader];factor=i['known_factors'][leader];budget=max(0,min(.95*i['equity_at_decision'],i['cash_at_decision']-.05*i['equity_at_decision']))
                near(o['normalized_units'],math.floor(budget/price*factor/100)*100/factor,'exact prior-close budget and lot rounding')
    for o in rows(case/'orders.csv'):
        i=byintent[o['session']];planned=[p for p in i['orders'] if p['instrument']==o['instrument'] and p['side']==o['side']]
        need(len(planned)==1,'actual order has prior intent');near(abs(float(o['requested_normalized_units'])),planned[0]['normalized_units'],'requested order identity')
        q=abs(float(o['filled_normalized_units']));need(q<=planned[0]['normalized_units']+1e-7,'strict requested quantity cap')
        if q:
            near(o['normalized_price'],value(o['instrument'],'open',o['session']),'literal primary open')
            need(value(o['instrument'],'buyblock' if o['side']=='BUY' else 'sellblock',o['session'])==0,'source reference band allows actual fill')
        notional=abs(float(o['signed_trade_value']));near(o['cost'],max(5,notional*(5+extra)/10000) if notional else 0,'same ETF fee')
    periods=independent_periods(dayrows)
    need(set(periods)==set(metric['per_year']),'all evaluated years')
    for y,p in periods.items():
        for k,v in p.items():near(v,metric['per_year'][y][k],'independent annual '+y+'/'+k)
    return {**ledger,'periods':periods,'snapshots_checked':len(intents),'source_history_values_checked':cells,'investment_rule_recomputed':True}


def audit(root,old,data,old_run,request,expected,out):
    need(sha(request)==expected,'frozen request SHA256');req=read(request);t=read(out/'terminal.json');before=tree(out)
    need(t['complete'] and t['all_inputs_unchanged'] and t['request_sha256']==expected,'complete unchanged application')
    need(t['2026_results_used_to_change_rules'] is False and t['average_exposure_is_hard_gate'] is False,'no tuning or exposure veto')
    need(before=={**t['artifact_sha256'],'terminal.json':sha(out/'terminal.json')},'whole output identity')
    def unchanged():return (tree(old)==req['old_data_sha256'] and tree(data)==req['data_sha256'] and tree(old_run)==req['old_run_sha256']
        and all(sha(root/n)==h for n,h in {**req['method_and_source_sha256'],**req['public_sha256']}.items())
        and all(sha(p)==h for p,h in req['captured_article_sha256'].items()))
    need(unchanged(),'all frozen inputs before');source=sources(old,data);checks={};prefix={}
    expected_labels={phase+'/'+str(e)+'/'+n for phase in ('baseline','forward') for e in (20,40) for n in req['candidates']}
    need(set(t['results'])==expected_labels and req['candidates']==['fengji20','fengji_mean','plus2047'],'all twelve accounts, same three candidates')
    for label,metric in t['results'].items():
        phase,e,n=label.split('/');checks[label]=check_case((old if phase=='baseline' else data)/'provider',out/label,req['configs'][n],metric,int(e))
        if phase=='baseline':prefix[label]=compare_original(old_run/(e+'/'+n),out/label)
        else:assert_prefix(out/'baseline'/e/n,out/label)
    for threshold,key in ((10,'actual_2026_return_ge10_by_case'),(20,'actual_2026_return_ge20_by_case')):
        need(t[key]=={str(e)+'/'+n:checks['forward/'+str(e)+'/'+n]['periods']['2026']['net_return_pct']>=threshold for e in (20,40) for n in req['candidates']},'all actual threshold comparisons')
    need(unchanged() and tree(out)==before,'all inputs and outputs unchanged after')
    return {'status':'PASS_ALL_TWELVE_BLOGGER_LEDGERS_SOURCE_RULES_AND2026_BASELINES','request_sha256':expected,'terminal_sha256':sha(out/'terminal.json'),
        'cases':checks,'source_checks':source,'original_replay_comparisons':prefix,'same_process_2024_2025_forward_prefix_exact':True,
        'all_inputs_outputs_unchanged':True,'same_researcher_not_independent_assurance':True,'investment_qualified':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('old-data','data','old-run','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    result=audit(root,Path(a.old_data),Path(a.data),Path(a.old_run),Path(a.request),a.expected_sha256,Path(a.run_dir))
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])


if __name__=='__main__':main()
