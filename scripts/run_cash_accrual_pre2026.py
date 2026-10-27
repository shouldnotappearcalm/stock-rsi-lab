"""Frozen single-candidate pre2026 research screen; no future-year execution path."""
import argparse
from importlib import metadata
import math
from pathlib import Path
import sys
from scripts import inspect_cash_accrual_cfo_corpus as source
from scripts import run_qlib_profitability_pre2026 as engine
from scripts.run_low_operating_proxy_pre2026 import finish_account
from stock_rsi import cash_accrual_monthly as signal
from stock_rsi.qlib_snapshot import QlibSnapshot

PROOF='experiments/qlib/cash-accrual-cfo-root-check.json'
REQUEST='experiments/qlib/cash-accrual-cfo-request.json'
REQUEST_SHA='690524629d6382b78dc8dd7c75a14df603572803459be27725452527e2a465a1'
ENGINE_REQUEST='experiments/qlib/gross-profitability-pre2026-request.json'
ENGINE_SHA='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5'
INDUSTRY='gross-profitability-2021Q3-industry-catalog-v1-20261022/catalog.json'
AMENDMENTS='experiments/qlib/low-operating-known-amendment-metadata.json'
DESIGN='docs/research/cash-accrual-development-design-2026-10-27.md'
OUTPUT='cash-accrual-development-pre2026-v1-20261027'
METHODS=tuple(dict.fromkeys((*engine.METHODS,*source.METHODS,'src/stock_rsi/cash_accrual_monthly.py',
    'scripts/audit_cash_accrual_wrapped_corpus.py','scripts/run_cash_accrual_pre2026.py',
    'scripts/run_low_operating_proxy_pre2026.py','tests/test_cash_accrual_monthly.py','tests/test_cash_accrual_development.py')))
PROFILE={'status':'FROZEN_ONE_CN_TOTAL_NI_CFO_ACCRUAL_DEVELOPMENT_SCREEN', 'output_subdir':OUTPUT,
         'candidate':signal.PRIMARY,'controls':['eligible_equal_weight',signal.HIGH_CONTROL],
         'candidate_budget':1,'account_window':[signal.START,signal.END],'capital_CNY':1000000,
         'extra_bps':[20,40],'target_exposure':.95,'ranking_fraction':'1/10','minimum_eligible':100,
         'source_mode':signal.cash.RECONSTRUCTED,'known_amendment_policy':'BLOCK_AFFECTED_EDITION_AFTER_PUBLICATION',
         'network_permitted':False,'2026_financial_or_market_values_permitted':False,
         'selection_rule':'PRIMARY_ONLY_40BPS_EACH_YEAR_POSITIVE_EXPOSURE_GE90_ZERO_UNVERIFIED_MARKS',
         'screen_is_raw_share_or_investment_qualification':False}


def validate_profile(req):
    source.need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'one frozen cash-accrual development profile; no2026 or control promotion')


def bindings(base,root):
    proof=source.read(root/PROOF)
    source.need(proof['status']=='PASS_ALL_CFO_SOURCE_CASE_REPLAY_AND_SEPARATE_LITERAL_CHECKS_NOT_FACTOR_ADMISSION'
                and proof['request_sha256']==REQUEST_SHA and proof['all_inputs_outputs_unchanged'] is True
                and proof['all_original_257_reports_preserved_identically'] is True,'whole source reconciliation required')
    known={}
    def bind(path,h):
        path=Path(path);key=str(path.resolve())
        source.need(not path.is_symlink() and (key not in known or known[key]==h),'one source identity')
        if key not in known:source.need(source.sha(path)==h,'authenticated input '+str(path));known[key]=h
    for p,h in proof['all_input_sha256'].items():bind(p,h)
    source.need(source.tree(base/source.OUTPUT)==proof['all_output_sha256'],'entire audited source tree')
    for n,h in proof['all_output_sha256'].items():bind(base/source.OUTPUT/n,h)
    bind(root/REQUEST,REQUEST_SHA);bind(root/PROOF,source.sha(root/PROOF));bind(root/ENGINE_REQUEST,ENGINE_SHA)
    previous=source.read_bound(root/ENGINE_REQUEST,ENGINE_SHA)
    membership=base/'qlib-enhanced-dev/instruments/csi500.txt'
    for k,h in previous['input_sha256'].items():bind(engine.resolve(k,root,base,membership),h)
    source.need(engine.inventory(base/engine.PROVIDER)==previous['provider_inventory_sha256'],'entire physically pre2026 provider unchanged')
    for n in (*METHODS,DESIGN,AMENDMENTS):bind(root/n,source.sha(root/n))
    source.need(str((base/INDUSTRY).resolve()) in known,'source vintage industry bound')
    return known,proof,previous


