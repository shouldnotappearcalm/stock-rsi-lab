"""Separate source, period sampling, execution-state and signed CSV audit."""
import argparse,hashlib,json,math,struct
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from scripts.audit_blogger_pre2026 import need,read,sha,tree,rows,near
from scripts.audit_blogger_batch2 import check_development_source
from scripts.audit_blogger_2026 import source_reader,reference_flags,sources as inherited_stock_sources
from scripts.audit_published_strategies import audit_case
from scripts.audit_published_strategies_2026 import independent_periods,assert_prefix
from scripts.published_replay_float_comparison import compare_original

STOCK,BOND='SH510050','SH511010'

def check_source(data,phase):
    prep=read(data/'preparation.json');cal,value=source_reader(data/'provider');packets={};overlap=0
    if phase=='development':
        stock=Path(prep['stock_data_root']);need(tree(stock)==prep['stock_data_sha256'],'whole inherited stock data');stock_check=check_development_source(stock)
        for f in ('open','high','low','close','factor','volume','change','buyblock','sellblock'):
            rel=Path('features')/STOCK.lower()/(f+'.day.bin');need((data/'provider'/rel).read_bytes()==(stock/'provider'/rel).read_bytes(),'literal old stock values')
    else:
        dev=Path(prep['development_data_root']);stock=Path(prep['source_2026_root']);need(tree(dev)==prep['development_data_sha256'] and tree(stock)==prep['source_2026_sha256'],'full development and inherited2026 identities')
        stock_check={'development':check_source(dev,'development'),'prior2026':inherited_stock_sources(Path(read(stock/'preparation.json')['old_data_root']),stock)}
        a=(dev/'provider/calendars/day.txt').read_text().splitlines();b=(stock/'provider/calendars/day.txt').read_text().splitlines();cut=next(i for i,d in enumerate(b) if d>'2025-12-31')
        need(cal==a+b[cut:],'actual appended full calendar')
        for c in (STOCK,BOND):
            for f in ('open','high','low','close','factor','volume','change','buyblock','sellblock'):
                rel=Path('features')/c.lower()/(f+'.day.bin');old=(dev/'provider'/rel).read_bytes();need((data/'provider'/rel).read_bytes()[:len(old)]==old,'exact original development prefix')
                if c==STOCK:need((data/'provider'/rel).read_bytes()==old+(stock/'provider'/rel).read_bytes()[4*(cut+1):],'literal stock2026 quote tail')
    for mode in ('raw','hfq'):
        field='day' if mode=='raw' else 'hfqday';wire=data/'capture'/(mode+'-wire.json');receipt=read(data/'capture/manifest.json')['receipts'][mode]
        need(sha(wire)==receipt['wire_sha256'],'bond raw HTTP receipt');body=read(wire);raw=body['data'][BOND.lower()][field]
        observed=[dict(zip(('date','open','close','high','low','volume_provider_units'),r)) for r in raw]
        need(body['code']==0 and read(data/'capture'/(mode+'.json'))['bars']==observed,'literal parsed bond identity')
        want=[d for d in cal if d>=('2023-07-03' if phase=='development' else '2025-12-01')]
        need([r['date'] for r in observed]==want,'complete requested actual bond window')
        if phase=='development':combined=observed
        else:
            old=read(dev/'combined'/(mode+'.json'))['bars'];lookup={r['date']:r for r in old}
            for r in observed:
                if r['date']<='2025-12-31':need(all(Decimal(r[k])==Decimal(lookup[r['date']][k]) for k in r if k!='date'),'unchanged bond overlap');overlap+=1
            combined=old+[r for r in observed if r['date']>'2025-12-31']
        need(read(data/'combined'/(mode+'.json'))['bars']==combined,'literal original plus appended bond bars');packets[mode]=combined
    references={}
    if phase=='forward':
        rr=read(data/'reference-source.json');need(rr['error_code']=='0','successful reported reference capture');rr=[dict(zip(rr['fields'],r)) for r in rr['rows']];byday={r['date']:r for r in packets['raw']}
        need([r['date'] for r in rr]==[d for d in cal if d>'2025-12-31'],'all198 raw references')
        for r in rr:
            need(r['code']=='sh.511010' and r['adjustflag']=='3','unadjusted bond reference identity')
            need(all(Decimal(r[f])==Decimal(byday[r['date']][f]) for f in ('open','high','low','close')),'reference raw OHLC matches primary')
            references[r['date']]=Decimal(r['preclose']);need(references[r['date']].is_finite() and references[r['date']]>0,'positive raw reference')
    first=Decimal(packets['hfq'][0]['close']);previous=None;cells=0;inactive=0
    for r,h in zip(packets['raw'],packets['hfq']):
        need(r['date']==h['date'],'raw and HFQ dates align');norm=Decimal(h['close'])/first;factor=norm/Decimal(r['close']);volume=Decimal(r['volume_provider_units'])
        fields={f:Decimal(r[f])*factor for f in ('open','high','low','close')};fields.update(factor=factor,volume=volume/factor,change=norm/previous-1 if previous is not None else 0)
        if not volume:flags=(1,1);inactive+=1
        elif previous is None:flags=(0,0)
        else:flags=reference_flags(Decimal(r['open']),references.get(r['date'],previous/factor),BOND)
        fields.update(buyblock=flags[0],sellblock=flags[1])
        for f,v in fields.items():need(value(BOND,f,r['date'])==struct.unpack('<f',struct.pack('<f',float(v)))[0],'literal bond normalization '+r['date']+'/'+f);cells+=1
        previous=norm
    return {'stock':stock_check,'bond_rows_per_mode':len(packets['raw']),'bond_provider_values_checked':cells,'inactive_bond_rows_preserved':inactive,'overlap_rows_identical':overlap,'raw_reference_rows':len(references),'opening_capacity_verified':False}

