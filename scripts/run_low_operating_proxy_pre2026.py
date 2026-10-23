"""Frozen amendment-aware joined-source continuous daily-proxy development.

No strategy search, network, broker access, FIFO tax or2026admission.
"""
import argparse,json,hashlib,os
from dataclasses import asdict
from datetime import date
from functools import partial
from pathlib import Path
from scripts import decode_low_operating_sina_pre2026 as source
from scripts.replay_low_operating_proxy_targets import simulate_low_operating_proxy
from scripts.run_low_risk_raw_share_validation import clean,summarize_case
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.operating_amendments import reform_receipts,RECONSTRUCTED
from stock_rsi.stock_distribution_account import StockDistributionAccount
from scripts.audit_low_operating_lifecycle_sources_pre2026 import BOUNDARIES

sha,changed,tree,persist=source.sha,source.changed,source.tree,source.persist
need=source.legacy.need
PREFIX='experiments/qlib/'
PINS={PREFIX+'low-operating-full-historical-state-source-root-check.json':'ce0b5f9612e65fc4f4aa845cc06658ec241b8c13f30ff764f060bb5e54e4f26e',PREFIX+'low-operating-restatement-primary-root-check.json':'df416d823cdb0f87361fbcfbbd0b57760e815502aa06881d91190cd428c5ce01',PREFIX+'low-operating-primary-action-root-check.json':'958af1c37b1938712c05a18dd2a29d0847ecd3fd0bf9f585a61b9ec4a6ae52e2'}
TARGET=PREFIX+'operating-profitability-pre2026-targets.json';TARGET_SHA='d56de5a1fcce5e404b7a795f75fa92cfd5197a95e1d5a2a017b41caed3cc4dfa'
FORM=PREFIX+'operating-profitability-pre2026-formation-receipts.json';FORM_SHA='6259b638783c13c7f014dd6d67c8d099353e9f5c2eee0dfcb31f859899927e7d'
META=PREFIX+'low-operating-known-amendment-metadata.json';PAYLOAD=PREFIX+'low-operating-known-amendment-payload.json';REVIEW=PREFIX+'low-operating-proxy-account-review.json'
DESIGN='docs/research/low-operating-proxy-account-design-2026-10-23.md';PLAN='docs/superpowers/plans/2026-10-23-low-operating-proxy-account.md'
METHODS=('src/stock_rsi/operating_amendments.py','src/stock_rsi/mainboard_daily_proxy.py','scripts/replay_low_operating_proxy_targets.py','scripts/run_low_operating_proxy_pre2026.py','tests/test_operating_amendments.py','tests/test_low_operating_proxy_account.py')
OUTPUT='low-operating-proxy-account-pre2026-v1-20261023';FAMILY='operating_profit_prior_assets_bottom_decile_control'
PROFILE={'status':'FROZEN_LOW_OPERATING_AMENDMENT_AWARE_JOINED_DAILY_PROXY_ACCOUNT','candidate':source.CANDIDATE,'window':[source.START,source.END],'initial_CNY':'1000000','extra_bps':[20,40],'target_exposure':.95,'simulated_warning_buy_agreement':True,'allow_conditional_joined_target':True,'source_visibility':RECONSTRUCTED,'network_or_2026_selection_permitted':False}

def read(path,expected=None):
    data=Path(path).read_bytes();need(len(data)<=16*1024*1024,'bounded16MiBJSONinput');need(expected is None or hashlib.sha256(data).hexdigest()==expected,'authenticated actual JSONbuffer')
    def bad(v):raise ValueError('nonfinite JSONconstant')
    return json.loads(data,parse_constant=bad)

