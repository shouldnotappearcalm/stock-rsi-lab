"""Independent Decimal weights and signed source/account checks."""
import argparse,hashlib,json,math
from decimal import Decimal, localcontext
from pathlib import Path
from scripts.audit_blogger_pre2026 import need,read,sha,tree,rows,near
from scripts.audit_blogger_2026 import source_reader
from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategies_2026 import independent_periods,assert_prefix

from scripts.audit_blogger_2026 import sources as audit_forward_source
from scripts.audit_blogger_pre2026 import audit_source
from scripts.published_replay_float_comparison import compare_original

ASSETS = ('SH510300','SH510500','SH518880','SZ159915')


def check_source(data, phase):
    if phase=='development':
        cal,value=source_reader(data/'provider')
        return audit_source(data,cal,value)
    return audit_forward_source(Path(read(data/'preparation.json')['old_data_root']),data)


def recompute_weights(name, histories):
    if name=='equal4':
        need(not histories,'equal weight needs no return history')
        return dict.fromkeys(ASSETS,.2375),{}
    need(name=='invvol60' and set(histories)==set(ASSETS),'declared volatility weighting')
    with localcontext() as ctx:
        ctx.prec=50
        vols={}
        for c,history in histories.items():
            p=[Decimal.from_float(v) for _,v in history]
            returns=[y/x-1 for x,y in zip(p,p[1:])]
            need(len(returns)==60,'60 daily returns')
            mean=sum(returns)/60
            vols[c]=(sum((v-mean)**2 for v in returns)/59).sqrt()
        total=sum(1/v for v in vols.values())
        return ({c:float(Decimal('.95')/vols[c]/total) for c in ASSETS},
                {c:float(vols[c]) for c in ASSETS})


def rounded(q,factor):
    n=int(q*factor/100)
    return next(n*100/factor for n in range(n,max(-1,n-2),-1) if n*100/factor<=q)


def check_case(provider,case,config,metric,extra):
    cal,value=source_reader(provider)
    index={d:i for i,d in enumerate(cal)}
    sessions=[d for d in cal if d>='2024-01-02']
    ledger=audit_case(case,metric,sessions)
    dayrows=rows(case/'days.csv')
    byday={r['session']:r for r in dayrows}
    held={}
    for r in dayrows:need(float(r['cash'])>=-1e-6,'no borrowing')
    for h in rows(case/'holdings.csv'):
        c,d=h['instrument'],h['session']
        need(c in ASSETS,'declared ETF only')
        held.setdefault(d,{})[c]=float(h['normalized_units'])
        near(h['normalized_price'],value(c,'close',d),'source close mark')
    intents=read(case/'decision_intents.json')
    need(len(intents)==len(sessions),'every daily decision')
    expected_fills={}
    target,weights={},{}
    active=False
    formed=None
    formations=0
    for day,i in zip(sessions,intents):
        idx=index[day]
        prior=cal[idx-1]
        need(i['execution_session']==day and i['as_of']==prior+'T15:05:00+08:00'
             and i['latest_decision_price_read']==prior and i['execution_exchange_queried_for_decision'] is False,'prior close only')
        payload={k:v for k,v in i.items() if k!='snapshot_sha256'}
        need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'snapshot hash')
        account=byday.get(prior)
        near(i['equity_at_decision'],account['account_value'] if account else 1000000,'prior actual NAV')
        near(i['cash_at_decision'],account['cash'] if account else 1000000,'prior actual cash')
        equity,cash=i['equity_at_decision'],i['cash_at_decision']
        owned=held.get(prior,{})
        need(owned==i['holdings_at_decision'],'actual prior units')
        price={c:value(c,'close',prior) for c in ASSETS}
        factor={c:value(c,'factor',prior) for c in ASSETS}
        need(i['known_closes']==price and i['known_factors']==factor,'literal marks and factors')
        formation=prior[:7]!=day[:7]
        need(i['formation'] is formation,'month boundary')
        histories={c:[[d,value(c,'close',d)] for d in cal[idx-61:idx]] for c in ASSETS} if formation and config['id']=='invvol60' else {}
        need(i['histories']==histories,'literal prior history')
        if formation:
            estimated,sigma=recompute_weights(config['id'],histories)
            need(set(i['weights'])==set(estimated) and set(i['volatility'])==set(sigma),'complete weights and volatility')
            for c,w in estimated.items():near(i['weights'][c],w,'independent weight')
            for c,v in sigma.items():near(i['volatility'][c],v,'independent volatility')
            weights=i['weights']
            target={c:rounded(equity*weights[c]/price[c],factor[c]) for c in ASSETS}
            formed=prior
            active=True
            formations+=1
        else:
            need(not i['volatility'],'no midmonth refit')
        need(i['formed_at']==formed and i['weights']==weights and i['target_normalized_units']==target
             and i['active_before'] is active,'frozen monthly targets')
        expected=[]
        if active:
            for c in ASSETS:
                q=rounded(max(0,owned.get(c,0)-target[c]),factor[c])
                if q:expected.append({'instrument':c,'side':'SELL','normalized_units':q})
            if not expected:
                remaining=max(0,cash-.05*equity)
                for c in ASSETS:
                    desired=max(0,target[c]-owned.get(c,0))*price[c]
                    affordable=min(remaining*10000/(10000+5+extra),remaining-5)
                    q=rounded(max(0,min(desired,affordable))/price[c],factor[c])
                    if not q:continue
                    notional=q*price[c]
                    remaining-=notional+max(5,notional*(5+extra)/10000)
                    expected.append({'instrument':c,'side':'BUY','normalized_units':q})
                need(remaining>=-1e-7,'prior cash reserve and fees')
        active=bool(expected)
        need(i['orders']==expected and i['active_after'] is active,'exact phased orders')
        for o in expected:expected_fills[day,o['instrument']]=o
    for o in rows(case/'orders.csv'):
        d,c=o['session'],o['instrument']
        planned=expected_fills.pop((d,c))
        need(planned['side']==o['side'] and o['signal_date']==cal[index[d]-1],'prior intent and direction')
        requested=planned['normalized_units']
        near(abs(float(o['requested_normalized_units'])),requested,'requested size')
        q=abs(float(o['filled_normalized_units']))
        need(q<=requested+1e-7,'strict requested cap')
        if q:
            near(o['normalized_price'],value(c,'open',d),'literal source open')
            need(value(c,'buyblock' if o['side']=='BUY' else 'sellblock',d)==0,'source price band')
        notional=abs(float(o['signed_trade_value']))
        near(o['cost'],max(5,notional*(5+extra)/10000) if notional else 0,'ETF fee')
    need(not expected_fills,'all intended orders recorded')
    periods=independent_periods(dayrows)
    for y,p in periods.items():
        for k,v in p.items():near(v,metric['per_year'][y][k],'independent annual '+y+'/'+k)
    return {**ledger,'periods':periods,'snapshots_checked':len(intents),'formations_checked':formations,
            'max_simultaneous_holdings':max(map(len,held.values()),default=0)}

