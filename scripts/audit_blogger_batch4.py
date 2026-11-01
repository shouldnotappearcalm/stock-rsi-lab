"""Separate Decimal indicators, actual filled-entry and signed source/account checks."""
import argparse,hashlib,json,math
from decimal import Decimal,localcontext
from pathlib import Path
from scripts.audit_blogger_pre2026 import need,read,sha,tree,rows,near
from scripts.audit_blogger_2026 import source_reader
from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategies_2026 import independent_periods,assert_prefix

CODE='SH510050'

def independent_rule(name,values,held,low,entry,pending):
    with localcontext() as ctx:
        ctx.prec=60;prices=[Decimal(str(v)) for v in values];last=prices[-1];details={'close':values[-1]}
        if name=='alvarez2':
            ds=[b-a for a,b in zip(prices,prices[1:])];up=sum((max(x,Decimal(0)) for x in ds[:2]),Decimal(0))/2;down=sum((max(-x,Decimal(0)) for x in ds[:2]),Decimal(0))/2
            for x in ds[2:]:up=(up+max(x,Decimal(0)))/2;down=(down+max(-x,Decimal(0)))/2
            rsi=100*up/(up+down) if up+down else Decimal(0);down2=prices[-1]<prices[-2]<prices[-3]
            buy=rsi<5 and down2;sell=rsi>50;details.update(rsi2=float(rsi),two_strict_down_closes=down2)
        elif name=='marwood10':
            ma200=sum(prices[-200:])/200;ma10=sum(prices[-10:])/10;stop=bool(held and Decimal(str(low))<=Decimal(str(entry))*Decimal('.9'))
            buy=last>ma200 and last<ma10;sell=last>ma10 or stop;details.update(ma200=float(ma200),ma10=float(ma10),low=low,actual_entry_price=entry,stop_touched=stop)
        else:raise ValueError('undeclared rule')
        return ('SELL' if held and (pending or sell) else 'BUY' if not held and buy else 'HOLD'),details

from scripts.audit_blogger_batch2 import check_source
from scripts.published_replay_float_comparison import compare_original

def check_case(provider,case,config,metric,extra):
    cal,value=source_reader(provider);indices={d:i for i,d in enumerate(cal)};sessions=[d for d in cal if d>='2024-01-02'];ledger=audit_case(case,metric,sessions)
    dayrows=rows(case/'days.csv');byday={r['session']:r for r in dayrows};held={}
    for r in dayrows:need(float(r['cash'])>=-1e-6,'no borrowing')
    for h in rows(case/'holdings.csv'):
        need(h['instrument']==CODE,'fixed ETF only');held.setdefault(h['session'],{})[CODE]=float(h['normalized_units']);near(h['normalized_price'],value(CODE,'close',h['session']),'source close mark')
    executions=rows(case/'orders.csv');fills={r['session']:r for r in executions if r['side']=='BUY' and float(r['filled_normalized_units'])>0}
    intents=read(case/'decision_intents.json');need(len(intents)==len(sessions),'every actual daily wake');entry=None;entry_price=None;pending=False;byintent={};cells=0
    for day,i in zip(sessions,intents):
        before=cal[indices[day]-1];owned=held.get(before,{})
        if owned:
            if entry is None:
                need(before in fills,'inventory starts only after actual filled buy');entry=before;entry_price=float(fills[before]['normalized_price']);near(entry_price,value(CODE,'open',before),'actual fill uses observed source open')
        else:entry=None;entry_price=None;pending=False
        need(i['entry_session']==entry and i['actual_entry_price']==entry_price and i['exit_latched_before']==pending,'actual observed fill entry and prior latch')
        need(i['execution_session']==day and i['as_of']==before+'T15:05:00+08:00' and i['latest_decision_price_read']==before and i['execution_exchange_queried_for_decision'] is False,'prior close only')
        payload={k:v for k,v in i.items() if k!='snapshot_sha256'}
        need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'exact snapshot hash')
        d=byday.get(before);near(i['equity_at_decision'],d['account_value'] if d else 1000000,'prior actual NAV');near(i['cash_at_decision'],d['cash'] if d else 1000000,'prior actual cash')
        need(set(owned)==set(i['holdings_at_decision']),'actual prior inventory')
        if owned:near(i['holdings_at_decision'][CODE],owned[CODE],'actual prior units')
        dates=cal[:indices[day]];history=[[d,value(CODE,'close',d)] for d in dates]
        need(history==i['history'],'complete exact visible source history');cells+=len(history)
        low=value(CODE,'low',before);need(i['completed_low']==low,'completed source low')
        action,detail=independent_rule(config['id'],[v for _,v in history],bool(owned),low,entry_price,pending)
        need(action==i['observation']['action'],'independent strategy decision')
        leader=CODE if action=='BUY' or owned and action!='SELL' else None;need(i['observation']['leader']==leader,'independent desired inventory')
        for k,v in detail.items():
            if v is None or type(v)==bool:need(i['observation']['details'][k]==v,'indicator state '+k)
            else:near(v,i['observation']['details'][k],'independent indicator '+k)
        if owned and action=='SELL':pending=True
        need(i['exit_latched_after']==pending,'exit stays pending until actual sale')
        price,factor=value(CODE,'close',before),value(CODE,'factor',before);near(i['known_closes'][CODE],price,'known close');near(i['known_factors'][CODE],factor,'known factor')
        orders=i['orders'];expected=[]
        if owned and leader is None:expected=[{'instrument':CODE,'side':'SELL','normalized_units':owned[CODE]}]
        elif not owned and leader:
            budget=max(0,min(.95*i['equity_at_decision'],i['cash_at_decision']-.05*i['equity_at_decision']));units=math.floor(budget/price*factor/100)*100/factor
            if units>0:expected=[{'instrument':CODE,'side':'BUY','normalized_units':units}]
        need(orders==expected,'exact source decision, known budget and no held top-up');byintent[day]=i
    for o in executions:
        planned=byintent[o['session']]['orders'];need(len(planned)==1 and planned[0]['side']==o['side'] and o['instrument']==CODE,'fill bound to actual prior intent')
        near(abs(float(o['requested_normalized_units'])),planned[0]['normalized_units'],'requested quantity');q=abs(float(o['filled_normalized_units']));need(q<=planned[0]['normalized_units']+1e-7,'strict fill cap')
        if q:
            near(o['normalized_price'],value(CODE,'open',o['session']),'literal source open');need(value(CODE,'buyblock' if o['side']=='BUY' else 'sellblock',o['session'])==0,'source price band permits fill')
        notional=abs(float(o['signed_trade_value']));near(o['cost'],max(5,notional*(5+extra)/10000) if notional else 0,'ETF fees')
    periods=independent_periods(dayrows)
    for y,p in periods.items():
        for k,v in p.items():near(v,metric['per_year'][y][k],'independent annual '+y+'/'+k)
    return {**ledger,'periods':periods,'snapshots_checked':len(intents),'source_history_values_checked':cells,'rule_actual_entry_and_exit_latch_recomputed':True}

