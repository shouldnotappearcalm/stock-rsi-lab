"""Independent full raw ledger QA. Stdlib + two PDF readers; no production imports."""
import argparse
import ast
import copy
import csv
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path
import re

POLICY='low_asset_expansion_decile_conditional'
HELPER='2026-10-21-low-beta60-raw-daily-audit.py'
HELPER_SHA='aa8763240039be18551f2707b5cb415b0957bda446068caa1440c1604f6ae2fc'
REQUEST='experiments/qlib/asset-expansion-2026-tax-proven-account-request.json'
REQUEST_SHA='12a0394d146922707a99edecb739b5482c068e939b535f9a9a19e2974f4c3377'
REVIEW='experiments/qlib/asset-expansion-2026-tax-source-reviewed.json'
REVIEW_SHA='ba0d2e73589d7973b9ac082216590351692dd9dec8981592e36039dd65799178'
RAW='asset-expansion-raw-reconstructed-20261023'
RUN='asset-expansion-tax-proven-account-20261023'
OLD='asset-expansion-raw-development-20261022'
END='2026-10-21'

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def exit_guard(code,day,quantities,stockclaims,claims,marks,lifecycles,events):
    proof=lifecycles.get(code)
    if proof is None or day<proof['effective_date']:return False
    assert quantities.get(code,0)==0,'post-exit owned inventory'
    assert not any(c==code for c,_,_,_ in stockclaims.values()),'post-exit pending shares'
    assert not any(events[eid]['instrument']==code for eid in claims),'post-exit unpaid cash'
    marks.pop(code,None)
    return True


def finish_state(cash,lots,claims,stockclaims,registered):
    return {'cash':str(cash),'positions':{c:[{'quantity':q,'bought_on':bought,'price':str(price)}
            for q,bought,price in ls] for c,ls in lots.items() if ls},
        'registered':dict(registered),'unpaid_cash':{eid:[at,str(net)] for eid,(at,net) in claims.items()},
        'pending_stock':{str(key):list(v) for key,v in stockclaims.items()}}