def floor_qty(q,factor):
    lots=int(math.floor(q*factor/100));answer=lots*100/factor
    return max(0,lots-1)*100/factor if answer>q else answer

def annual_plan(target,equity,cash,owned,closes,factors,extra):
    sells=[{'instrument':c,'side':'SELL','normalized_units':floor_qty(max(0,owned.get(c,0)-target[c]),factors[c])} for c in (STOCK,BOND)]
    sells=[o for o in sells if o['normalized_units']>0]
    if sells:return sells
    available=max(0,cash-.05*equity);buy=[];rate=(5+extra)/10000
    for c in (STOCK,BOND):
        notional=max(0,min(max(0,target[c]-owned.get(c,0))*closes[c],available/(1+rate),available-5));q=floor_qty(notional/closes[c],factors[c])
        if q>0:
            buy.append({'instrument':c,'side':'BUY','normalized_units':q});value=q*closes[c];available-=value+max(5,value*rate)
            need(available>=-1e-8,'independent planned fees fit observed cash')
    return buy

def check_case(provider,case,config,metric,extra):
    cal,value=source_reader(provider);index={d:i for i,d in enumerate(cal)};sessions=[d for d in cal if d>='2024-01-02'];ledger=audit_case(case,metric,sessions)
    dayrows=rows(case/'days.csv');byday={r['session']:r for r in dayrows};owned_byday={}
    for r in dayrows:need(float(r['cash'])>=-1e-6,'no borrowing')
    for h in rows(case/'holdings.csv'):
        need(h['instrument'] in config['symbols'],'declared actual inventory');owned_byday.setdefault(h['session'],{})[h['instrument']]=float(h['normalized_units']);near(h['normalized_price'],value(h['instrument'],'close',h['session']),'literal source close')
    intents=read(case/'decision_intents.json');need(len(intents)==len(sessions),'all daily execution wakes');byintent={};regime=None;signal=[];detail={};target={};active=False;formed_at=None;formations=0
    for day,i in zip(sessions,intents):
        prev=cal[index[day]-1];owned=owned_byday.get(prev,{});row=byday.get(prev);equity=float(row['account_value']) if row else 1000000.;cash=float(row['cash']) if row else 1000000.
        need(i['as_of']==prev+'T15:05:00+08:00' and i['execution_session']==day and i['latest_decision_price_read']==prev and i['execution_exchange_queried_for_decision'] is False,'actual prior close clock, no execution inputs')
        payload={k:v for k,v in i.items() if k!='snapshot_sha256'};need(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==i['snapshot_sha256'],'exact snapshot hash')
        near(i['equity_at_decision'],equity,'prior NAV');near(i['cash_at_decision'],cash,'prior actual cash');need(set(owned)==set(i['holdings_at_decision']),'actual inventory identities')
        for c,q in owned.items():near(i['holdings_at_decision'][c],q,'actual units')
        closes={c:value(c,'close',prev) for c in config['symbols']};factors={c:value(c,'factor',prev) for c in config['symbols']}
        for c in closes:near(i['known_closes'][c],closes[c],'known close');near(i['known_factors'][c],factors[c],'known factor')
        formation=prev[:7]!=day[:7] if config['id']=='faber10' else prev[:4]!=day[:4]
        need(i['formation']==formation and i['regime_before']==regime and i['execution_active_before']==active,'exact period and prior execution state')
        if formation:
            formations+=1;formed_at=prev
            if config['id']=='faber10':
                monthly={}
                for d in cal[:index[day]]:monthly[d[:7]]=[d,value(STOCK,'close',d)]
                signal=list(monthly.values())[-10:];need(len(signal)==10,'ten complete calendar months')
                p=[Decimal(str(v)) for _,v in signal];mean=sum(p)/10;difference=p[-1]-mean;regime=True if difference>0 else False if difference<0 else bool(regime);fraction=Fraction(difference)
                detail={'ma10':float(mean),'close':float(p[-1]),'difference_exact':[str(fraction.numerator),str(fraction.denominator)]}
            else:target={c:floor_qty(.475*equity/closes[c],factors[c]) for c in (STOCK,BOND)};active=True
        need(i['formed_at']==formed_at and i['regime_after']==regime and i['signal_rows']==signal and i['target_normalized_units']==target,'frozen period signal/target evidence')
        need(i['signal_detail']==detail,'independent monthly indicator arithmetic')
        if config['id']=='faber10':
            if owned and not regime:expected=[{'instrument':STOCK,'side':'SELL','normalized_units':owned[STOCK]}]
            elif not owned and regime:
                budget=max(0,min(.95*equity,cash-.05*equity));q=math.floor(budget/closes[STOCK]*factors[STOCK]/100)*100/factors[STOCK];expected=[{'instrument':STOCK,'side':'BUY','normalized_units':q}] if q>0 else []
            else:expected=[]
        else:
            expected=annual_plan(target,equity,cash,owned,closes,factors,extra) if active else []
            if active and not expected:active=False
        need(i['orders']==expected and i['execution_active_after']==active,'independent funded orders and target lifecycle');byintent[day]=i
    for o in rows(case/'orders.csv'):
        planned=[p for p in byintent[o['session']]['orders'] if p['instrument']==o['instrument'] and p['side']==o['side']];need(len(planned)==1,'actual order bound to prior intent')
        near(abs(float(o['requested_normalized_units'])),planned[0]['normalized_units'],'requested size identity');q=abs(float(o['filled_normalized_units']));need(q<=planned[0]['normalized_units']+1e-7,'strict fill bound')
        if q:
            near(o['normalized_price'],value(o['instrument'],'open',o['session']),'literal primary open');need(value(o['instrument'],'buyblock' if o['side']=='BUY' else 'sellblock',o['session'])==0,'source reference allows actual fill')
        notional=abs(float(o['signed_trade_value']));near(o['cost'],max(5,notional*(5+extra)/10000) if notional else 0,'unchanged ETF fee')
    periods=independent_periods(dayrows)
    for y,p in periods.items():
        for k,v in p.items():near(v,metric['per_year'][y][k],'independent annual '+y+'/'+k)
    return {**ledger,'periods':periods,'snapshots_checked':len(intents),'formations_checked':formations,'period_rules_and_cash_reservations_recomputed':True}

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
    return {'status':'PASS_BATCH3_PERIODS_SOURCES_TARGETS_AND_ALL_LEDGERS','phase':req['phase'],'request_sha256':expected,'terminal_sha256':sha(out/'terminal.json'),'cases':checks,
        'source_checks':source,'original_replay_comparisons':prefix,'all_prior_210_files_unchanged':True,'same_researcher_not_independent_assurance':True,'investment_qualified':False,'objective_achieved':False}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('data','request','expected-sha256','run-dir','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--development-run');a=p.parse_args();result=audit(Path(__file__).resolve().parents[1],Path(a.data),Path(a.request),a.expected_sha256,Path(a.run_dir),Path(a.development_run) if a.development_run else None)
    with Path(a.out).open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(result['status'])
