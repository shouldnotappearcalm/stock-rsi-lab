"""Separate Decimal indicators, actual holding-age and full CSV/source checks."""
import argparse,hashlib,json,math,struct
from decimal import Decimal,localcontext
from pathlib import Path
from scripts.audit_blogger_pre2026 import need,read,sha,tree,rows,near,derived_fields
from scripts.audit_blogger_2026 import source_reader,sources as inherited_2026_sources
from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategies_2026 import independent_periods,assert_prefix

CODE='SH510050'

def independent_rule(name,values,held,age,pending):
    if name=='bigquant20':
        detail={'upper20':max(values),'lower10':min(values[-10:]),'close':values[-1]}
        action='SELL' if held and values[-1]<=detail['lower10'] else 'BUY' if not held and values[-1]>=detail['upper20'] else 'HOLD'
    else:
        with localcontext() as ctx:
            ctx.prec=60;p=list(map(lambda x:Decimal(str(x)),values));d=[b-a for a,b in zip(p,p[1:])]
            up=sum((max(x,Decimal(0)) for x in d[:10]),Decimal(0))/10;down=sum((max(-x,Decimal(0)) for x in d[:10]),Decimal(0))/10
            rsis=[up/(up+down)*100 if up+down else Decimal(0)]
            for x in d[10:]:
                up=(up*9+max(x,Decimal(0)))/10;down=(down*9+max(-x,Decimal(0)))/10;rsis.append(up/(up+down)*100 if up+down else Decimal(0))
            mean=sum(p[-200:])/200;detail={'ma200':float(mean),'rsi10':float(rsis[-1]),'previous_rsi10':float(rsis[-2]),'close':values[-1]}
            action='SELL' if held and (pending or rsis[-1]>40 or age>=10) else 'BUY' if not held and p[-1]>mean and rsis[-1]<30 else 'HOLD'
    return action,detail

def check_development_source(data):
    prep=read(data/'preparation.json');old=Path(prep['old_data_root']);need(tree(old)==prep['old_data_sha256'],'original source tree unchanged')
    calendar,value=source_reader(data/'provider');combined={};overlap=0
    for mode in ('raw','hfq'):
        packet=read(data/'capture'/(mode+'.json'));wire=data/'capture'/(mode+'-wire.json');receipt=read(data/'capture/manifest.json')['receipts'][mode]
        need(sha(wire)==receipt['wire_sha256'],'new warmup wire identity');body=read(wire);field='day' if mode=='raw' else 'hfqday'
        expected=[dict(zip(('date','open','close','high','low','volume_provider_units'),r)) for r in body['data'][CODE.lower()][field]]
        need(body['code']==0 and packet['bars']==expected,'explicit original warmup fields')
        need([r['date'] for r in expected]==[d for d in calendar if d<='2023-07-31'],'complete physical warmup window')
        before=read(old/'capture'/(CODE+'-'+mode+'.json'))['bars'];lookup={r['date']:r for r in before}
        for r in expected:
            if r['date']>='2023-07-03':need(all(Decimal(r[k])==Decimal(lookup[r['date']][k]) for k in r if k!='date'),'unchanged old source overlap');overlap+=1
        merged=[r for r in expected if r['date']<'2023-07-03']+before
        need(merged==read(data/'combined'/(mode+'.json'))['bars'] and [r['date'] for r in merged]==calendar,'complete merged source identity');combined[mode]=merged
    denom=Decimal(next(r['close'] for r in combined['hfq'] if r['date']=='2023-07-03'));previous=None;cells=0
    for r,h in zip(combined['raw'],combined['hfq']):
        # First original July row retains old unused warmup sentinels.
        fields,norm=derived_fields(CODE,r,h,None if r['date']=='2023-07-03' else previous,denom)
        for f,v in fields.items():
            need(value(CODE,f,r['date'])==struct.unpack('<f',struct.pack('<f',float(v)))[0],'literal normalized input '+r['date']+'/'+f);cells+=1
        previous=norm
    need(tree(old)==prep['old_data_sha256'],'old source tree after')
    return {'new_warmup_rows':len(expected)*2,'overlap_rows_identical':overlap,'derived_provider_values_checked':cells,'historical_arrival_verified':False}