def audit(root,data,request,expected,out,dev=None):
    need(sha(request)==expected,'request hash');req=read(request);t=read(out/'terminal.json');before=tree(out)
    need(t['complete'] and t['all_inputs_unchanged'] and t['request_sha256']==expected and t['phase']==req['phase'],'complete unchanged phase')
    need(before=={**t['artifact_sha256'],'terminal.json':sha(out/'terminal.json')},'whole output identity')
    def unchanged():return (tree(data)==req['data_sha256'] and all(sha(root/n)==h for n,h in {**req['method_and_source_sha256'],**req['retained_prior_files_sha256']}.items()) and all(sha(p)==h for p,h in req['captured_article_sha256'].items()) and (dev is None and req['development_run_sha256'] is None or dev is not None and tree(dev)==req['development_run_sha256']))
    need(unchanged(),'all frozen inputs before');source=check_source(data,req['phase']);checks={};prefix={}
    expected_labels={str(e)+'/'+n for e in (20,40) for n in req['candidates']} if dev is None else {phase+'/'+str(e)+'/'+n for phase in ('baseline','forward') for e in (20,40) for n in req['candidates']}
    need(set(t['results'])==expected_labels,'all registered cases')
    for label,m in t['results'].items():
        parts=label.split('/');e,n=parts[-2:];phase=parts[0] if len(parts)==3 else 'development';provider=(Path(read(data/'preparation.json')['development_data_root']) if phase=='baseline' else data)/'provider'
        checks[label]=check_case(provider,out/label,req['configs'][n],m,int(e))
        if phase=='baseline':prefix[label]=compare_original(dev/e/n,out/label)
        if phase=='forward':assert_prefix(out/'baseline'/e/n,out/label)
    if dev is None:
        passed=[n for n in req['candidates'] if checks['40/'+n]['2024_return_pct']>0 and checks['40/'+n]['2025_return_pct']>0 and checks['40/'+n]['unverified_held_marks']==0];need(passed==t['passed_two_year_screen'],'same development criterion')
    else:
        for threshold,key in ((10,'actual_2026_return_ge10_by_case'),(20,'actual_2026_return_ge20_by_case')):need(t[key]=={k.removeprefix('forward/'):c['periods']['2026']['net_return_pct']>=threshold for k,c in checks.items() if k.startswith('forward/')},'complete threshold report')
    need(unchanged() and tree(out)==before,'all inputs/outputs unchanged after')
    return {'status':'PASS_BATCH4_SOURCES_DAILY_RULES_ACTUAL_ENTRY_AND_ALL_LEDGERS','phase':req['phase'],'request_sha256':expected,'terminal_sha256':sha(out/'terminal.json'),'cases':checks,
        'source_checks':source,'original_replay_comparisons':prefix,'all_prior_306_files_unchanged':True,'same_researcher_not_independent_assurance':True,'investment_qualified':False,'objective_achieved':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('data','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--development-run');a=p.parse_args();result=audit(Path(__file__).resolve().parents[1],Path(a.data),Path(a.request),a.expected_sha256,Path(a.run_dir),Path(a.development_run) if a.development_run else None)
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])