def audit(root,data,request,expected,out,dev=None):
    need(sha(request)==expected,'request hash');req=read(request);t=read(out/'terminal.json');before=tree(out)
    need(t['complete'] and t['all_inputs_unchanged'] and t['request_sha256']==expected and t['phase']==req['phase'],'complete unchanged phase')
    need(before=={**t['artifact_sha256'],'terminal.json':sha(out/'terminal.json')},'whole output identity')
    def unchanged():return (tree(data)==req['data_sha256'] and all(sha(root/n)==h for n,h in {**req['method_and_source_sha256'],**req['retained_prior_files_sha256']}.items()) and all(sha(p)==h for p,h in req['captured_article_sha256'].items()) and (dev is None and req['development_run_sha256'] is None or dev is not None and tree(dev)==req['development_run_sha256']))
    need(unchanged(),'all frozen inputs before');source=check_source(data,req['phase']);checks={};prefix={}
    expected_labels={str(e)+'/'+n for e in (20,40) for n in req['candidates']} if dev is None else {phase+'/'+str(e)+'/'+n for phase in ('baseline','forward') for e in (20,40) for n in req['candidates']}
    need(set(t['results'])==expected_labels,'all registered cases')
    for label,m in t['results'].items():
        parts=label.split('/');e,n=parts[-2:];phase=parts[0] if len(parts)==3 else 'development';provider=(Path(read(data/'preparation.json')['old_data_root']) if phase=='baseline' else data)/'provider'
        checks[label]=check_case(provider,out/label,req['configs'][n],m,int(e))
        if phase=='baseline':prefix[label]=compare_original(dev/e/n,out/label)
        if phase=='forward':assert_prefix(out/'baseline'/e/n,out/label)
    if dev is None:
        passed=[n for n in req['candidates'] if checks['40/'+n]['2024_return_pct']>0 and checks['40/'+n]['2025_return_pct']>0 and checks['40/'+n]['unverified_held_marks']==0];need(passed==t['passed_two_year_screen'],'same development criterion')
    else:
        for threshold,key in ((10,'actual_2026_return_ge10_by_case'),(20,'actual_2026_return_ge20_by_case')):need(t[key]=={k.removeprefix('forward/'):c['periods']['2026']['net_return_pct']>=threshold for k,c in checks.items() if k.startswith('forward/')},'complete threshold report')
    need(unchanged() and tree(out)==before,'all inputs/outputs unchanged after')
    return {'status':'PASS_BATCH7_SOURCES_WEIGHTS_AND_ALL_LEDGERS','phase':req['phase'],'request_sha256':expected,'terminal_sha256':sha(out/'terminal.json'),'cases':checks,
        'source_checks':source,'original_replay_comparisons':prefix,'all_prior_files_unchanged':True,'same_researcher_not_independent_assurance':True,'investment_qualified':False,'objective_achieved':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('data','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--development-run');a=p.parse_args();result=audit(Path(__file__).resolve().parents[1],Path(a.data),Path(a.request),a.expected_sha256,Path(a.run_dir),Path(a.development_run) if a.development_run else None)
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])