def check_source(data,phase):
    if phase=='development':return check_development_source(data)
    prep=read(data/'preparation.json');dev=Path(prep['development_data_root']);prior=Path(prep['source_2026_root'])
    need(tree(dev)==prep['development_data_sha256'] and tree(prior)==prep['source_2026_sha256'],'whole inherited source identities')
    first=check_development_source(dev);old=Path(read(prior/'preparation.json')['old_data_root']);inherited=inherited_2026_sources(old,prior)
    cal=(data/'provider/calendars/day.txt').read_text().splitlines();a=(dev/'provider/calendars/day.txt').read_text().splitlines();b=(prior/'provider/calendars/day.txt').read_text().splitlines()
    cut=next(i for i,d in enumerate(b) if d>'2025-12-31');need(cal==a+b[cut:],'full actual clock and unchanged prefix')
    for f in ('open','high','low','close','factor','volume','change','buyblock','sellblock'):
        rel=Path('features')/CODE.lower()/(f+'.day.bin');blob=(data/'provider'/rel).read_bytes();before=(dev/'provider'/rel).read_bytes();after=(prior/'provider'/rel).read_bytes()[4*(cut+1):]
        need(blob==before+after,'literal development prefix and independently audited2026 tail')
    return {'development':first,'inherited_2026':inherited,'all_nine_development_prefixes_and_tails_identical':True}

def check_case(provider,case,config,metric,extra):
    cal,value=source_reader(provider);indices={d:i for i,d in enumerate(cal)};sessions=[d for d in cal if d>='2024-01-02'];ledger=audit_case(case,metric,sessions)
    dayrows=rows(case/'days.csv');byday={r['session']:r for r in dayrows};held={}
    for r in dayrows:need(float(r['cash'])>=-1e-6,'no borrowing')
    for h in rows(case/'holdings.csv'):
        need(h['instrument']==CODE,'fixed ETF only');held.setdefault(h['session'],{})[CODE]=float(h['normalized_units']);near(h['normalized_price'],value(CODE,'close',h['session']),'source close mark')
    intents=read(case/'decision_intents.json');need(len(intents)==len(sessions),'every actual daily wake');entry=None;pending=False;byintent={};cells=0
    for day,i in zip(sessions,intents):
        before=cal[indices[day]-1];owned=held.get(before,{})
        if owned:
            if entry is None:entry=before
        else:entry=None;pending=False
        age=indices[before]-indices[entry]+1 if entry else 0
        need(i['entry_session']==entry and i['holding_sessions']==age and i['exit_latched_before']==pending,'actual filled holding age and prior latch')
        need(i['execution_session']==day and i['as_of']==before+'T15:05:00+08:00' and i['latest_decision_price_read']==before and i['execution_exchange_queried_for_decision'] is False,'prior close only')
        payload={k:v for k,v in i.items() if k!='snapshot_sha256'}
        need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'exact snapshot hash')
        d=byday.get(before);near(i['equity_at_decision'],d['account_value'] if d else 1000000,'prior actual NAV');near(i['cash_at_decision'],d['cash'] if d else 1000000,'prior actual cash')
        need(set(owned)==set(i['holdings_at_decision']),'actual prior inventory')
        if owned:near(i['holdings_at_decision'][CODE],owned[CODE],'actual prior units')
        dates=cal[:indices[day]] if config['id']=='rayner10' else cal[indices[day]-20:indices[day]];history=[[d,value(CODE,'close',d)] for d in dates]
        need(history==i['history'],'complete exact visible source history');cells+=len(history)
        action,detail=independent_rule(config['id'],[v for _,v in history],bool(owned),age,pending)
        need(action==i['observation']['action'],'independent strategy decision')
        leader=CODE if action=='BUY' or owned and action!='SELL' else None;need(i['observation']['leader']==leader,'independent desired inventory')
        for k,v in detail.items():near(v,i['observation']['details'][k],'independent indicator '+k)
        if config['id']=='rayner10' and owned and action=='SELL':pending=True
        need(i['exit_latched_after']==pending,'exit stays pending until actual sale')
        price,factor=value(CODE,'close',before),value(CODE,'factor',before);near(i['known_closes'][CODE],price,'known close');near(i['known_factors'][CODE],factor,'known factor')
        orders=i['orders'];expected=[]
        if owned and leader is None:expected=[{'instrument':CODE,'side':'SELL','normalized_units':owned[CODE]}]
        elif not owned and leader:
            budget=max(0,min(.95*i['equity_at_decision'],i['cash_at_decision']-.05*i['equity_at_decision']));units=math.floor(budget/price*factor/100)*100/factor
            if units>0:expected=[{'instrument':CODE,'side':'BUY','normalized_units':units}]
        need(orders==expected,'exact source decision, known budget and no held top-up');byintent[day]=i
    for o in rows(case/'orders.csv'):
        planned=byintent[o['session']]['orders'];need(len(planned)==1 and planned[0]['side']==o['side'] and o['instrument']==CODE,'fill bound to actual prior intent')
        near(abs(float(o['requested_normalized_units'])),planned[0]['normalized_units'],'requested quantity');q=abs(float(o['filled_normalized_units']));need(q<=planned[0]['normalized_units']+1e-7,'strict fill cap')
        if q:
            near(o['normalized_price'],value(CODE,'open',o['session']),'literal source open');need(value(CODE,'buyblock' if o['side']=='BUY' else 'sellblock',o['session'])==0,'source price band permits fill')
        notional=abs(float(o['signed_trade_value']));near(o['cost'],max(5,notional*(5+extra)/10000) if notional else 0,'ETF fees')
    periods=independent_periods(dayrows)
    for y,p in periods.items():
        for k,v in p.items():near(v,metric['per_year'][y][k],'independent annual '+y+'/'+k)
    return {**ledger,'periods':periods,'snapshots_checked':len(intents),'source_history_values_checked':cells,'rule_and_holding_age_recomputed':True}

