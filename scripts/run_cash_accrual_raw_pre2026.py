"""Frozen cash-accrual targets in integer shares; strict corporate guards retained."""
import argparse
from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from scripts import capture_cash_accrual_raw_pre2026 as capture
from scripts.run_low_operating_proxy_pre2026 import finish_account
from scripts.replay_low_operating_proxy_targets import simulate_low_operating_proxy
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.stock_distribution_account import StockDistributionAccount
from stock_rsi.execution_cost import ExecutionCostBroker

r=capture.shared
OUTPUT='cash-accrual-integer-pre2026-v1-20261028'
PROFILE={'status':'FROZEN_CASH_ACCRUAL_INTEGER_SHARE_PRE2026','output_subdir':OUTPUT,
 'candidate':'cn_total_ni_minus_cfo_mean_assets_bottom_decile','window':['2023-12-29','2025-12-31'],
 'initial_CNY':'1000000','extra_bps':[20,40],'target_exposure':.95,'monthly_decisions':24,'source_names':31,
 'corporate_events':72,'unverified_noncash_require_actual_zero_ownership':2,'cash_tax_stress_rate':'.2',
 'network_or_2026_computation_permitted':False,'fractional_policy':'STRICT_FAILURE_RETAINED_THEN_ENUMERATE_ALL_LAWFUL_BRANCHES_IF_NEEDED'}
PROOF='experiments/qlib/cash-accrual-raw-source-root-check.json';TARGET='experiments/qlib/cash-accrual-pre2026-targets.json'
METHODS=('scripts/run_cash_accrual_raw_pre2026.py','scripts/replay_low_operating_proxy_targets.py',
 'scripts/run_low_operating_proxy_pre2026.py','scripts/run_low_risk_raw_share_validation.py',
 'src/stock_rsi/mainboard_daily_proxy.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/budgeted_raw_orders.py','src/stock_rsi/distribution_event_compiler.py',
 'src/stock_rsi/execution_cost.py','src/stock_rsi/broker.py','src/stock_rsi/calendar.py','src/stock_rsi/lifecycle_source_rows.py',
 'src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py','tests/test_cash_accrual_raw_account.py')

def validate(req):r.need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed cash-accrual physical account protocol')

def unknown_checks(case,events,receipts):
    r.need(len(events)==len(receipts),'complete event receipt registry')
    out=[]
    for event,receipt in zip(events,receipts):
        r.need(receipt['event_id']==event.event_id,'coherent event receipt identity')
        if not receipt['requires_zero_record_ownership_if_tax_unverified']:continue
        owned=case['ownership'][event.recorded.isoformat()].get(event.instrument,0)
        entries=[v for v in case['corporate_ledger'] if v['kind']=='EX_DATE_ENTITLEMENT' and v['event_id']==event.event_id]
        r.need(owned==0 and len(entries)==1 and entries[0]['registered_quantity']==0,'unverified noncash requires actual zero registered inventory')
        out.append({'event_id':event.event_id,'instrument':event.instrument,'recorded':event.recorded.isoformat(),'actual_owned_shares':0})
    return out

def bindings(base,root):
    p=r.read(root/PROOF);r.need(p['status']=='PASS31_RAW_PACKETS72EVENTS_SOURCE_CHECKS_NOT_ACCOUNT_ADMISSION' and p['all_inputs_outputs_unchanged'],'audited original raw data required')
    known=dict(p['all_input_sha256'])
    def bind(path,h=None):
        path=Path(path);h=h or r.sha(path);key=str(path.resolve());r.need(not path.is_symlink() and (key not in known or known[key]==h) and r.sha(path)==h,'one original input '+str(path));known[key]=h
    r.need(r.tree(base/capture.OUTPUT)==p['all_output_sha256'],'entire original capture tree')
    for n,h in p['all_output_sha256'].items():bind(base/capture.OUTPUT/n,h)
    for n,h in r.tree(base/'cash-accrual-raw-source-audit-v1-20261028').items():bind(base/'cash-accrual-raw-source-audit-v1-20261028'/n,h)
    for n in (*METHODS,PROOF,TARGET,'docs/research/cash-accrual-integer-design-2026-10-28.md'):bind(root/n)
    return known

