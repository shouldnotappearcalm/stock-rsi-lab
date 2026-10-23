"""Freeze unchanged full-horizon targets; no portfolio/account return scorer."""
import argparse,ast,json,sys
from collections import defaultdict
from pathlib import Path

from scripts import build_asset_availability_2026 as availability
from scripts.immutable_http_capture import need,write_once
from stock_rsi import asset_expansion_horizon as signal
from stock_rsi.qlib_snapshot import QlibSnapshot

read,sha,inventory=availability.read,availability.sha,availability.inventory
OUTPUT='asset-expansion-targets-through2026-v1-20261023'
VIEWS=availability.OUTPUT
PROVIDER='qlib-enhanced-dev'
OLD_PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
OLD_RUN='asset-expansion-conditional-development-v1-20261022'
OLD_TARGETS=OLD_RUN+'/targets.json'
OLD_RECEIPTS=OLD_RUN+'/formation_receipts.json'
AVAIL_REQUEST='experiments/qlib/asset-expansion-2026-availability-request.json'
AVAIL_AUDIT='experiments/qlib/asset-expansion-2026-availability-source-audit.json'
OLD_AUDIT='experiments/qlib/asset-expansion-pre2026-audit.json'
RAW_RESULT='experiments/qlib/asset-expansion-raw-development-results.json'
RAW_AUDIT='experiments/qlib/asset-expansion-raw-account-audit.json'
PROTOCOL='docs/research/asset-expansion-2026-targets-plan-2026-10-23.md'
STATUS='FROZEN_UNCHANGED_ASSET_EXPANSION_TARGETS_THROUGH2026'
PUBLIC=(AVAIL_REQUEST,AVAIL_AUDIT,OLD_AUDIT,RAW_RESULT,RAW_AUDIT,PROTOCOL)
METHODS=('scripts/run_asset_expansion_targets_2026.py','src/stock_rsi/asset_expansion_horizon.py',
    'src/stock_rsi/asset_expansion_monthly.py','src/stock_rsi/gross_profitability_monthly.py',
    'src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
    'scripts/build_asset_availability_2026.py','tests/test_asset_expansion_horizon.py','tests/test_asset_expansion_horizon_runner.py')


def canonical(obj):return json.loads(json.dumps(obj,allow_nan=False))


def assert_same_policy_ast(old_text,new_text):
    old,new=ast.parse(old_text),ast.parse(new_text)
    for tree in (old,new):
        need(isinstance(tree.body[0],ast.Expr) and isinstance(tree.body[0].value,ast.Constant)
            and type(tree.body[0].value.value) is str,'source policy module docstring')
        tree.body[0].value.value='module description only'
    def window(tree):
        nodes=[n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Tuple)
            and [getattr(v,'id',None) for v in n.targets[0].elts]==['START','END']]
        need(len(nodes)==1,'one explicit policy window');return nodes[0].value
    a,b=window(old),window(new)
    need([v.value for v in a.elts]==['2024-01-02','2025-12-31']
        and [v.value for v in b.elts]==['2024-01-02','2026-10-21'],'only the declared bounded horizon changes')
    b.elts[1].value=a.elts[1].value
    def guard(tree):
        f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_targets')
        n=f.body[0];need(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and len(n.value.args)==2
            and isinstance(n.value.args[1],ast.Constant) and type(n.value.args[1].value) is str,'one explicit first window guard')
        return n.value.args[1]
    guard(new).value=guard(old).value
    need(ast.dump(old)==ast.dump(new),'unchanged policy AST: only docstring,END and guard diagnostic may differ')


def dependency_contract(base,repo,membership):
    expected,paths=availability.dependency_contract(base,repo,membership)
    def bind(key,path,h=None):
        value=sha(path) if h is None else h
        need(key not in expected or expected[key]==value,'consistent repeated input binding')
        expected[key]=value;paths[key]=path
    for name in (*PUBLIC,*METHODS):bind('repo/'+name,repo/name)
    qa=read(repo/AVAIL_AUDIT)
    need(inventory(base/VIEWS)==qa['all_output_sha256'],'all72 source views remain unchanged')
    for n,h in qa['all_output_sha256'].items():bind('source/'+VIEWS+'/'+n,base/VIEWS/n,h)
    oldqa=read(repo/OLD_AUDIT)
    for n in ('targets.json','formation_receipts.json'):
        bind('source/'+OLD_RUN+'/'+n,base/OLD_RUN/n,oldqa['all_output_sha256'][n])
    seed=read(repo/availability.SEED_REQUEST)
    for relative in ('calendars/day.txt','instruments/all.txt','instruments/csi500.txt'):
        bind('source/'+PROVIDER+'/'+relative,base/PROVIDER/relative)
    relative='calendars/day.txt';key='source/'+OLD_PROVIDER+'/'+relative
    bind(key,base/OLD_PROVIDER/relative,seed['input_sha256'][key])
    for code in seed['cohort']:
        for field in ('close','volume','factor'):
            relative='features/'+code.lower()+'/'+field+'.day.bin'
            bind('source/'+PROVIDER+'/'+relative,base/PROVIDER/relative)
            key='source/'+OLD_PROVIDER+'/'+relative;bind(key,base/OLD_PROVIDER/relative,seed['input_sha256'][key])
    return expected,paths