def bindings(base,root):
    known={}
    def bind(p,h):
        p=Path(p).resolve();need(not p.is_symlink() and (str(p) not in known or known[str(p)]==h) and sha(p)==h,'unchanged source binding '+str(p));known[str(p)]=h
    for name,h in PINS.items():
        bind(root/name,h);p=read(root/name,h)
        for f,value in p['all_input_sha256'].items():bind(f,value)
        caps=p['all_capture_sha256']
        if name.endswith('primary-action-root-check.json'):
            for folder,files in caps.items():
                need(tree(base/folder)==files,'whole primary capture tree')
                for f,value in files.items():bind(base/folder/f,value)
            folder=base/'low-operating-primary-reviewed-v1-20261023';need(tree(folder)==p['reviewed_local_artifact_sha256'],'whole reviewed primary tree')
            for f,value in p['reviewed_local_artifact_sha256'].items():bind(folder/f,value)
        else:
            folder=base/('low-operating-full-historical-state-source-v1-20261023' if 'full-historical' in name else 'low-operating-restatement-primary-v1-20261023');need(tree(folder)==caps,'whole historical capture tree')
            for f,value in caps.items():bind(folder/f,value)
            if 'all_projection_sha256' in p:
                folder=base/'low-operating-full-historical-state-projection-v1-20261023';need(tree(folder)==p['all_projection_sha256'],'whole component projection')
                for f,value in p['all_projection_sha256'].items():bind(folder/f,value)
        for f,value in p['public_copy_sha256'].items():bind(root/f,value)
    for name,h in ((TARGET,TARGET_SHA),(FORM,FORM_SHA)):bind(root/name,h)
    for name in (*METHODS,META,PAYLOAD,DESIGN,PLAN,REVIEW):bind(root/name,sha(root/name))
    need(not changed(known),'complete source/method graph');return known

