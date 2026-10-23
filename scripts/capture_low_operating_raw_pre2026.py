"""One openly adaptive follow-up; source-only wrapper over the frozen shared adapter."""
import argparse
from datetime import date
import hashlib
import json
import math
import os
from importlib.metadata import version
from pathlib import Path

from scripts import capture_low_market_residual_vol_raw_pre2026 as core
from scripts.capture_asset_expansion_raw_pre2026 import source_fingerprint as old_fingerprint,choose_route
from scripts.capture_budgeted_residual_raw_pre2026 import load_reuse_packet
from scripts.immutable_http_capture import need,write_once,file_sha as sha

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
FAMILY='operating_profit_prior_assets_bottom_decile_control'
OUTPUT='low-operating-profitability-raw-pre2026-v1-20261023'
STATUS='FROZEN_LOW_OPERATING_FOLLOWUP_PRE2026_SOURCE_CAPTURE'
CALENDAR='qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
TRAINING='operating-profitability-conditional-development-v1-20261023'
PREFIX='experiments/qlib/'
RESULT=PREFIX+'operating-profitability-pre2026-results.json'
PROOF=PREFIX+'operating-profitability-pre2026-independent-check.json'
TARGET=PREFIX+'operating-profitability-pre2026-targets.json'
RECEIPTS=PREFIX+'operating-profitability-pre2026-formation-receipts.json'
TRAINING_SHA={RESULT:'4df4da7060a746c0c4b748323e4a09c0f882b5d8ba670b6c5bd0adf6666c13e9',
 PROOF:'c42d2d584d5d813000f248884be39521c4619a19d7d9e9f14bf35fef175f9897',
 TARGET:'d56de5a1fcce5e404b7a795f75fa92cfd5197a95e1d5a2a017b41caed3cc4dfa',
 RECEIPTS:'6259b638783c13c7f014dd6d67c8d099353e9f5c2eee0dfcb31f859899927e7d'}
SOURCES=('asset-expansion-raw-pre2026-20261022','low-market-residual-vol1m-raw-pre2026-20261021',
 'budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020','return-families-raw-dev-20261017')
SELECTION=PREFIX+'low-operating-profitability-continuation.json'
INVENTORY=PREFIX+'low-operating-profitability-raw-source-inventory.json'
REVIEW=PREFIX+'low-operating-profitability-raw-source-review.json'
DESIGN='docs/research/low-operating-profitability-source-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-profitability-sources.md'
ORIGINAL_AUDIT=PREFIX+'audit_sources/2026-10-22-asset-expansion-raw-source-audit.py'
METHODS=tuple(dict.fromkeys((*core.METHOD_FILES,'scripts/capture_asset_expansion_raw_pre2026.py','scripts/immutable_http_capture.py',
 'scripts/capture_low_operating_raw_pre2026.py','scripts/audit_low_operating_raw_pre2026.py',ORIGINAL_AUDIT,
 'tests/test_low_operating_raw_sources.py','tests/test_low_operating_raw_audit.py')))
PUBLIC=(SELECTION,INVENTORY,REVIEW,DESIGN,PLAN)


def read(p):return json.loads(Path(p).read_text())
def hash_bytes(v):return hashlib.sha256(v).hexdigest()


def source_fingerprint(packet):
    for row in [*packet['distributions'],*(q.get('record',{}) for q in packet['quarantine'])]:
        for key in ('dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate'):
            value=row.get(key)
            if value:need(date.fromisoformat(value).isoformat()==value and value<=END,'all corporate/quarantine dates must precede2026')
    return old_fingerprint(packet)


def selection(root):
    for p,h in TRAINING_SHA.items():need(sha(root/p)==h,'unchanged complete known development evidence')
    result,proof=read(root/RESULT),read(root/PROOF);metrics=result['results_by_extra_bps_and_family']['40/'+FAMILY]
    need(result['selected_development_lead'] is None and proof['status']=='PASS_SEPARATE_OPERATING_SOURCE_RANKS_INTENTS_AND_SIX_NATIVE_ACCOUNTS_NOT_RAW_CONFIRMATION'
        and proof['all_inputs_outputs_unchanged'] is True,'original primary rejection and independently checked training retained')
    need(all(type(metrics[k]) in (int,float) and math.isfinite(metrics[k]) for k in ('2024_return_pct','2025_return_pct','average_exposure_pct'))
        and min(metrics['2024_return_pct'],metrics['2025_return_pct'])>0 and metrics['average_exposure_pct']>=90 and metrics['unverified_held_marks']==0,
        'known control satisfies numerical development gate, not original promotion')
    targets=read(root/TARGET)[FAMILY];codes=sorted({c for t in targets.values() for c in t['weights']})
    need(len(targets)==24 and len(codes)==43,'unchanged complete follow-up targets')
    return {'status':'ADAPTIVE_SEEN_DEVELOPMENT_CONTROL_SELECTED_FOR_NEW_FOLLOWUP_NOT_ORIGINAL_LEAD','candidate':CANDIDATE,
        'original_target_family':FAMILY,'original_primary_lead':None,'seen_operating_policies':3,'selected_from_seen_development_control':True,
        'fresh_independent_hypothesis':False,'followup_candidates':1,'source_window':[START,END],'formations':24,'codes':codes,
        'target_sha256':TRAINING_SHA[TARGET],'known_training_metrics_40bps':{k:metrics[k] for k in ('2024_return_pct','2025_return_pct','average_exposure_pct','unverified_held_marks')},
        'training_evidence_sha256':TRAINING_SHA,'strategy_or_targets_changed':False,'2026_values_used_for_selection':False,
        'historical_arrival_verified':False,'raw_share_execution_verified':False,'investment_factor_admitted':False,'objective_achieved':False}