def verify(base,repo,membership,request,expected_sha):
    need(sha(request)==expected_sha,'frozen horizon target request');req=read(request)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['provider_relative']==PROVIDER
        and req['candidate']==signal.PRIMARY and req['controls']==['eligible_equal_weight',signal.HIGH_CONTROL]
        and req['candidate_budget']==1 and req['new_alpha_candidates']==0 and req['investment_rule_changed'] is False
        and req['ranking_permitted'] is True and req['portfolio_returns_permitted'] is False and req['network_permitted'] is False
        and req['target_exposure']==.95 and req['minimum_eligible']==100 and req['ranking_fraction']=='1/10'
        and req['freshness_rule']=='YEAR_MINUS2_THROUGH_JUNE_YEAR_MINUS1_FROM_JULY'
        and req['runtime_python']==sys.version.split()[0] and set(req['method_sha256'])==set(METHODS),
        'same single frozen policy and no account scorer')
    expected,paths=dependency_contract(base,repo,membership)
    need(req['input_sha256']==expected and req['method_sha256']=={n:expected['repo/'+n] for n in METHODS},
        'exact consumed-source,quote and method closure')
    parent,qa,oldqa=(read(repo/n) for n in (AVAIL_REQUEST,AVAIL_AUDIT,OLD_AUDIT))
    need(req['cohort']==parent['cohort'] and len(req['cohort'])==394 and req['formations']==parent['formations']
        and len(req['formations'])==34 and qa['request_sha256']==sha(repo/AVAIL_REQUEST)
        and qa['queries_checked']==68 and qa['pre2026_selection_parity_queries']==48
        and qa['all_consumed_inputs_and_outputs_unchanged'] is True
        and oldqa['request_sha256']==sha(repo/availability.SEED_REQUEST)
        and oldqa['all_inputs_and_outputs_unchanged'] is True and oldqa['selected_development_lead']==signal.PRIMARY
        and read(repo/RAW_RESULT)['raw_daily_proxy_development_gate_passes'] is True,'same audited source cohort and pre2026 lead')
    oldfile=repo/'src/stock_rsi/asset_expansion_monthly.py';seed=read(repo/availability.SEED_REQUEST)
    need(sha(oldfile)==seed['input_sha256']['repo/src/stock_rsi/asset_expansion_monthly.py'],'unchanged original frozen selector')
    assert_same_policy_ast(oldfile.read_text(),(repo/'src/stock_rsi/asset_expansion_horizon.py').read_text())
    need(req['provider_calendar_last_session']==(base/PROVIDER/'calendars/day.txt').read_text().splitlines()[-1]=='2026-10-13',
        'only stored actual formation calendar coverage')
    need(sha(base/PROVIDER/'instruments/csi500.txt')==sha(membership),'same complete dated membership file')
    for key,path in paths.items():need(sha(path)==expected[key],'bound horizon input '+key)
    return req,paths


def prefix_evidence(base,req):
    a=(base/OLD_PROVIDER/'calendars/day.txt').read_text().splitlines();b=(base/PROVIDER/'calendars/day.txt').read_text().splitlines()
    need(a==b[:len(a)] and a[-1]=='2025-12-31','unchanged original calendar prefix')
    evidence={}
    for code in req['cohort']:
        for field in ('close','volume','factor'):
            relative='features/'+code.lower()+'/'+field+'.day.bin';old=base/OLD_PROVIDER/relative;new=base/PROVIDER/relative
            h=sha(old);need(h==req['input_sha256']['source/'+OLD_PROVIDER+'/'+relative],'original frozen feature hash')
            original=old.read_bytes()
            with new.open('rb') as f:prefix=f.read(len(original))
            need(original==prefix,'unchanged pre2026 opaque feature prefix '+code+'/'+field)
            evidence[code+'/'+field]=h
    return {'old_calendar_end':a[-1],'new_calendar_last_session':b[-1],'old_calendar_sessions':len(a),
        'feature_prefix_count':len(evidence),'all_pre2026_byte_prefixes_equal':True,
        'no2026_float_values_decoded_in_prefix_check':True,'feature_prefix_sha256':evidence}


