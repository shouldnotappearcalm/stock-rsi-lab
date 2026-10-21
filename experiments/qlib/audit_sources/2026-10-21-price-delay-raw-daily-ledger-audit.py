"""Independent Decimal ledger reconstruction of observed PRE2026 orders/fills.
Stdlib only; no project imports, production replay/summarize/reconcile or network.
Does not generate new strategy decisions/outcomes; checks frozen observed artifacts.
"""
from pathlib import Path
from decimal import Decimal as D,ROUND_HALF_UP,ROUND_DOWN
from collections import defaultdict,Counter
import ast,csv,hashlib,json,subprocess
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
O=B/'price-delay-raw-daily-pre2026-20261021'
PLAN=R/'experiments/qlib/price-delay-raw-daily-plan.json'
REPORT=Path('/tmp/price-delay-raw-daily-independent-ledger-audit-20261021.json')
EXPECTED='9d6ece8670a62f17acd31d9a82175b8d289b74b45465e5064bd99cdd1bd83a45'
CENT=D('.01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(v):return hashlib.sha256(canon(v).encode()).hexdigest()
def need(ok,msg):
    if not ok:raise AssertionError(msg)
def cents(v):return v.quantize(CENT,rounding=ROUND_HALF_UP)
def same(a,b,msg):need(D(str(a))==D(str(b)),msg+': '+str(a)+' != '+str(b))
def metric_same(a,b,msg):need(abs(D(str(a))-D(str(b)))<D('0.000000000001'),msg)
def clean(v):
    if isinstance(v,D):return str(v)
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
    if isinstance(v,list):return [clean(x) for x in v]
    return v

def main():
    plan=read(PLAN);summary=read(O/'summary.json');freeze=subprocess.check_output(['git','rev-parse','2aaa47c'],cwd=R,text=True).strip()
    need(sha(PLAN)==EXPECTED==summary['plan_sha256'],'external frozen plan')
    need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(PLAN.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen plan blob')
    tree=ast.parse((R/'scripts/run_price_delay_raw_pre2026.py').read_text());constants={}
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('METHOD_FILES','LOCAL_FILES','PUBLIC_FILES'):constants[n.targets[0].id]=ast.literal_eval(n.value)
    for field,root,key in [('method_code_sha256',R,'METHOD_FILES'),('local_source_sha256',B,'LOCAL_FILES'),('public_evidence_sha256',R,'PUBLIC_FILES')]:
        need(set(plan[field])==set(constants[key]),'exact binding scope '+field)
        for n,h in plan[field].items():
            need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(root/n)==h,'bound identity '+n)
            if root==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)).hexdigest()==h,'freeze identity '+n)
    need(summary['method_code_sha256']==plan['method_code_sha256'] and sha(R/plan['protocol_file'])==plan['protocol_sha256'],'summary methods/protocol')
    need(plan['initial_CNY']=='1000000' and plan['extra_cost_bps']==[20,40] and plan['window']==['2023-12-29','2025-12-31'] and plan['policy_id']=='price_delay_d1','fixed scope')
    raw=B/'price-delay-raw-dev-20261021';src=B/'price-delay-account-source-events-20261021';rm=read(raw/'manifest.json');ss=read(src/'summary.json');sourceaudit=read(B/'price-delay-event-source-independent-audit-20261021.json');proof=read(src/'effective_proofs.json')
    need(sourceaudit['status']=='INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED' and sourceaudit['events_reconstructed']==378 and sourceaudit['summary_sha256']==sha(src/'summary.json') and sourceaudit['all378_economics_dates_event_IDs_and_receipts_identical'] is True and not sourceaudit['critical_or_important_findings'],'reuse bound independent source audit')
    need(sourceaudit['all151_source_packets_authenticated'] and sourceaudit['all15_primary_PDF_bytes_and_two_content_reviews_authenticated'] and sourceaudit['strict_statutory_capital_tax_certification'] is False,'source evidence scope')
    for n,h in ss['artifact_sha256'].items():need(sha(src/n)==h,'source artifact')
    sessions=read(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==plan['window'],'486 sessions')
    bars={}
    for c,h in rm['per_code_sha256'].items():
        p=raw/'codes'/(c+'.json');need(sha(p)==h==ss['source_packet_sha256'][c],'raw source identity');v=read(p);need(v['instrument']==c and v['window']==plan['window'] and [x['date'] for x in v['bars']]==sessions,'raw pre2026 dates');bars[c]={x['date']:x for x in v['bars']}
    need(len(bars)==151,'151 source names')
    targetfile=B/'price-delay-pre2026-formations-20261021/targets.json';targets=read(targetfile)['price_delay_d1'];need(sha(targetfile)==rm['target_sha256']==ss['target_sha256'] and len(targets)==24,'frozen targets')
    events=read(src/'derived_events.json');ev={e['event_id']:e for e in events};need(len(events)==len(ev)==378,'378 distinct event identities')
    approved={e['instrument']+'|'+e['ex_date'] for e in events if e['capital_tax_exempt_verified'] is True}
    need(approved==set(proof['capital_tax']) and len(approved)==4 and proof['direct_primary_capital_tax_statements']==3 and proof['conditional_capital_tax_inferences']==1 and proof['strict_statutory_capital_tax_certification'] is False,'limited four capital flags preserved')
    unknown=[e for e in events if e['instrument']=='SH603596' and e['ex_date']=='2024-05-20'];need(len(unknown)==1 and unknown[0]['capital_tax_exempt_verified'] is False,'unknown tax guard remains')
    for key,ratio in sourceaudit['primary_cash_supplements'].items():
        c,d=key.split('|');e=next(e for e in events if e['instrument']==c and e['ex_date']==d);same(e['cash_per_share'],ratio,'primary actual shareholder cash ratio')
    records=defaultdict(list);exes=defaultdict(list)
    for e in events:records[e['recorded']].append(e);exes[e['ex_date']].append(e)
    prior={sessions[i]:sessions[i-1] for i in range(1,len(sessions))};following={sessions[i]:sessions[i+1] for i in range(len(sessions)-1)}
    financial={};results={}
    need(set(summary['results_by_extra_bps'])=={'20','40'} and read(O/'case_results.json')==summary['results_by_extra_bps'],'two cases')
    for bps in (20,40):
        s=summary['results_by_extra_bps'][str(bps)];folder=O/str(bps);need(s['status']=='RAW_DAILY_PROXY_RECONCILED','completed account status')
        need(set(s['artifact_sha256'])=={'daily.csv','intents.json','fills.json','orders.json','corporate_ledger.json','ownership.json'},'six financial artifact scope')
        for n,h in s['artifact_sha256'].items():need(sha(folder/n)==h,'financial hash');financial[str(bps)+'/'+n]=h
        with (folder/'daily.csv').open() as f:days=list(csv.DictReader(f))
        need([r['day'] for r in days]==sessions,'all486 daily observations')
        fills=read(folder/'fills.json');orders=read(folder/'orders.json');ledger=read(folder/'corporate_ledger.json');ownership=read(folder/'ownership.json');intents=read(folder/'intents.json');need(list(ownership)==sessions,'ownership486')
        need(len({o['order_id'] for o in orders})==len(orders) and len({f['order_id'] for f in fills})==len(fills),'unique orders/fills')
        ordermap={o['order_id']:o for o in orders};fillmap={f['order_id']:f for f in fills};need(set(fillmap)<=set(ordermap),'all fills have orders')
        byday=defaultdict(list)
        for o in orders:
            need(type(o['quantity']) is int and 0<o['quantity']<=1000000 and o['action'] in ('BUY','SELL'),'valid integer order');need(o['eligible_at'] is not None and o['eligible_at'][:10] in sessions,'known eligible session');byday[o['eligible_at'][:10]].append(o)
        byintent={i['execution_session']:i for i in intents};need(list(byintent)==list(targets) and len(intents)==24,'24 intent execution dates')
        cash=D('1000000');lots=defaultdict(list);claims=[];cashclaims=[];ent={};marks={};expectedledger=[];observedfills=[];nav={};exposure=[];peak=cash;dd=D(0);previous_equity=cash;maxvol=D(0);feesall=D(0);turnoverall=D(0);pendingdays=0;snapshotcount=0
        def circulation():return {c:sum(l['q'] for l in ls) for c,ls in lots.items() if ls}
        def owned():
            out=circulation()
            for cl in claims:
                if not cl['credited']:out[cl['instrument']]=out.get(cl['instrument'],0)+cl['quantity']
            return out
        for row in days:
            day=row['day'];daycorp=[];credit=D(0);fees=D(0)
            # Calendar availability is strictly after the published payment date.
            for cl in cashclaims:
                if not cl['paid'] and cl['available']==day:
                    cash+=cl['net'];credit+=cl['net'];cl['paid']=True;daycorp.append({'day':day,'kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':cl['event_id'],'cash_delta':str(cl['net'])})
            for e in exes[day]:
                q=ent[e['event_id']];cap=D(e['capital_per_share'])*q;stock=D(e['stock_per_share'])*q
                need(cap==cap.to_integral_value() and stock==stock.to_integral_value(),'whole corporate shares')
                need(not(q and cap>0) or e['capital_tax_exempt_verified'] is True,'positive-owned capital tax guard')
                need(not(q and stock>0) or e['stock_tax_basis_verified'] is True,'bonus stock guard')
                gross=cents(D(e['cash_per_share'])*q);income=cents(D(e['stock_taxable_income_per_share'])*q);reserve=cents((gross+income)*D('.2'));need(reserve<=gross,'supported reserve')
                if gross:cashclaims.append({'event_id':e['event_id'],'net':gross-reserve,'available':next((d for d in sessions if d>e['pay_date']),None),'paid':False})
                for amount,kind in ((int(cap),'CAPITAL_TRANSFER'),(int(stock),'STOCK_DIVIDEND')):
                    if amount:claims.append({'event_id':e['event_id'],'instrument':e['instrument'],'quantity':amount,'listed':e['listed'],'recorded':e['recorded'],'credited':False,'kind':kind})
                daycorp.append({'day':day,'kind':'EX_DATE_ENTITLEMENT','event_id':e['event_id'],'instrument':e['instrument'],'registered_quantity':q,'cash_gross':str(gross),'stress_tax_reserve':str(reserve),'capital_shares':int(cap),'stock_shares':int(stock),'taxable_stock_income':str(income)})
            for cl in claims:
                if not cl['credited'] and cl['listed']<=day:
                    lots[cl['instrument']].append({'q':cl['quantity'],'day':cl['recorded'],'price':D(0)});cl['credited']=True
                    daycorp.append({'day':day,'kind':'CAPITAL_SHARES_LISTED' if cl['kind']=='CAPITAL_TRANSFER' else 'STOCK_DIVIDEND_SHARES_LISTED','event_id':cl['event_id'],'quantity':cl['quantity']})
            dayorders=sorted(byday[day],key=lambda o:(o['action']!='SELL',o['security_id']))
            for o in dayorders:
                c=o['security_id'];action=o['action'];r=bars[c][day];need(r['isST']=='0' and r['tradestatus'] in ('0','1'),'known ordinary state')
                blocked=r['tradestatus']=='0' or action=='BUY' and D(r['open'])>=D(r['preclose'])*D('1.095') or action=='SELL' and D(r['open'])<=D(r['preclose'])*D('.905')
                if blocked:need(o['status']=='UNFILLED_MARKET_CONSTRAINT' and o['order_id'] not in fillmap,'blocked order absent fill');continue
                p=D(r['open']);q=o['quantity'];need(p==cents(p),'cent-tick raw open')
                if action=='SELL':need(q<=sum(l['q'] for l in lots[c] if l['day']<day),'T+1 available FIFO lots')
                gross=p*q;base=cents(max(D(5),gross*D(5 if action=='BUY' else 15)/10000));extra=cents(gross*D(bps)/10000);cost=base+extra
                need(o['order_id'] in fillmap,'nonblocked full order must have fill in this output');f=fillmap[o['order_id']]
                need(f['execution_at']==day+'T01:30:00+00:00' and f['security_id']==c and f['action']==action and type(f['quantity']) is int and f['quantity']==q and o['status']=='FILLED','fill/order exact full quantity/time')
                same(f['price'],p,'actual raw open fill');same(f['cost'],cost,'independent base+extra fees')
                if action=='BUY':need(q%100==0 and cash>=gross+cost,'100share buy affordability');cash-=gross+cost;lots[c].append({'q':q,'day':day,'price':p})
                else:
                    cash+=gross-cost;remaining=q
                    for l in lots[c]:
                        if l['day']>=day:continue
                        removed=min(remaining,l['q']);l['q']-=removed;remaining-=removed
                    need(remaining==0,'FIFO removal complete');lots[c]=[l for l in lots[c] if l['q']]
                same(cash,f['cash_after'],'fill cash_after');need(cash>=0 and cash==cents(cash),'nonnegative cent cash');fees+=cost;feesall+=cost;turnoverall+=gross
                vol=D(r['volume']);need(vol>=q and vol>0,'whole-day necessary volume cap');maxvol=max(maxvol,D(q)/vol);observedfills.append(f)
            # Mark only with raw observations and documented suspension convention.
            for c,rows in bars.items():
                r=rows[day]
                if r['tradestatus']=='1':marks[c]=D(r['close'])
                elif any(e['instrument']==c for e in exes[day]):marks[c]=D(r['preclose'])
                elif c not in marks and r['close'] and D(r['close'])>0:marks[c]=D(r['close'])
            circ=circulation();own=owned();need(circ==ownership[day],'circulating integer inventory')
            for e in records[day]:
                need(not any(not cl['credited'] and cl['instrument']==e['instrument'] for cl in claims),'no overlapping unlisted entitlement')
                q=circ.get(e['instrument'],0);ent[e['event_id']]=q;daycorp.append({'day':day,'kind':'RECORD_DATE_OWNERSHIP','event_id':e['event_id'],'instrument':e['instrument'],'quantity':q})
            market=sum((q*marks[c] for c,q in circ.items()),D(0));pending=sum((cl['quantity']*marks[cl['instrument']] for cl in claims if not cl['credited']),D(0));receivable=sum((cl['net'] for cl in cashclaims if not cl['paid']),D(0));equity=cash+market+pending+receivable
            if pending:pendingdays+=1
            expectedvalues={'cash':cash,'market_value':market,'pending_stock_value':pending,'cash_receivable':receivable,'equity':equity,'net_return':equity/previous_equity-1,'exposure':(market+pending)/equity,'fees':fees,'net_dividend_cash_available':credit}
            for k,v in expectedvalues.items():same(row[k],v,'daily '+str(bps)+' '+day+' '+k)
            nav[day]=equity;expectedledger.extend(daycorp);previous_equity=equity
            if day>='2024-01-02':exposure.append(expectedvalues['exposure']);peak=max(peak,equity);dd=min(dd,equity/peak-1)
            if day in following and following[day] in targets:
                exday=following[day];target=targets[exday];i=byintent[exday];asof=day+'T07:05:00+00:00';need(target['as_of']==day and i['as_of']==asof and i['owned_integer_shares']==own,'prior-close intent shares/clock');same(i['equity_at_decision'],equity,'intent continuous wealth')
                expecteddecisions=[]
                for c in sorted(set(own)|set(target['weights'])):
                    held=own.get(c,0);w=D(str(target['weights'].get(c,0)))
                    if not w:q=held;action='SELL'
                    else:
                        need(bars[c][day]['tradestatus']=='1','prior-close target tradable')
                        desired=int((equity*w/marks[c]/100).to_integral_value(rounding=ROUND_DOWN))*100
                        if desired>held:q=(desired-held)//100*100;action='BUY'
                        else:q=held-desired;action='SELL'
                    if q:expecteddecisions.append((action,c,q))
                expecteddecisions.sort(key=lambda d:(d[0]!='SELL',d[1]));need([(d['action'],d['security_id'],d['quantity']) for d in i['decisions']]==expecteddecisions,'actual target integer quantities')
                # Independently rebuild complete decision snapshot from reconstructed lots.
                positions={}
                for c,ls in lots.items():
                    if not ls:continue
                    q=sum(l['q'] for l in ls);positions[c]={'quantity':q,'average_price':str(sum((l['price']*l['q'] for l in ls),D(0))/q),'mark_price':str(marks[c]),'mark_source':'VISIBLE_PRICE'}
                wealth={'cash':cash,'positions':positions,'market_value':market,'cash_receivable':receivable,'pending_stock_value':pending,'equity':equity}
                record={'record_id':digest({'policy':'price_delay_d1','formation':day,'target':target}),'kind':'frozen_target','available_at':asof,'payload':target};visible=[record]
                for c in sorted(set(own)|set(target['weights'])):
                    content={'instrument':c,'as_of':day,'known_mark':str(marks[c]),'source_bar':bars[c][day]};visible.append({'record_id':digest(content),'kind':'raw_market_state','available_at':asof,'payload':content})
                snap=digest({'as_of':asof,'records':visible,'account':clean(wealth)});need(i['snapshot_sha256']==snap,'complete reconstructed snapshot hash');snapshotcount+=1
                for d in i['decisions']:
                    need(d['evidence_ids']==[record['record_id']] and d['reason']=='frozen monthly price_delay_d1 target, physical-share execution','decision evidence')
                    did=digest({'decision':d,'snapshot':snap});expiry=exday+'T01:30:00+00:00';oid=digest({'decision_id':did,'at':asof,'expires_at':expiry});o=ordermap[oid]
                    need(o['decision_id']==did and o['submitted_at']==asof and o['eligible_at']==o['expires_at']==expiry and (o['action'],o['security_id'],o['quantity'])==(d['action'],d['security_id'],d['quantity']),'decision/order complete identity')
        need(observedfills==fills,'all fills reconstructed in order')
        need(expectedledger==ledger,'all corporate ledger rows reconstructed exactly')
        need(len(ent)==378 and Counter(x['kind'] for x in ledger)['EX_DATE_ENTITLEMENT']==378,'all378 record and ex coverage')
        uid=unknown[0]['event_id'];need(ent[uid]==0,'SH603596 May17 zero actual record ownership')
        recomputed={'2024_return_pct':(nav['2024-12-31']/D('1000000')-1)*100,'2025_return_pct':(nav['2025-12-31']/nav['2024-12-31']-1)*100,'average_exposure_pct':sum(exposure,D(0))/485*100,'max_drawdown_pct':dd*100,'max_order_fraction_of_whole_day_volume':maxvol}
        for k,v in recomputed.items():metric_same(s[k],v,'summary metric '+k)
        need(s['fills']==len(fills) and s['orders']==len(orders) and s['monthly_decisions']==24 and s['account_sessions']==485 and s['whole_day_volume_violations']==0,'summary counts')
        results[str(bps)]={'status':'ALL_OBSERVED_LEDGER_IDENTITIES_RECONSTRUCTED','source_days':486,'trading_account_days':485,'fills_reconstructed':len(fills),'orders_checked':len(orders),'corporate_ledger_rows':len(ledger),'record_and_ex_events':378,'all24_integer_target_decisions_and_snapshot_SHA_identical':snapshotcount==24,'T_plus_1_and_FIFO_sellable_lots_checked':True,'circulating_inventory_pending_claims_and_receivables_reconstructed':True,'raw_close_valuation_all486days_exact':True,'separately_rounded_base_and_extra_fees_CNY':str(feesall),'gross_turnover_CNY':str(turnoverall),'nav_CNY':{d:str(nav[d]) for d in ['2023-12-29','2024-12-31','2025-12-31']},'recomputed_metrics':clean(recomputed),'days_with_positive_pending_stock_value':pendingdays,'ending_cash_CNY':str(cash),'ending_circulating_integer_shares':circulation(),'SH603596_2024_05_17_registered_quantity':ent[uid],'SH603596_capital_tax_flag_remains_false':True}
    need(summary['raw_daily_proxy_development_gate_passes'] is True and summary['objective_achieved'] is False and summary['minute_execution_admitted'] is False and summary['2026_return_computed'] is False,'bounded daily development status')
    report={'status':'PASS_INDEPENDENT_PRE2026_RAW_DAILY_DECIMAL_LEDGER_AUDIT','freeze_commit':freeze,'plan_sha256':EXPECTED,'summary_sha256':sha(O/'summary.json'),'audit_script_sha256':sha(Path(__file__)),'binding_scope_counts':{'method':len(plan['method_code_sha256']),'local':len(plan['local_source_sha256']),'public':len(plan['public_evidence_sha256'])},'method_sha256':plan['method_code_sha256'],'all12_financial_artifact_sha256':financial,'all151_raw_source_packet_sha256':rm['per_code_sha256'],'source_audit_sha256':sha(B/'price-delay-event-source-independent-audit-20261021.json'),'source_audit_economics_identity_evidence_reused_without_reparsing_PDFs':True,'all378_source_events_and_15_PDF_review_bindings_unchanged':True,'capital_flags':{'direct_statements':3,'conditional_inference':1,'strict_statutory_certification':False,'unverified_SH603596_requires_and_has_zero_record_ownership':True},'primary_actual_cash_ratios':sourceaudit['primary_cash_supplements'],'results_by_extra_bps':results,'daily_proxy_development_gate_passes_independently':True,'execution_evidence':'DAILY_PROXY_ONLY','minute_execution_verified':False,'PIT_or_historical_arrival_certified':False,'actual_FIFO_tax_liability_verified':False,'2026_values_or_results_read':False,'portfolio_replay_rerun':False,'production_simulate_summarize_reconcile_imported_or_called':False,'repository_or_source_outputs_modified':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Independent ledger reconstruction of observed frozen pre2026 daily-proxy outputs; no new account replay or strategy search.','FIFO lot availability is reconstructed for sellable shares; the cash+bonus20%stress reserve is not actual FIFO dividend tax settlement.','Daily open fills and whole-day volume are proxy/necessary checks only; no opening-auction depth, queue, impact or minute execution proof.','Three direct capital-source statements and one conditional inference retain their bound evidence level; no strict statutory tax certification.','Seven later adjustment labels remain source-labelled without invented second entitlements; full corporate-action completeness and historical arrival remain uncertified.']}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'sha256':sha(REPORT),'audit_script_sha256':report['audit_script_sha256'],'cases':2,'days_each':486,'events_each':378,'snapshot_hashes':48,'financial_files':len(financial),'metrics':{k:v['recomputed_metrics'] for k,v in results.items()}},ensure_ascii=False))
if __name__=='__main__':main()