def inventory(base,root):
    selected=selection(root);codes=selected['codes'];proof=read(root/PROOF);paths={'repo/'+p:root/p for p in TRAINING_SHA}
    def bind(name,p,h=None):
        actual=sha(p);need(h is None or actual==h,'original source identity '+name);paths[name]=p;return actual
    for name,h in proof['all_output_sha256'].items():bind('source/'+TRAINING+'/'+name,base/TRAINING/name,h)
    bind('source/'+CALENDAR,base/CALENDAR);sessions=[d for d in (base/CALENDAR).read_text().splitlines() if START<=d<=END]
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'486 actual source sessions')
    manifests={};choices={c:[] for c in codes}
    for directory in SOURCES:
        m=read(base/directory/'manifest.json');bind('source/'+directory+'/manifest.json',base/directory/'manifest.json')
        bind('source/'+directory+'/calendar.json',base/directory/'calendar.json',m['calendar_sha256'])
        need(m['window']==[START,END] and read(base/directory/'calendar.json')['sessions']==sessions,'all source windows/calendars agree')
        manifests[directory]=m
        for code in codes:
            if code not in m['per_code_sha256']:continue
            relative=directory+'/codes/'+code+'.json';p=base/relative;h=bind('source/'+relative,p,m['per_code_sha256'][code])
            packet,diagnostic=load_reuse_packet(p,code,h,sessions)
            choices[code].append({'directory':directory,'file':relative,'packet_sha256':h,'fingerprint':source_fingerprint(packet),'complete_calendar':diagnostic['full_explicit_calendar_covered']})
    routes={};fresh=[]
    for code in codes:
        route=choose_route(choices[code])
        if route is None:fresh.append(code)
        else:routes[code]=route
    return {'status':'LOW_OPERATING_FOLLOWUP_PRE2026_SOURCE_INVENTORY_NOT_ACCOUNT_ADMISSION','candidate':CANDIDATE,
        'target_family':FAMILY,'window':[START,END],'codes':codes,'reuse_routes':routes,'fresh_codes':fresh,'all_choices':choices,
        'source_priority':list(SOURCES),'reference_calendar_sha256':sha(base/CALENDAR),'target_sha256':TRAINING_SHA[TARGET],
        'input_sha256':{k:sha(p) for k,p in sorted(paths.items())},'historical_arrival_verified':False,'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False},sessions,paths


def validate_scope(r):
    need(r['status']==STATUS and r['candidate']==CANDIDATE and r['target_family']==FAMILY and r['window']==[START,END]
        and len(r['codes'])==len(set(r['codes']))==43 and len(r['reuse_routes'])==42 and r['fresh_codes']==['SZ002326']
        and set(r['reuse_routes'])==set(r['codes'])-{'SZ002326'} and r['maximum_new_query_reservations']==4
        and r['maximum_administrative_login_attempts']==1 and r['max_attempts_per_query']==1 and r['socket_timeout_seconds']==20
        and r['baostock_version']=='0.9.4' and r['portfolio_returns_permitted'] is False and r['2026_values_permitted'] is False,
        'exact one-followup43-name42+1/four-query pre2026 capture scope')


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'frozen follow-up source request');r=read(request);validate_scope(r)
    inv,sessions,paths=inventory(base,root)
    need(r['inventory']==inv and read(root/INVENTORY)==inv and read(root/SELECTION)==selection(root)
        and r['codes']==inv['codes'] and r['reuse_routes']==inv['reuse_routes'] and r['fresh_codes']==inv['fresh_codes']
        and r['target_sha256']==inv['target_sha256'] and r['reference_calendar_sha256']==inv['reference_calendar_sha256'],'unchanged selected sources and inventory')
    need(set(r['method_sha256'])==set(METHODS) and version('baostock')=='0.9.4','fixed methods and installed SDK')
    for p in (*METHODS,*PUBLIC):paths['repo/'+p]=root/p
    need(set(paths)==set(r['input_sha256']),'complete source/selection/method binding set')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'follow-up source input '+k)
    for p,h in r['method_sha256'].items():need(h==r['input_sha256']['repo/'+p],'explicit method identity')
    paths['frozen_request']=request
    return r,{'sessions':sessions,'reuse_routes':{c:{**route,'path':str(base/route['file'])} for c,route in r['reuse_routes'].items()},
        'known_hashes':{str(p.resolve()):expected if k=='frozen_request' else r['input_sha256'][k] for k,p in paths.items()}}