def form_targets(base,req,on_formation):
    snapshot=QlibSnapshot(base/PROVIDER);memberships=defaultdict(list)
    for line in (base/PROVIDER/'instruments/csi500.txt').read_text().splitlines():
        code,first,last=line.split();memberships[code].append((first,last))
    views={q['execution_session']:read(base/VIEWS/(q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json')) for q in req['formations']}
    cases=read(base/availability.OLD_ASSETS/'case_results.json');new=read(base/availability.NEW_ASSETS/'case_results.json')
    need(not set(cases)&set(new),'all source cases have disjoint original keys');cases.update(new)
    return signal.build_targets(snapshot,memberships,req['cohort'],views,cases.__getitem__,on_formation=on_formation)


def run(base,repo,membership,request,expected_sha,*,former=None):
    out=base/OUTPUT;need(not out.exists(),'fresh horizon targets; no resume or overwrite')
    req,paths=verify(base,repo,membership,request,expected_sha)
    paths={**paths,'frozen_request':request};expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'horizon input before '+key)
    out.mkdir(parents=True);(out/'formations').mkdir();saved=[];original=None;changed=[];persistence=[];parity=0
    try:
        write_once(out/'input-before.json',expected);write_once(out/'pre2026-prefix-evidence.json',prefix_evidence(base,req))
        oldtargets,oldreceipts=read(base/OLD_TARGETS),read(base/OLD_RECEIPTS)
        oldreceipts={r['execution_session']:r for r in oldreceipts}
        def save(day,targets,receipt):
            nonlocal parity
            i=len(saved);need(i<len(req['formations']) and day==req['formations'][i]['execution_session'],'exact ordered formation identity')
            q=req['formations'][i];prior=q['as_of'][:10]
            need(set(targets)==set(signal.NAMES) and all(t['as_of']==prior for t in targets.values())
                and receipt['execution_session']==day and receipt['formation_asof']==receipt['latest_factor_price_read']==prior
                and signal.aware(receipt['source_as_of'])==signal.aware(q['as_of']),'exact prior-close formation clock')
            row=canonical({'targets':targets,'receipt':receipt})
            if day<'2026-01-01':
                need(row['targets']=={n:oldtargets[n][day] for n in signal.NAMES}
                    and row['receipt']==oldreceipts[day],'legacy target and complete receipt parity before2026')
            write_once(out/'formations'/(day+'.json'),row);saved.append((day,row));parity+=int(day<'2026-01-01')
            print('asset horizon formation',len(saved),'/',len(req['formations']),day,'eligible',receipt['eligible'],flush=True)
        targets,receipts=(former or form_targets)(base,req,save)
        need(len(saved)==len(req['formations']) and canonical(targets)=={n:{d:r['targets'][n] for d,r in saved} for n in signal.NAMES}
            and canonical(receipts)==[r['receipt'] for _,r in saved],'complete unchanged persisted formation aggregates')
        write_once(out/'targets.json',targets);write_once(out/'formation_receipts.json',receipts)
    except BaseException as exc:original=exc
    finally:
        for key,path in paths.items():
            try:
                if sha(path)!=expected[key]:changed.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:changed.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not changed,'count':len(paths),'mismatches':changed}
        terminal={'completed_formations':[d for d,_ in saved],
            'pending_formations':[q['execution_session'] for q in req['formations'] if q['execution_session'] not in {d for d,_ in saved}],
            'pre2026_target_parity_formations':parity,'original_error':None if original is None else {'type':type(original).__name__,'message':str(original)},
            'postcheck':post,'persistence_errors':persistence}
        for name,value in (('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if original is not None:raise original
    need(not changed and not persistence,'unchanged horizon inputs and complete persistence')
    primary={d:r['targets'][signal.PRIMARY] for d,r in saved}
    summary={'status':'UNCHANGED_FULL_HORIZON_TARGETS_COMPLETE_PENDING_SEPARATE_QA','request_sha256':expected_sha,
        'candidate':signal.PRIMARY,'completed_formations':len(saved),'pre2026_target_parity_formations':parity,
        'primary_target_union':sorted({c for t in primary.values() for c in t['weights']}),
        'primary_2026_target_union':sorted({c for d,t in primary.items() if d>='2026-01-01' for c in t['weights']}),
        '2026_formation_counts':[{'execution_session':d,'eligible':r['receipt']['eligible'],
            'primary_names':len(r['targets'][signal.PRIMARY]['weights'])} for d,r in saved if d>='2026-01-01'],
        'targets_sha256':sha(out/'targets.json'),'formation_receipts_sha256':sha(out/'formation_receipts.json'),
        'all_inputs_unchanged':True,'investment_rule_changed':False,'portfolio_returns_computed':False,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'sealed_2026_evidence':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();run(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),
        Path(a.request).resolve(),a.expected_request_sha256)


if __name__=='__main__':main()