def verify(base,root,request,expected):
    req=r.read_bound(request,expected);validate(req);known=bindings(base,root)
    r.need(req['input_sha256']==known and set(req['method_sha256'])==set(METHODS) and all(r.sha(root/n)==h for n,h in req['method_sha256'].items()),'entire fixed raw account method/source closure')
    known[str(request.resolve())]=expected;out=base/capture.OUTPUT;m=r.read_bound(out/'manifest.json',known[str((out/'manifest.json').resolve())]);sessions=r.read(out/'calendar.json')['sessions']
    r.need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==req['window'],'486explicit source sessions')
    packets={c:r.read_bound(out/'codes'/(c+'.json'),h) for c,h in m['per_code_sha256'].items()}
    r.need(len(packets)==31 and all([b['date'] for b in p['bars']]==sessions and all(b['isST']=='0' for b in p['bars']) for p in packets.values()),'complete31ordinary mainboard source packets')
    proof=r.read(root/PROOF)['primary_review'];events,receipts=compile_distribution_events(packets,proof,TradingCalendar(sessions))
    r.need(len(events)==72 and sum(p['requires_zero_record_ownership_if_tax_unverified'] for p in receipts)==2,'same72events and two unresolved noncash constraints')
    r.need(r.sha(root/TARGET)==m['target_sha256'],'targets must match original captured primary identity')
    targets=r.read_bound(root/TARGET,known[str((root/TARGET).resolve())])[PROFILE['candidate']]
    r.need(len(targets)==24 and {c for t in targets.values() for c in t['weights']}==set(packets),'exact24targets/31names unchanged')
    return {'known':known,'request_sha256':expected,'calendar':TradingCalendar(sessions),
            'bars':{c:{b['date']:b for b in p['bars']} for c,p in packets.items()},'events':events,'event_receipts':receipts,'targets':targets}

def execute(auth,out,*,simulation=simulate_low_operating_proxy):
    out=Path(out);r.need(not out.exists() and not r.changed(auth['known']),'fresh unchanged raw account');out.mkdir();outputs={};cases={};results={};error=None;stage='SETUP'
    terminal={'status':'CASH_ACCRUAL_INTEGER_ACCOUNT_INCOMPLETE','complete':False,'request_sha256':auth['request_sha256'],
      'portfolio_return_computed':False,'objective_achieved':False,'2026_values_used_for_selection':False,'physical_investment_admitted':False}
    def save(n,v):r.persist(out,n,clean(v),outputs)
    try:
        save('events.json',[asdict(e) for e in auth['events']]);save('event_receipts.json',auth['event_receipts'])
        for bps in PROFILE['extra_bps']:
            stage='CASE_'+str(bps);print('cash-accrual integer account',bps,'bps',flush=True)
            factory=partial(StockDistributionAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps))
            case=simulation(auth['calendar'],auth['bars'],auth['events'],auth['targets'],PROFILE['initial_CNY'],
                lifecycles={},policy={'simulated_warning_buy_agreement':False,'warning_daily_buy_cap':500000,'warnings':{}},
                policy_id=PROFILE['candidate'],account_factory=factory)
            r.need(len(case['intents'])==24 and len(case['days'])==486 and case['whole_day_volume_violations']==0,'complete continuous account and necessary observed capacity checks')
            zero=unknown_checks(case,auth['events'],auth['event_receipts']);r.need(len(zero)==2,'both actual unresolved noncash ownership receipts required')
            save(str(bps)+'/case.json',case);save(str(bps)+'/zero_ownership.json',zero);cases[str(bps)]=case
        stage='SUMMARY'
        for bps,c in cases.items():
            days=[v for v in c['days'] if v['day']>='2024-01-02'];peak=Decimal(PROFILE['initial_CNY']);dd=Decimal(0)
            for v in days:peak=max(peak,v['equity']);dd=min(dd,v['equity']/peak-1)
            results[bps]={**summarize_case(c,PROFILE['initial_CNY']),'average_exposure_pct':float(sum(v['exposure'] for v in days)/len(days)*100),
                          'max_drawdown_pct':float(dd*100),'account_sessions':len(days),'unverified_noncash_zero_ownership_verified':True}
        p=results['40'];passed=min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90
        save('results.json',results);terminal.update(status='CASH_ACCRUAL_INTEGER_PRE2026_COMPLETE',complete=True,
            portfolio_return_computed=True,results_by_extra_bps=results,development_gate_passes=passed,
            next_step='SEPARATE_LEDGER_QA_THEN_FROZEN2026_EXTENSION' if passed else 'REJECT_FROZEN_CANDIDATE_NO2026_RUN',
            all_fills_integer=True,source_level='RAW_DAILY_OPEN_PROXY_FLAT20PCT_CASH_RESERVE_NOT_FIFO_NOT_AUCTION_LIQUIDITY')
    except BaseException as exc:
        error=exc;terminal.update(error_type=type(exc).__name__,error=str(exc),failed_stage=stage,failed_row_index=None)
        if hasattr(exc,'account_failure_state'):
            try:save('failed_account_state.json',exc.account_failure_state)
            except BaseException as failure:exc.add_note('failure state persistence:'+type(failure).__name__)
    try:value=finish_account(out,terminal,auth['known'],outputs)
    except BaseException as exc:
        if error is None:error=exc
        else:error.add_note('publication failure:'+type(exc).__name__)
    if error is not None:raise error
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1]
    auth=verify(base,root,Path(a.request).resolve(),a.expected_request_sha256);print(execute(auth,base/OUTPUT)['status'])
if __name__=='__main__':main()