def audit(root,data,request,expected,out,dev=None):
    need(sha(request)==expected,'request hash');req=read(request);t=read(out/'terminal.json');before=tree(out)
    need(t['complete'] and t['all_inputs_unchanged'] and t['request_sha256']==expected and t['phase']==req['phase'],'complete unchanged phase')
    need(before=={**t['artifact_sha256'],'terminal.json':sha(out/'terminal.json')},'whole output hash')
    def unchanged():return (tree(data)==req['data_sha256'] and all(sha(root/n)==h for n,h in {**req['method_and_source_sha256'],**req['retained_prior_files_sha256']}.items())
        and all(sha(p)==h for p,h in req['captured_article_sha256'].items()) and (dev is None and req['development_run_sha256'] is None or dev is not None and tree(dev)==req['development_run_sha256']))
    need(unchanged(),'all inputs before');source=check_source(data,req['phase']);checks={}
    need(set(t['results'])=={str(e)+'/'+n for e in (20,40) for n in req['candidates']},'all registered cases retained')
    for label,m in t['results'].items():
        e,n=label.split('/');checks[label]=check_case(data/'provider',out/label,req['configs'][n],m,int(e))
        if dev is not None:assert_prefix(dev/label,out/label)
    if req['phase']=='development':
        passed=[n for n in req['candidates'] if checks['40/'+n]['2024_return_pct']>0 and checks['40/'+n]['2025_return_pct']>0 and checks['40/'+n]['unverified_held_marks']==0]
        need(passed==t['passed_two_year_screen'],'same two-year profit-only screening')
    else:
        for threshold,key in ((10,'actual_2026_return_ge10_by_case'),(20,'actual_2026_return_ge20_by_case')):need(t[key]=={k:c['periods']['2026']['net_return_pct']>=threshold for k,c in checks.items()},'all actual2026 threshold results')
    need(unchanged() and tree(out)==before,'all inputs/outputs unchanged after')
    return {'status':'PASS_BATCH2_SOURCE_RULES_HOLDING_CLOCK_AND_ALL_LEDGERS','phase':req['phase'],'request_sha256':expected,'terminal_sha256':sha(out/'terminal.json'),
        'source_checks':source,'cases':checks,'all_prior_strategy_files_unchanged':True,'same_researcher_not_independent_assurance':True,'investment_qualified':False,'objective_achieved':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('data','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--development-run');a=p.parse_args();result=audit(Path(__file__).resolve().parents[1],Path(a.data),Path(a.request),a.expected_sha256,Path(a.run_dir),Path(a.development_run) if a.development_run else None)
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])