def execute(req,auth,out,sdk,*,request_bytes,request_sha):
    need(not out.exists() and not out.is_symlink(),'fresh immutable follow-up capture output')
    need(hash_bytes(request_bytes)==request_sha,'exact request bytes before SDK')
    primary=None;rc=None;result=None
    def unchanged():
        changed=[]
        for p,h in auth['known_hashes'].items():
            try:
                if sha(p)!=h:changed.append(p)
            except BaseException:changed.append(p)
        return changed
    try:rc=core.capture(req,auth,out,sdk,request_bytes=request_bytes,request_sha=request_sha)
    except BaseException as exc:primary=exc
    try:
        out.mkdir(exist_ok=True);m=read(out/'manifest.json') if (out/'manifest.json').exists() else {}
        changed=unchanged();complete=(rc==0 and m.get('capture_complete') is True and m.get('all_source_calendars_complete') is True and not changed and primary is None)
        result={'status':'LOW_OPERATING_FOLLOWUP_RAW_CAPTURE_COMPLETE_NOT_ADMITTED' if complete else 'LOW_OPERATING_FOLLOWUP_SOURCE_FAILURE_RETAINED',
            'candidate':CANDIDATE,'original_target_family':FAMILY,'request_sha256':request_sha,'complete':complete,
            'shared_adapter_origin_status':m.get('status'),'adapter_return_code':rc,'adapter_abnormal_exit':m.get('abnormal_exit'),
            'adapter_errors_sha256':m.get('errors_sha256',{}),'all_inputs_unchanged':not changed,'changed_inputs':changed,
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'historical_arrival_verified':False,'corporate_action_completeness_verified':False,'physical_account_admitted':False,
            'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}
        for code,h in m.get('per_code_sha256',{}).items():
            packet,diagnostic=load_reuse_packet(out/'codes'/(code+'.json'),code,h,auth['sessions'])
            need(diagnostic['full_explicit_calendar_covered'],'captured packet must cover the full explicit source calendar')
            source_fingerprint(packet)
        write_once(out/'.followup-terminal-pending.json',result)
        late=unchanged()
        if late:
            if primary is None:primary=ValueError('follow-up inputs changed during final persistence')
            result.update(status='LOW_OPERATING_FOLLOWUP_SOURCE_FAILURE_RETAINED',complete=False,all_inputs_unchanged=False,changed_inputs=late,
                original_error={'type':type(primary).__name__,'message':str(primary)})
            write_once(out/'.followup-terminal-failure.json',result);os.replace(out/'.followup-terminal-failure.json',out/'followup-terminal.json')
        else:os.replace(out/'.followup-terminal-pending.json',out/'followup-terminal.json')
    except BaseException as exc:
        if primary is None:primary=exc
        late=unchanged();failure={**(result or {}),'status':'LOW_OPERATING_FOLLOWUP_SOURCE_FAILURE_RETAINED','complete':False,
            'all_inputs_unchanged':not late,'changed_inputs':late,'original_error':{'type':type(primary).__name__,'message':str(primary)}}
        try:write_once(out/'.followup-finalization-failure.json',failure);os.replace(out/'.followup-finalization-failure.json',out/'followup-terminal.json')
        except BaseException as secondary:primary.add_note('follow-up terminal persistence failed: '+type(secondary).__name__)
    if primary is not None:raise primary
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--inventory-only',action='store_true');p.add_argument('--output',required=True)
    p.add_argument('--request');p.add_argument('--expected-request-sha256');p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];base=Path(a.source_root).resolve();out=Path(a.output).resolve()
    need(not out.exists(),'new source output only')
    if a.inventory_only:
        inv,_,_=inventory(base,root);write_once(out,inv);print('source inventory',len(inv['reuse_routes']),'reused',inv['fresh_codes'],'fresh; no returns',flush=True);return 0
    need(a.request and a.expected_request_sha256,'frozen source request required')
    r,auth=authenticate(base,root,Path(a.request).resolve(),a.expected_request_sha256)
    need(out==base/OUTPUT,'fixed follow-up capture directory')
    if a.preflight_only:print('source-only full preflight PASS; no SDK connection',flush=True);return 0
    class DeferredSDK:
        def __init__(self):self.client=None
        def login(self):self.client=core.load_sdk();return self.client.login()
        def logout(self):return self.client.logout() if self.client is not None else None
        def __getattr__(self,name):return getattr(self.client,name)
    result=execute(r,auth,out,DeferredSDK(),request_bytes=Path(a.request).read_bytes(),request_sha=a.expected_request_sha256)
    print(result['status'],flush=True);return 0 if result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
