"""Unchanged policy AST and exact old24target parity before any2026account ROI."""
import argparse,ast
from pathlib import Path
from scripts import inspect_cash_accrual_2026_sources as source
from scripts.run_qlib_low_risk_pre2026 import parse_memberships
from stock_rsi import cash_accrual_horizon as signal
from stock_rsi.qlib_snapshot import QlibSnapshot

OUTPUT='cash-accrual-targets-through2026-v1-20261028';PROVIDER='qlib-enhanced-dev'
OLD_REQUEST='experiments/qlib/cash-accrual-cfo-request.json';OLD_PROOF='experiments/qlib/cash-accrual-cfo-root-check.json'
NEW_REQUEST='experiments/qlib/cash-accrual-2026-source-request.json';NEW_PROOF='experiments/qlib/cash-accrual-2026-source-root-check.json'
OLD_SOURCE='cash-accrual-cfo-corpus-v3-20261027';NEW_SOURCE=source.OUTPUT
INDUSTRY='gross-profitability-2021Q3-industry-catalog-v1-20261022/catalog.json'
OLD_TARGET='experiments/qlib/cash-accrual-pre2026-targets.json';AMENDMENTS='experiments/qlib/low-operating-known-amendment-metadata.json'
DESIGN='docs/research/cash-accrual-horizon-target-design-2026-10-28.md'
METHODS=('src/stock_rsi/cash_accrual_monthly.py','src/stock_rsi/cash_accrual_horizon.py','scripts/run_cash_accrual_horizon_targets.py',
 'src/stock_rsi/industry_catalog.py','src/stock_rsi/gross_profitability_monthly.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
 'src/stock_rsi/annual_cash_accruals.py','src/stock_rsi/annual_cash_accruals_v2.py','src/stock_rsi/annual_cash_accruals_v3.py','tests/test_cash_accrual_horizon.py','tests/test_cash_accrual_2026_real_witnesses.py',
 'tests/fixtures/cash-accrual2026-real-cells.json','experiments/qlib/cash-accrual-2026-visual-review.json')
PROFILE={'status':'FROZEN_UNCHANGED_CASH_ACCRUAL_HORIZON_TARGETS_NO_ROI','output_subdir':OUTPUT,'candidate':signal.PRIMARY,
 'window':['2024-01-02','2026-10-21'],'cohort_count':394,'document_count':1636,'formations':34,'new_alpha_candidates':0,
 'investment_rule_changed':False,'target_exposure':.95,'minimum_eligible':100,'network_or_portfolio_returns_permitted':False,'sealed_evidence':False}

def same_policy(old,new):
    a,b=ast.parse(old),ast.parse(new);a.body[0].value.value=b.body[0].value.value='module description'
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self,n):
            replacements={'2026-10-21':'2025-12-31','development ends in2026':'development ends in2025','development window ends in2026':'development window ends in2025'}
            if type(n.value) is str and n.value in replacements:return ast.copy_location(ast.Constant(replacements[n.value]),n)
            if type(n.value) is int and n.value==2026:return ast.copy_location(ast.Constant(2025),n)
            return n
    b=Normalize().visit(b);source.need(ast.dump(a)==ast.dump(b),'only horizon/end-year guard/diagnostics may change in policy AST')

def bindings(base,root):
    old=source.read(root/OLD_PROOF);new=source.read(root/NEW_PROOF);gate=source.read(root/source.LEDGER_QA)
    source.need(new['status']=='PASS400_UNCHANGED_V3_EXPOSED2026_CASH_SOURCE_NO_RANKING_OR_RETURN' and new['all_inputs_outputs_unchanged']
        and old['all_inputs_outputs_unchanged'] and gate['all_inputs_outputs_unchanged'],'all source/physical development audits required')
    known={}
    def bind(p,h=None):
        p=Path(p);h=h or source.sha(p);key=str(p.resolve());source.need(not p.is_symlink() and (key not in known or known[key]==h) and source.sha(p)==h,'unchanged target dependency '+str(p));known[key]=h
    for folder,proof in ((OLD_SOURCE,old),(NEW_SOURCE,new)):
        source.need(source.tree(base/folder)==proof['all_output_sha256'],'whole case output tree')
        for n,h in proof['all_output_sha256'].items():bind(base/folder/n,h)
    for n in (*METHODS,OLD_REQUEST,OLD_PROOF,NEW_REQUEST,NEW_PROOF,source.LEDGER_QA,OLD_TARGET,AMENDMENTS,DESIGN):bind(root/n)
    bind(base/INDUSTRY)
    for n in ('calendars/day.txt','instruments/csi500.txt'):bind(base/PROVIDER/n)
    cohort=source.read(root/OLD_REQUEST)['cohort'];old_provider=base/'qlib-price-delay-pre2026-clock-v2-20261021'
    for c in cohort:
        for field in ('close','volume','factor'):
            n='features/'+c.lower()+'/'+field+'.day.bin';full=base/PROVIDER/n;past=old_provider/n;bind(full);bind(past)
            prefix=past.read_bytes();source.need(full.read_bytes()[:len(prefix)]==prefix,'all old quote bytes preserved exactly')
    same_policy((root/METHODS[0]).read_text(),(root/METHODS[1]).read_text())
    return known

