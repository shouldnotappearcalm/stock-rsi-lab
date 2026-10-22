"""Original source events plus adapted prior separate ledger; no production imports."""
import argparse,ast,copy,hashlib,json
from decimal import Decimal
from pathlib import Path

CANDIDATE='low_asset_expansion_decile_conditional'
RAW='asset-expansion-raw-pre2026-20261022'
HELPER='2026-10-21-low-beta60-raw-daily-audit.py'
HELPER_SHA='aa8763240039be18551f2707b5cb415b0957bda446068caa1440c1604f6ae2fc'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}


def ledger_namespace(event_count):
    helper=Path(__file__).with_name(HELPER);need(sha(helper)==HELPER_SHA,'previous separate ledger code pinned')
    tree=ast.parse(helper.read_text());nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
    for n in nodes:
        if isinstance(n,ast.Import):need(all(v.name.split('.')[0] in {'argparse','copy','csv','hashlib','json'} for v in n.names),'stdlib helper imports')
        if isinstance(n,ast.ImportFrom):need(n.module in {'collections','datetime','decimal','pathlib','zoneinfo'},'stdlib helper imports')
    class Adapt(ast.NodeTransformer):
        def __init__(self):self.counts={'policy':0,'event_count':0}
        def visit_Constant(self,node):
            if node.value=='low_beta60':self.counts['policy']+=1;return ast.copy_location(ast.Constant(CANDIDATE),node)
            if node.value=='frozen monthly low_beta60 target, physical-share execution':
                self.counts['policy']+=1;return ast.copy_location(ast.Constant('frozen monthly '+CANDIDATE+' target, physical-share execution'),node)
            if type(node.value) is int and node.value==179:
                self.counts['event_count']+=1;return ast.copy_location(ast.Constant(event_count),node)
            return node
    adapt=Adapt();module=adapt.visit(ast.Module(body=nodes,type_ignores=[]));ast.fix_missing_locations(module)
    need(adapt.counts=={'policy':2,'event_count':2},'only two policy labels and two source event-count constants adapted')
    ns={'sha':sha,'read':read};exec(compile(module,str(helper),'exec'),ns)
    return ns,adapt.counts


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','run-dir','plan','expected-plan-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base,repo,run,plan,out=map(Path,(a.source_root,a.repo_root,a.run_dir,a.plan,a.output))
    need(not out.exists() and sha(plan)==a.expected_plan_sha256,'fresh audit/frozen raw plan')
    req=read(plan);summary=read(run/'summary.json');before=inventory(run)
    need(summary['plan_sha256']==a.expected_plan_sha256 and not summary['changed_original_inputs'],'complete immutable actual physical run')
    bound={plan:a.expected_plan_sha256,repo/req['protocol_file']:req['protocol_sha256'],
        repo/'experiments/qlib/audit_sources/2026-10-22-asset-expansion-primary-audit.py':req['primary_audit_code_sha256']}
    for field,parent in (('method_code_sha256',repo),('public_inputs_sha256',repo),('source_inputs_sha256',base)):
        for name,h in req[field].items():bound[parent/name]=h
    for f,h in bound.items():need(sha(f)==h,'original input before '+str(f))
    raw=base/RAW;m=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions'];packets={};bars={}
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31','exact pre2026 calendar')
    for code,h in m['per_code_sha256'].items():
        f=raw/'codes'/(code+'.json');need(sha(f)==h,'original raw packet');v=read(f)
        need(v['instrument']==code and [r['date'] for r in v['bars']]==sessions,'all issuer source sessions')
        packets[code]=v;bars[code]={r['date']:r for r in v['bars']}
    targets_path=base/'asset-expansion-conditional-development-v1-20261022/targets.json'
    need(sha(targets_path)==m['target_sha256'],'fixed original target bytes');targets=read(targets_path)[CANDIDATE]
    projection=read(run/'source_projection.json');events={};receipts=[]
    for code,packet in sorted(packets.items()):
        for row in packet['distributions']:
            stock=row['dividStocksPs'];capital=row['dividReserveToStockPs'];cash=row['dividCashPsBeforeTax']
            need(cash and stock,'known distribution components')
            if not capital:
                need(float(cash)>0 and float(stock)==0 and row['dividCashStock'].startswith('10派')
                    and '转' not in row['dividCashStock'] and '送' not in row['dividCashStock']
                    and not row['dividStockMarketDate'],'explicit cash-only blank capital')
                capital='0'
            identity={'instrument':code,'source_kind':'VENDOR_DISTRIBUTION','source_distribution':row,
                'primary_source_sha256':[],'effective_stock_taxable_income_per_original_share':'0',
                'capital_tax_exempt_verified':False,'stock_tax_basis_verified':False}
            eid=digest(identity);need(eid not in events,'unique original source event')
            events[eid]={'event_id':eid,'instrument':code,'announced':row['dividPlanDate'],'recorded':row['dividRegistDate'],
                'ex_date':row['dividOperateDate'],'pay_date':row['dividPayDate'] or None,'listed':row['dividStockMarketDate'] or None,
                'cash_per_share':cash,'capital_per_share':capital,'capital_tax_exempt_verified':False,
                'stock_per_share':stock,'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False}
            receipts.append({'event_id':eid,'instrument':code,'ex_date':row['dividOperateDate'],'source_kind':'VENDOR_DISTRIBUTION',
                'source_row_sha256':digest(row),'primary_source_sha256':[],
                'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),
                'requires_zero_record_ownership_if_tax_unverified':float(capital)>0 or float(stock)>0})
    need(len(events)==79 and list(events.values())==projection['events'] and receipts==projection['event_receipts'],'independently reconstructed original79 event economics and receipts')
    restorations=[]
    for code,packet in packets.items():
        ex={r['dividOperateDate'] for r in packet['distributions']};adjustments={r['dividOperateDate']:r for r in packet['adjustments']}
        for at,current in adjustments.items():
            if at in ex:continue
            i=sessions.index(at);need(i>0 and sessions[i-1] in ex,'restoration directly follows original distribution')
            previous=adjustments[sessions[i-1]]
            need(Decimal(previous['adjustFactor'])==1
                and all(Decimal(previous[f])==Decimal(current[f]) for f in ('foreAdjustFactor','backAdjustFactor'))
                and Decimal(current['adjustFactor'])==Decimal(current['backAdjustFactor'])
                and Decimal(bars[code][at]['preclose'])==Decimal(bars[code][sessions[i-1]]['close']),
                'exact original cumulative restoration/no additional raw-reference cash gap')
            restorations.append({'instrument':code,'distribution_day':sessions[i-1],'restoration_day':at,
                'previous_adjustment_sha256':digest(previous),'restoration_adjustment_sha256':digest(current),
                'new_cash_or_shares_inferred':False,'source_rows_modified':False})
    need(restorations==projection['restoration_receipts'] and len(restorations)==2,'both exact restoration receipts independently reproduced')
    ns,adaptations=ledger_namespace(len(events));ns.update(sessions=sessions,bars=bars,targets=targets,events=events)
    results={};cases={}
    for extra in ('20','40'):
        stated=summary['results_by_extra_bps'][extra];case=ns['load_case'](run/extra,stated);cases[extra]=case
        results[extra]=ns['audit'](case,int(extra),stated)
        e=next(e for e in events.values() if e['instrument']=='SH603688' and float(e['capital_per_share'])>0)
        need(case['ownership'][e['recorded']].get(e['instrument'],0)==0,'actual unverified noncash registration inventory zero')
        need(stated['unverified_noncash_zero_ownership_verified'] is True,'correct zero-ownership status')
    negatives={}
    for name in ('erased_fee','false_daily_equity','false_record_quantity','wrong_target_quantity','unfilled_order_forged_as_filled','false_noncash_registration'):
        v=copy.deepcopy(cases['40'])
        if name=='erased_fee':v['fills'][0]['cost']='0'
        elif name=='false_daily_equity':v['rows'][-1]['equity']=str(ns['D'](v['rows'][-1]['equity'])+1)
        elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
        elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
        elif name=='unfilled_order_forged_as_filled':next(o for o in v['orders'] if o['status'].startswith('UNFILLED'))['status']='FILLED'
        else:next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP' and x['instrument']=='SH603688')['quantity']=100
        try:ns['audit'](v,40,summary['results_by_extra_bps']['40'])
        except (AssertionError,KeyError):negatives[name]=True
        else:raise ValueError('arithmetic negative accepted: '+name)
    ref=results['40'];passes=min(ref['2024_return_pct'],ref['2025_return_pct'])>0 and ref['average_exposure_pct']>=90
    need(passes==summary['raw_daily_proxy_development_gate_passes'],'fixed40bp physical development gate')
    for f,h in bound.items():need(sha(f)==h,'original input after '+str(f))
    need(inventory(run)==before,'all physical output bytes unchanged through QA')
    result={'status':'SEPARATE_ASSET_EXPANSION_TWO_PHYSICAL_DAILY_ACCOUNT_AUDIT_PASSED',
        'audit_code_sha256':sha(Path(__file__)),'plan_sha256':sha(plan),'summary_sha256':sha(run/'summary.json'),
        'shared_prior_separate_ledger_sha256':HELPER_SHA,'only_helper_AST_adaptations':adaptations,
        'results_by_extra_bps':results,'arithmetic_negative_controls_rejected':negatives,
        'negative_controls_use_artifact_hash_gate':False,'all_output_sha256':before,
        'all_original_inputs_unchanged':True,'source_events_independently_reconstructed':79,'restoration_relationships_independently_checked':2,
        'no_production_imports':True,'same_researcher_after_outcomes_QA':True,
        'raw_daily_proxy_development_gate_passes_independently':passes,
        'minute_execution_admitted':False,'historical_arrival_verified':False,'investment_factor_admitted':False,
        '2026_return_computed':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],'six arithmetic negatives rejected')

if __name__=='__main__':main()