def ledger_namespace():
    helper=Path(__file__).with_name(HELPER);need(sha(helper)==HELPER_SHA,'frozen independent reference')
    nodes=[n for n in ast.parse(helper.read_text()).body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
    for node in nodes:
        if isinstance(node,ast.Import):need(all(x.name in ('argparse','copy','csv','hashlib','json') for x in node.names),'stdlib reference imports')
        if isinstance(node,ast.ImportFrom):need(node.module in ('collections','datetime','decimal','pathlib','zoneinfo'),'stdlib reference imports')
    counts={'policy':0,'24':0,'179':0,'485':0,'486':0,'lifecycle_loop':0,'return_state':0}
    class Adapt(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value in (24,179,485,486):
                counts[str(node.value)]+=1
                return ast.copy_location(ast.Constant({24:34,179:141,485:676,486:677}[node.value]),node)
            if node.value in ('low_beta60','frozen monthly low_beta60 target, physical-share execution'):
                counts['policy']+=1
                return ast.copy_location(ast.Constant(node.value.replace('low_beta60',POLICY)),node)
            return node
        def visit_For(self,node):
            node=self.generic_visit(node)
            if ast.unparse(node.target)=='(c, series)' and ast.unparse(node.iter)=='bars.items()':
                counts['lifecycle_loop']+=1
                guard=ast.parse('if exit_guard(c, day, quantities, stockclaims, claims, marks, lifecycles, events):\n continue').body[0]
                node.body.insert(0,guard)
            return node
        def visit_FunctionDef(self,node):
            node=self.generic_visit(node)
            if node.name=='audit':
                returns=[v for v in ast.walk(node) if isinstance(v,ast.Return)]
                need(len(returns)==1 and isinstance(returns[0].value,ast.Dict),'one independent audit return')
                returns[0].value.keys.append(ast.Constant('independent_final_state'))
                returns[0].value.values.append(ast.parse('finish_state(cash,lots,claims,stockclaims,registered)',mode='eval').body)
                counts['return_state']+=1
            return node
    module=Adapt().visit(ast.Module(body=nodes,type_ignores=[]));ast.fix_missing_locations(module)
    need(counts=={'policy':2,'24':4,'179':2,'485':1,'486':1,'lifecycle_loop':1,'return_state':1},'only enumerated ledger adaptations')
    ns={'read':read,'sha':sha,'exit_guard':exit_guard,'finish_state':finish_state}
    exec(compile(module,str(helper),'exec'),ns)
    return ns,counts


def source_events(packets,pdf_sha):
    events={};receipts=[]
    for code,p in sorted(packets.items()):
        for row in p['distributions']:
            cash=row['dividCashPsBeforeTax'];stock=row['dividStocksPs'];capital=row['dividReserveToStockPs']
            need(cash and stock,'known raw distribution components')
            if not capital:
                need(D(cash)>0 and D(stock)==0 and row['dividCashStock'].startswith('10派')
                    and '转' not in row['dividCashStock'] and '送' not in row['dividCashStock']
                    and not row['dividStockMarketDate'],'explicit cash-only capital blank')
                capital='0'
            verified=code=='SH603737' and row['dividOperateDate']=='2026-06-01'
            if verified:need(digest(row)=='0c8930d524a9a657993f8fa516adf68f7abc0ddf2a023df6ab26b3027bc9e479','exact independently reviewed distribution')
            primary=[pdf_sha] if verified else []
            identity={'instrument':code,'source_kind':'VENDOR_DISTRIBUTION','source_distribution':row,
                'primary_source_sha256':primary,'effective_stock_taxable_income_per_original_share':'0',
                'capital_tax_exempt_verified':verified,'stock_tax_basis_verified':False}
            eid=digest(identity);need(eid not in events,'unique source event identity')
            events[eid]={'event_id':eid,'instrument':code,'announced':row['dividPlanDate'],'recorded':row['dividRegistDate'],
                'ex_date':row['dividOperateDate'],'pay_date':row['dividPayDate'] or None,'listed':row['dividStockMarketDate'] or None,
                'cash_per_share':cash,'capital_per_share':capital,'capital_tax_exempt_verified':verified,
                'stock_per_share':stock,'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False}
            receipts.append({'event_id':eid,'instrument':code,'ex_date':row['dividOperateDate'],
                'source_kind':'VENDOR_DISTRIBUTION','source_row_sha256':digest(row),'primary_source_sha256':primary,
                'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),
                'requires_zero_record_ownership_if_tax_unverified':D(capital)>0 and not verified or D(stock)>0})
    need(len(events)==141 and sum(v['capital_tax_exempt_verified'] for v in events.values())==1,'141 events with one proof')
    return events,receipts


def stated_for_reference(case,stated,bars,ns):
    rows=[r for r in case['rows'] if r['day']>='2024-01-02'];peak=D('1000000');dd=D(0)
    for row in rows:peak=max(peak,D(row['equity']));dd=min(dd,D(row['equity'])/peak-1)
    capacity=max((D(f['quantity'])/D(bars[f['security_id']][ns['localday'](f['execution_at'])]['volume'])
                  for f in case['fills']),default=D(0))
    return {'2024_return_pct':stated['2024_return_pct'],'2025_return_pct':stated['2025_return_pct'],
        'average_exposure_pct':float(sum((D(r['exposure']) for r in rows),D(0))/len(rows)*100),
        'max_drawdown_pct':float(dd*100),'max_order_fraction_of_whole_day_volume':float(capacity),
        'fills':stated['fills'],'orders':stated['orders'],'whole_day_volume_violations':stated['whole_day_volume_violations']}


def check_observations(obs,case,result,events,sessions):
    final=obs['final_state'];independent=result['independent_final_state']
    assert final['last_clock']==[END,1] and final['cash']==independent['cash']
    assert final['positions']==independent['positions'] and final['entitlements']==independent['registered']
    assert final['orders']==case['orders'] and final['fills']==case['fills'] and final['corporate_ledger']==case['corporate_ledger']
    cashclaims=[];stockclaims=[]
    cents=lambda v:v.quantize(D('.01'),rounding='ROUND_HALF_UP')
    for entry in case['corporate_ledger']:
        if entry['kind']!='EX_DATE_ENTITLEMENT':continue
        e=events[entry['event_id']];q=entry['registered_quantity'];gross=cents(D(e['cash_per_share'])*q)
        reserve=cents(gross*D('.2'))
        if gross:
            available=next((day for day in sessions if day>e['pay_date']),None)
            cashclaims.append({'event_id':e['event_id'],'instrument':e['instrument'],'gross':str(gross),
                'reserve':str(reserve),'net':str(gross-reserve),'available_on':available,
                'paid':available is not None and available<=END})
        for ratio,kind in ((e['capital_per_share'],'CAPITAL_TRANSFER'),(e['stock_per_share'],'STOCK_DIVIDEND')):
            quantity=D(ratio)*q
            if quantity:
                assert quantity==int(quantity)
                stockclaims.append({'event_id':e['event_id'],'instrument':e['instrument'],'quantity':int(quantity),
                    'listed':e['listed'],'recorded':e['recorded'],'credited':e['listed']<=END,'share_kind':kind})
    assert final['cash_claims']==cashclaims and final['stock_claims']==stockclaims
    assert final['owned']=={c:sum(lot['quantity'] for lot in ls) for c,ls in independent['positions'].items()}
    assert obs['prior_partial_state_verified'] is True and obs['prefix_checks']['passed'] is True
    assert len(obs['exit_checks'])==136
    for check in obs['exit_checks']:
        assert check['instrument']=='SH603056' and check['day']>='2026-03-31'
        assert all(check[k]==0 for k in ('owned','pending_orders','unpaid_cash_claims','uncredited_stock_claims'))
        assert check['future_entitled_events']==[]
    proven=next(e for e in events.values() if e['capital_tax_exempt_verified'])
    assert independent['registered'][proven['event_id']]==2700
    assert [c['quantity'] for c in stockclaims if c['event_id']==proven['event_id']]==[540]


def check_prefix(case,obs,old_folder,old_ids):
    with (old_folder/'daily.csv').open() as f:oldrows=list(csv.DictReader(f))
    assert [r for r in case['rows'] if r['day']<='2025-12-31']==oldrows
    assert {k:v for k,v in case['ownership'].items() if k<='2025-12-31'}==read(old_folder/'ownership.json')
    assert [x for x in case['intents'] if x['execution_session']<='2025-12-31']==read(old_folder/'intents.json')
    assert [x for x in case['corporate_ledger'] if x['event_id'] in old_ids and x['day']<='2025-12-31']==read(old_folder/'corporate_ledger.json')
    checkpoint=obs['checkpoint'];assert checkpoint['cash']==oldrows[-1]['cash']
    for k in ('orders','fills'):assert checkpoint[k]==read(old_folder/(k+'.json'))
    assert checkpoint['owned']==read(old_folder/'ownership.json')['2025-12-31']


def compare_2026(case,stated):
    nav={r['day']:D(r['equity']) for r in case['rows']};start=nav['2025-12-31']
    selected=[r for r in case['rows'] if r['day']>'2025-12-31'];peak=start;dd=D(0)
    for r in selected:peak=max(peak,D(r['equity']));dd=min(dd,D(r['equity'])/peak-1)
    actual={'return_pct':float((nav[END]/start-1)*100),'starting_equity_CNY':str(start),'ending_equity_CNY':str(nav[END]),
        'sessions':len(selected),'max_drawdown_pct':float(dd*100),
        'average_exposure_pct':float(sum((D(r['exposure']) for r in selected),D(0))/len(selected)*100),
        'fees_CNY':str(sum((D(r['fees']) for r in selected),D(0)))}
    assert actual==stated['2026_through_'+END]
    passes=stated['2024_return_pct']>0 and stated['2025_return_pct']>0 and actual['return_pct']>=10
    assert passes==stated['three_return_conditions_met']
    return actual


def run_audit(repo,base,run):
    need(sha(repo/REQUEST)==REQUEST_SHA,'frozen account request hash')
    request=read(repo/REQUEST);summary=read(run/'summary.json')
    need((repo/REQUEST).read_bytes()==(run/'request.json').read_bytes(),'same frozen private/public request')
    need(summary['request_sha256']==REQUEST_SHA and summary['complete'] is True and not summary['changed_inputs']
        and not summary['persistence_errors'] and summary['original_error'] is None and not summary['pending_cost_cases'],'complete two-case run')
    inputs=read(run/'inputs-before.json');need(inputs=={**{str(({'repo':repo,'source':base}[k.split('/',1)[0]]/k.split('/',1)[1]).resolve()):h
        for k,h in request['bound_sha256'].items()},str((repo/REQUEST).resolve()):REQUEST_SHA},'complete bound account inputs')
    need(read(run/'inputs-after.json')=={'consumed_files':len(inputs),'changed_or_missing':[],'unchanged':True},'unchanged account inputs')
    before=inventory(run)
    for p,h in inputs.items():need(sha(p)==h,'bound input '+p)
    primary=read(repo/REVIEW);need(sha(repo/REVIEW)==REVIEW_SHA and not primary['changed_inputs'],'checked issuer proof')
    pdf=base/primary['primary_file'];need(sha(pdf)==primary['primary_sha256'],'original primary bytes')
    source_helper=repo/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-source-review-v2.py'
    source_tree=ast.parse(source_helper.read_text());source_nodes=[n for n in source_tree.body if isinstance(n,ast.FunctionDef) and n.name in ('need','table_dates','text_facts')]
    need(len(source_nodes)==3,'only reviewed source-fact helpers')
    source_ns={'re':re};exec(compile(ast.Module(body=source_nodes,type_ignores=[]),str(source_helper),'exec'),source_ns)
    from pypdf import PdfReader
    from pdfminer.high_level import extract_text
    document=PdfReader(pdf);need(len(document.pages)==4,'fourpage original')
    need(source_ns['text_facts'](''.join(page.extract_text() for page in document.pages))==primary['primary_facts']
        and source_ns['text_facts'](extract_text(pdf))==primary['primary_facts'],'primary facts two readers')
    sourceqa=read(repo/'experiments/qlib/asset-expansion-2026-source-reconstruction-audit.json')
    need(sourceqa['all_inputs_and_outputs_unchanged'] is True and len(sourceqa['all_reconstruction_output_sha256'])==100,'separate complete raw QA')
    for p,h in sourceqa['all_reconstruction_output_sha256'].items():need(sha(p)==h,'all100 source outputs')
    raw=base/RAW;manifest=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions'];lifecycles=read(raw/'lifecycles.json')
    need(len(sessions)==677 and sessions==sorted(set(sessions)) and sessions[0]=='2023-12-29' and sessions[-1]==END,'explicit677sessions')
    need(set(lifecycles)=={'SH603056'} and lifecycles['SH603056']['kind']=='DELISTING_END'
        and lifecycles['SH603056']['verified_primary_boundary'] is True and lifecycles['SH603056']['effective_date']=='2026-03-31','one authenticated exit')
    packets={};bars={}
    for code,h in manifest['per_code_sha256'].items():
        p=raw/'codes'/(code+'.json');need(sha(p)==h,'actual raw packet');packet=read(p)
        active=[d for d in sessions if code not in lifecycles or d<lifecycles[code]['effective_date']]
        need(packet['instrument']==code and [r['date'] for r in packet['bars']]==active
            and packet['window']==[sessions[0],active[-1]] and not packet['quarantine'],'complete active source window')
        packets[code]=packet;bars[code]={r['date']:r for r in packet['bars']}
    need(len(packets)==47,'all47 source dependencies')
    events,receipts=source_events(packets,primary['primary_sha256']);projection=read(run/'source_projection.json')
    need(list(events.values())==projection['events'] and receipts==projection['event_receipts'],'independently reconstructed141 events/receipts')
    oldevents=read(base/OLD/'source_projection.json')['events'];oldids={e['event_id'] for e in oldevents}
    need([e for e in events.values() if e['event_id'] in oldids]==oldevents and sorted(oldids)==projection['old_event_ids'],'exact old79 source events')
    targets=read(repo/'experiments/qlib/asset-expansion-2026-targets.json')[POLICY]
    need(len(targets)==34 and {c for t in targets.values() for c in t['weights']}==set(packets),'all34 target dependency union')
    ns,changes=ledger_namespace();ns.update(sessions=sessions,bars=bars,events=events,targets=targets,lifecycles=lifecycles)
    cases={};observations={};refs={};results={}
    for bps in ('20','40'):
        stated=summary['results_by_extra_bps'][bps];need(stated['status']=='RAW_DAILY_PROXY_COMPLETE_PENDING_SEPARATE_LEDGER_QA','complete case')
        for name,h in stated['artifact_sha256'].items():need(sha(run/bps/name)==h,'raw case artifact')
        case={k:read(run/bps/(k+'.json')) for k in ('orders','fills','corporate_ledger','ownership','intents')}
        with (run/bps/'daily.csv').open() as f:case['rows']=list(csv.DictReader(f))
        obs=read(run/bps/'account_observations.json');ref=stated_for_reference(case,stated,bars,ns)
        result=ns['audit'](case,int(bps),ref);check_observations(obs,case,result,events,sessions)
        check_prefix(case,obs,base/OLD/bps,oldids)
        result['2026_through_'+END]=compare_2026(case,stated)
        cases[bps]=case;observations[bps]=obs;refs[bps]=ref;results[bps]=result
    negatives={}
    for name in ('erased_fee','forged_daily_equity','false_registered_quantity','forged_snapshot','missing_540_shares','false_post_exit_claim'):
        case=copy.deepcopy(cases['40']);obs=copy.deepcopy(observations['40'])
        if name=='erased_fee':case['fills'][0]['cost']='0'
        elif name=='forged_daily_equity':case['rows'][-1]['equity']=str(D(case['rows'][-1]['equity'])+1)
        elif name=='false_registered_quantity':next(e for e in case['corporate_ledger'] if e['kind']=='EX_DATE_ENTITLEMENT' and e['capital_shares']==540)['registered_quantity']+=1
        elif name=='forged_snapshot':case['intents'][0]['snapshot_sha256']='0'*64
        elif name=='missing_540_shares':next(e for e in case['corporate_ledger'] if e['kind']=='CAPITAL_SHARES_LISTED' and e['quantity']==540)['quantity']=0
        else:obs['final_state']['cash_claims'].append({'instrument':'SH603056','paid':False})
        try:
            independent=ns['audit'](case,40,refs['40']);check_observations(obs,case,independent,events,sessions)
        except (AssertionError,KeyError,ValueError):negatives[name]=True
        else:raise ValueError('arithmetic negative accepted: '+name)
    for p,h in inputs.items():need(sha(p)==h,'bound input after '+p)
    need(inventory(run)==before,'all actual run outputs unchanged through QA')
    return {'status':'SEPARATE_FULL_141_EVENT_34_SNAPSHOT_TWO_COST_LEDGER_PASSED',
        'request_sha256':REQUEST_SHA,'summary_sha256':sha(run/'summary.json'),'only_reference_AST_adaptations':changes,
        'results_by_extra_bps':results,'arithmetic_negative_controls_rejected':negatives,
        'negative_controls_use_artifact_hash_gate':False,'all_actual_output_sha256':before,
        'all_bound_input_sha256':inputs,'all100_source_outputs_authenticated':True,
        'primary_pdf_two_extractors_all4pages':True,'imports_production_account_broker_or_compiler':False,
        'historical_arrival_verified':False,'opening_auction_liquidity_verified':False,'full_october_complete':False,
        'sealed_2026_evidence':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();repo=Path(a.repo_root);base=Path(a.source_root);out=Path(a.output)
    need(not out.exists(),'fresh independent QA output required')
    result=None;error=None
    try:result=run_audit(repo,base,base/RUN)
    except BaseException as exc:
        error=exc;result={'status':'INDEPENDENT_LEDGER_QA_FAILURE_RETAINED','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False}
    result['audit_code_sha256']=sha(Path(__file__))
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    if error is not None:raise error
    print(result['status'],flush=True)

if __name__=='__main__':main()