def verify(base,root,request,expected):
    req=source.read_bound(request,expected);source.need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed unchanged horizon request')
    known=bindings(base,root);source.need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS)
        and all(source.sha(root/n)==h for n,h in req['method_sha256'].items()),'complete frozen target closure')
    old=source.read(root/OLD_REQUEST);new=source.read(root/NEW_REQUEST);ids={**source.read(root/OLD_PROOF)['approved_record_ids'],**source.read(root/NEW_PROOF)['approved_record_ids']}
    source.need(req['documents']==old['documents']+new['documents'] and req['cohort']==old['cohort']==new['cohort']
        and req['approved_record_ids']==ids and len(ids)==1636,'all original1636editions and source IDs')
    known[str(request.resolve())]=expected;return req,known

def execute(req,known,base,root):
    out=base/OUTPUT;source.need(not out.exists() and not source.changed(known),'fresh unchanged horizon targets');out.mkdir();outputs={};error=None
    state={'status':'CASH_HORIZON_TARGETS_INCOMPLETE','complete':False,'request_sha256':req['request_sha256'],
           '2026_portfolio_returns_computed':False,'investment_rule_changed':False,'objective_achieved':False,'sealed_evidence':False}
    def save(n,v):source.persist(out,n,v,outputs)
    def bound(p):return source.read_bound(p,known[str(p.resolve())])
    try:
        snapshot=QlibSnapshot(base/PROVIDER);members=parse_memberships((base/PROVIDER/'instruments/csi500.txt').read_text());docs={d['capture_key']:d for d in req['documents']};old_keys={d['capture_key'] for d in source.read(root/OLD_REQUEST)['documents']}
        def reader(k):return bound(base/(OLD_SOURCE if k in old_keys else NEW_SOURCE)/'cases'/(k+'.json'))
        def callback(day,targets,receipt):save('formations/'+day+'.json',{'targets':targets,'receipt':receipt})
        targets,receipts=signal.build_targets(snapshot,members,req['cohort'],req['documents'],reader,req['approved_record_ids'],bound(base/INDUSTRY),bound(root/AMENDMENTS),on_formation=callback)
        source.need(len(receipts)==34,'all34formations required')
        previous=bound(root/OLD_TARGET)
        for name in signal.NAMES:source.need({d:v for d,v in targets[name].items() if d<='2025-12-31'}==previous[name],'exact old24targets preserved')
        save('targets.json',targets);save('formation_receipts.json',receipts)
        state.update(status='CASH_HORIZON34TARGETS_COMPLETE_NO_PORTFOLIO_RETURN',complete=True,old24targets_preserved_identically=True,
                     eligibility_by_month={r['execution_session']:r['eligible'] for r in receipts},primary_target_union=sorted({c for t in targets[signal.PRIMARY].values() for c in t['weights']}))
    except BaseException as exc:error=exc;state.update(complete=False,error_type=type(exc).__name__,error=str(exc),failed_stage='TARGET_FORMATION')
    try:value=source.legacy.finish_source(out,state,known,outputs)
    except BaseException as exc:
        if error is None:error=exc
        else:error.add_note('publication:'+type(exc).__name__)
    if error is not None:raise error
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];request=Path(a.request).resolve()
    req,known=verify(base,root,request,a.expected_request_sha256);req['request_sha256']=a.expected_request_sha256;print(execute(req,known,base,root)['status'])
if __name__=='__main__':main()