def verify(base,root,request,expected):
    req=source.read_bound(request,expected);validate_profile(req);known,proof,previous=bindings(base,root)
    source.need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS)
                and all(source.sha(root/n)==h for n,h in req['method_sha256'].items()),'exact source/engine/method closure')
    original=source.read_bound(root/REQUEST,REQUEST_SHA)
    source.need(req['documents']==original['documents'] and req['cohort']==original['cohort']==previous['cohort']
                and req['formations']==previous['formations'] and req['approved_record_ids']==proof['approved_record_ids']
                and req['gap_state_manifest_sha256']==previous['gap_state_manifest_sha256'],'whole source cohort,actual sessions and approved records')
    actual={'python':sys.version.split()[0],**{n:metadata.version(n) for n in ('pyqlib','numpy','pandas')}}
    source.need(req['runtime']==previous['runtime']==actual,'frozen installed research runtime')
    snapshot=QlibSnapshot(base/engine.PROVIDER)
    source.need(snapshot.calendar[-1].isoformat()==signal.END and all(d['day']<='2025-12-31' for d in req['documents']),'physically capped quote calendar and financial publications')
    known[str(request.resolve())]=expected
    return req,known


def form_targets(base,root,req,known,out,save):
    def bound(p):return source.read_bound(p,known[str(p.resolve())])
    snapshot=QlibSnapshot(base/engine.PROVIDER)
    members=engine.parse_memberships((base/engine.PROVIDER/'instruments/csi500.txt').read_text())
    def case_reader(k):return bound(base/source.OUTPUT/'cases'/(k+'.json'))
    def callback(day,targets,receipt):save('formations/'+day+'.json',{'targets':targets,'receipt':receipt})
    return signal.build_targets(snapshot,members,req['cohort'],req['documents'],case_reader,req['approved_record_ids'],
        bound(base/INDUSTRY),bound(root/AMENDMENTS),on_formation=callback)


def eligible_lead(results):
    p=results['40/'+signal.PRIMARY]
    return signal.PRIMARY if min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90 and p['unverified_held_marks']==0 else None


def execute(base,root,req,known,expected,*,builder=form_targets,simulation=engine.simulate):
    validate_profile(req);out=base/OUTPUT
    source.need(not out.exists() and not source.changed(known),'fresh development output and unchanged inputs');out.mkdir()
    outputs={};results={};primary=None;stage='FORMATIONS'
    terminal={'status':'CASH_ACCRUAL_DEVELOPMENT_INCOMPLETE','complete':False,'request_sha256':expected,
              'portfolio_return_computed':False,'physical_investment_admitted':False,'2026_values_used_for_selection':False,
              'objective_achieved':False}
    def save(n,value):source.persist(out,n,value,outputs)
    try:
        targets,receipts=builder(base,root,req,known,out,save)
        source.need(len(receipts)==len(req['formations']) and all(r['coverage_pass'] for r in receipts),'all frozen monthly formations required')
        save('targets.json',targets);save('formation_receipts.json',receipts)
        for extra in req['extra_bps']:
            for name in signal.NAMES:
                stage=str(extra)+'/'+name;folder=out/stage;folder.mkdir(parents=True)
                print('cash-accrual development',stage,flush=True)
                result=simulation(base/engine.PROVIDER,targets[name],name=name,extra_bps=extra,out=folder,base=base,req=req)
                source.need(result['status']=='DAILY_PROXY_DEVELOPMENT_RECONCILED','same reconciled account engine')
                for key in ('2024_return_pct','2025_return_pct','average_exposure_pct'):
                    source.need(type(result.get(key)) in (int,float) and math.isfinite(result[key]),'finite complete annual metrics')
                source.need(type(result['unverified_held_marks']) is int and result['unverified_held_marks']>=0,'explicit unresolved held-mark count')
                outputs.update({stage+'/'+n:h for n,h in source.tree(folder).items()})
                save(stage+'/metrics.json',result);results[stage]=result
        stage='SUMMARY';lead=eligible_lead(results)
        save('results.json',results)
        terminal.update(status='CASH_ACCRUAL_PRE2026_DAILY_SCREEN_COMPLETE',complete=True,portfolio_return_computed=True,
                        results_by_extra_bps=results,selected_development_lead=lead,
                        next_step='RAW_SHARE_SOURCE_AND_ACCOUNT_VALIDATION' if lead else 'REJECT_THIS_FROZEN_CANDIDATE_NO2026_RUN',
                        historical_arrival_verified=False,financial_version_history_complete=False,
                        raw_share_execution_verified=False,screen_is_investment_qualification=False)
    except BaseException as exc:
        primary=exc;terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage=stage,failed_row_index=None)
        # Even failed simulations can leave diagnostic files; authenticate and retain them.
        outputs=source.tree(out)
    try:result=finish_account(out,terminal,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal publication: '+type(exc).__name__)
    if primary is not None:raise primary
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
    base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];req,known=verify(base,root,Path(a.request).resolve(),a.expected_request_sha256)
    if a.preflight_only:print('cash-accrual development preflight PASS');return
    print(execute(base,root,req,known,a.expected_request_sha256)['status'])
if __name__=='__main__':main()