def load_data(base,root,known):
    def load(p):return read(p,known[str(Path(p).resolve())])
    raw=base/source.RAW;m=load(raw/'manifest.json');sessions=load(raw/'calendar.json')['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[source.START,source.END],'same486explicit sessions');calendar=TradingCalendar(sessions)
    packets={c:load(raw/'codes'/(c+'.json')) for c in m['per_code_sha256']};need(len(packets)==42 and 'SZ002326' not in packets,'same42original packets')
    proof=load(root/PREFIX/'low-operating-primary-action-reviewed-manifest.json');events,event_receipts=compile_distribution_events(packets,proof,calendar)
    need(len(events)==64 and all(e.stock_per_share==e.capital_per_share==0 for e in events) and clean([asdict(e) for e in events])==load(root/PREFIX/'low-operating-primary-action-events.json') and list(event_receipts)==load(root/PREFIX/'low-operating-primary-action-event-receipts.json'),'same64cash events and actual original compilation')
    need({v['fiscal_year'] for v in proof['annual_zero_distribution_reviews']}=={2023,2024} and all(v['instrument']=='SZ002326' and not(v['cash'] or v['bonus_stock'] or v['capital_transfer']) for v in proof['annual_zero_distribution_reviews']),'known primary annualzero scope')
    projection=load(root/PREFIX/'low-operating-full-historical-state-source-summary.json');need(projection['source_component_projection_complete'] and not projection['preclose_previous_observed_close_changes'] and projection['printed_name_counts']=={'永太科技':486},'explicit conditional joined/noobserved corporate priceaction profile')
    joined=load(root/PREFIX/'low-operating-full-historical-state-components.json');need([v['date'] for v in joined]==sessions,'complete joined calendar');bars={c:{v['date']:v for v in p['bars']} for c,p in packets.items()};bars['SZ002326']={}
    for v in joined:
        need(v['instrument']=='SZ002326' and v['printed_name']=='永太科技' and v['inferred_warning_label']=='0' and v['native_exchange_state_flag_provided'] is False and v['positive_observed_trading_activity'] is True and int(v['observed_volume_shares'])>0,'explicit joined inference provenance')
        bars['SZ002326'][v['date']]={k:v[k] for k in ('date','open','high','low','close','preclose')}
        bars['SZ002326'][v['date']].update(volume=v['observed_volume_shares'],tradestatus='1',isST='0',source_kind=v['source_kind'],state_evidence='CONDITIONAL_PRIMARY_HISTORICAL_NAME_AND_POSITIVE_SINA_VOLUME',official_body_sha256=v['official_body_sha256'])
    meta=load(root/META)
    def amendment_payload(key):
        need(any(v['key']==key for v in meta),'registered amendment payload key')
        payload=load(root/PAYLOAD);primary=load(root/PREFIX/'low-operating-restatement-primary-review.json')
        need(payload['before_assets_CNY']==primary['consolidated_total_assets_2021_12_31']['before_CNY'] and payload['after_assets_CNY']==primary['consolidated_total_assets_2021_12_31']['after_CNY'] and {v['sha256'] for v in payload['documents']}=={v['source_sha256'] for v in primary['documents'] if v['role']=='issuer_correction'},'actual known correction literals/PDFs')
        return payload
    formations=load(root/FORM);targets,amended=reform_receipts(formations,meta,amendment_payload,RECONSTRUCTED);original=load(root/TARGET)[FAMILY]
    need(len(formations)==len(original)==24 and targets[FAMILY]==original and len({c for v in original.values() for c in v['weights']})==43 and set(bars)=={c for v in original.values() for c in v['weights']},'amended source must preserve exact frozen24targets/43names')
    need(sum(len(v['known_amendment_receipts']) for v in amended)==1,'exactly one known source correction is applicable')
    st=load(root/PREFIX/'low-operating-SZ002092-ST-primary-review.json');policy={'simulated_warning_buy_agreement':True,'warning_daily_buy_cap':500000,'warnings':{'SZ002092':{'start':'2024-05-21','end':'2025-05-19','published_on':'2024-05-18','rate':'0.05','source_sha256':st['source_sha256']}}}
    need(st['effective_warning_day']=='2024-05-21' and st['daily_limit_after']=='0.05','known primary warning rule')
    need(not changed(known),'all loaded source buffers and inputs unchanged')
    return {'calendar':calendar,'bars':bars,'events':events,'targets':original,'lifecycles':BOUNDARIES,'policy':policy,'initial_CNY':'1000000','extra_bps':[20,40],'formation_receipts':amended,'event_receipts':list(event_receipts)}

def authenticate(base,root,request,expected):
    req=read(request,expected);need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed source/account profile')
    need(set(req['method_sha256'])==set(METHODS) and all(sha(root/n)==h for n,h in req['method_sha256'].items()),'current frozen methods before source values')
    known=bindings(base,root);need(known==req['input_sha256'],'complete exact frozen source/method closure');known[str(request.resolve())]=expected
    data=load_data(base,root,known);return {**data,'known':known,'request_sha256':expected}

def finish_account(out,state,known,outputs):
    """Publish authenticated account evidence; quarantine every rejected ROI candidate.

    The immutable source-only finalizer does not know account return fields.
    Failure receipts retain actual artifact hashes and the intended hashes separately.
    """
    expected=dict(outputs)
    terminal={**state,'capture_sha256':expected,'all_inputs_unchanged':not changed(known),'all_outputs_unchanged':tree(out)==expected}
    try:
        need(terminal['all_inputs_unchanged'] and terminal['all_outputs_unchanged'],'account context before terminal persistence')
        encoded=(json.dumps(terminal,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode();terminal_sha=hashlib.sha256(encoded).hexdigest()
        pending=out/'.terminal-pending.json';source.legacy.write_once(pending,terminal)
        need(not changed(known) and tree(out)=={**expected,'.terminal-pending.json':terminal_sha},'account context during terminal persistence')
        os.replace(pending,out/'terminal.json')
        need(not changed(known) and tree(out)=={**expected,'terminal.json':terminal_sha},'account context after terminal publication')
        return terminal
    except BaseException as primary:
        try:
            archives={}
            for original,name in ((out/'terminal.json','terminal-rejected-published.json'),(out/'.terminal-pending.json','terminal-rejected-staged.json')):
                if original.exists():os.replace(original,out/name);archives[name]=sha(out/name)
            data={k:h for k,h in tree(out).items() if k not in archives};outputs_unchanged=data==expected
            if (out/'results.json').exists():
                os.replace(out/'results.json',out/'results-rejected.json');archives['results-rejected.json']=sha(out/'results-rejected.json')
            failure={k:v for k,v in state.items() if k!='results_by_extra_bps'}
            failure.update(status='LOW_OPERATING_PROXY_PUBLICATION_FAILURE_RETAINED',complete=False,portfolio_return_computed=False,
                physical_investment_admitted=False,source_and_investment_admitted=False,objective_achieved=False,
                capture_sha256=tree(out),intended_capture_sha256=expected,rejected_artifact_sha256=archives,
                all_inputs_unchanged=not changed(known),all_outputs_unchanged=outputs_unchanged,
                error_type=type(primary).__name__,error=str(primary),failed_stage='TERMINAL',failed_row_index=None)
            if 'error_type' in state:failure['prior_failure']={k:state.get(k) for k in ('error_type','error','failed_stage','failed_row_index')}
            source.legacy.write_once(out/'.terminal-failure-pending.json',failure);os.replace(out/'.terminal-failure-pending.json',out/'terminal.json')
        except BaseException as secondary:primary.add_note('account failure receipt persistence: '+type(secondary).__name__)
        raise primary

def execute(auth,out):
    out=Path(out);need(not out.exists() and not out.is_symlink(),'fresh conditional account output');need(not changed(auth['known']),'inputs before account creation');out.mkdir();outputs={};primary=None;cases={};terminal={'status':'LOW_OPERATING_PROXY_INCOMPLETE','complete':False,'request_sha256':auth['request_sha256'],'portfolio_return_computed':False,'physical_investment_admitted':False,'2026_values_used_for_selection':False,'objective_achieved':False}
    def save(n,v):persist(out,n,clean(v),outputs)
    def boundary():need(not changed(auth['known']) and tree(out)==outputs,'all account inputs/outputs unchanged')
    stage='SETUP'
    try:
        save('formation_receipts.json',auth['formation_receipts']);save('event_source_receipts.json',auth['event_receipts'])
        for bps in auth['extra_bps']:
            stage='CASE_'+str(bps);boundary();factory=partial(StockDistributionAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=bps))
            case=simulate_low_operating_proxy(auth['calendar'],auth['bars'],auth['events'],auth['targets'],auth['initial_CNY'],lifecycles=auth['lifecycles'],policy=auth['policy'],account_factory=factory)
            need(len(case['intents'])==len(auth['targets']) and case['whole_day_volume_violations']==0,'all target decisions and observed daily capacity required');cases[bps]=case;save(str(bps)+'/case.json',case);boundary()
        need(set(cases)=={20,40},'both frozen costs complete before any annual ROI');stage='SUMMARY';result={}
        for bps,case in cases.items():
            boundary();metrics=summarize_case(case,auth['initial_CNY']);days=[v for v in case['days'] if v['day']>='2024-01-02'];metrics.update(average_exposure_pct=float(sum(v['exposure'] for v in days)/len(days)*100),max_daily_volume_fraction=str(case['max_daily_volume_fraction']),execution_status=case['execution_status']);result[str(bps)]=metrics
        save('results.json',result);terminal.update(status='LOW_OPERATING_CONDITIONAL_DAILY_PROXY_COMPLETE',complete=True,portfolio_return_computed=True,results_by_extra_bps=result,source_evidence_level='RECONSTRUCTED_JOINED_DAILY_OPEN_PROXY_FLAT20PCT_DIVIDEND_RESERVE_NOT_FIFO',source_and_investment_admitted=False)
    except BaseException as exc:
        primary=exc;terminal.update(status='LOW_OPERATING_PROXY_NATIVE_FAILURE_RETAINED',error_type=type(exc).__name__,error=str(exc),complete=False,portfolio_return_computed=False,failed_stage=stage,failed_row_index=None)
        terminal.pop('results_by_extra_bps',None)
        if hasattr(exc,'account_failure_state'):
            try:save('failed_account_state.json',exc.account_failure_state)
            except BaseException as secondary:primary.add_note('failed state persistence: '+type(secondary).__name__)
    try:value=finish_account(out,terminal,auth['known'],outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal persistence: '+type(exc).__name__)
    if primary is not None:raise primary
    return value

def run(base,root,request,expected):return execute(authenticate(base,root,request,expected),base/OUTPUT)
def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];q=Path(a.request).resolve()
    if a.preflight_only:authenticate(base,root,q,a.expected_request_sha256);print('preflight PASS: target parity, no account/ROI');return
    v=run(base,root,q,a.expected_request_sha256);print(v['status'])
if __name__=='__main__':main()
