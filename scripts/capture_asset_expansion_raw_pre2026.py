"""One frozen pre2026 source capture; no account, selection or return work."""
import argparse
import hashlib
import json
import socket
from importlib.metadata import version
from pathlib import Path

from scripts.capture_budgeted_residual_raw_pre2026 import fetch_packet,load_reuse_packet
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_frozen_target_development_data import target_codes
from scripts.capture_illiquidity_raw_development import calendar_diagnostic,read_vendor_response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,source_code
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_asset_expansion_decile_conditional'
TARGET='asset-expansion-conditional-development-v1-20261022/targets.json'
CALENDAR='qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt'
SOURCES=('low-market-residual-vol1m-raw-pre2026-20261021',
    'budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020',
    'return-families-raw-dev-20261017')
METHOD_FILES=('scripts/capture_asset_expansion_raw_pre2026.py',
    'scripts/capture_budgeted_residual_raw_pre2026.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/capture_frozen_target_development_data.py',
    'scripts/capture_illiquidity_raw_development.py','scripts/capture_low_risk_raw_account_data.py',
    'scripts/fundamental_query_journal.py','tests/test_asset_expansion_raw_sources.py')
PUBLIC_FILES=('experiments/qlib/asset-expansion-pre2026-results.json',
    'experiments/qlib/asset-expansion-pre2026-audit.json')


def read(path):return json.loads(Path(path).read_text())


def source_fingerprint(packet):
    if packet['window']!=[START,END]:raise ValueError('physically pre2026 source window required')
    content={}
    for field,key in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        if any(not START<=row[key]<=END for row in packet[field]):raise ValueError('future source row')
        content[field]=sorted(json.dumps(row,sort_keys=True,separators=(',',':')) for row in packet[field])
    content['quarantine']=sorted(json.dumps(row,sort_keys=True,separators=(',',':')) for row in packet['quarantine'])
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def choose_route(choices):
    if not choices:return None
    if any(not v['complete_calendar'] for v in choices):raise ValueError('source calendar gap requires review')
    if len({v['fingerprint'] for v in choices})!=1:raise ValueError('source price/action contradiction requires review')
    return choices[0]


def inventory(base,repo):
    results,audit=(read(repo/n) for n in PUBLIC_FILES)
    if (results['selected_development_lead']!=CANDIDATE or audit['selected_development_lead']!=CANDIDATE
            or not audit['all_inputs_and_outputs_unchanged'] or audit['raw_share_execution_verified'] is not False
            or results['2026_financial_or_market_values_read'] is not False):
        raise ValueError('fixed audited development primary required')
    target=base/TARGET
    if sha256_file(target)!=results['targets_sha256']:raise ValueError('fixed development targets changed')
    targets=read(target)[CANDIDATE];codes=target_codes(targets)
    if len(targets)!=24 or len(codes)!=36:raise ValueError('complete24formation36name primary required')
    sessions=[v for v in (base/CALENDAR).read_text().splitlines() if START<=v<=END]
    if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=[START,END]:
        raise ValueError('complete explicit source calendar required')
    manifests={n:read(base/n/'manifest.json') for n in SOURCES}
    for n,m in manifests.items():
        if m['window']!=[START,END] or sha256_file(base/n/'calendar.json')!=m['calendar_sha256']:
            raise ValueError('pre2026 source manifest/calendar identity changed')
        if read(base/n/'calendar.json')['sessions']!=sessions:raise ValueError('source calendars disagree')
    choices={};routes={};fresh=[]
    for code in codes:
        choices[code]=[]
        for n,m in manifests.items():
            if code not in m['per_code_sha256']:continue
            h=m['per_code_sha256'][code];packet,diagnostic=load_reuse_packet(base/n/'codes'/(code+'.json'),code,h,sessions)
            choices[code].append({'directory':n,'packet_sha256':h,'fingerprint':source_fingerprint(packet),
                'complete_calendar':diagnostic['full_explicit_calendar_covered']})
        route=choose_route(choices[code])
        if route is None:fresh.append(code)
        else:routes[code]=route
    return {'status':'ASSET_EXPANSION_PRE2026_SOURCE_INVENTORY_NOT_ADMISSION',
        'candidate':CANDIDATE,'window':[START,END],'codes':codes,'target_sha256':sha256_file(target),
        'source_priority':list(SOURCES),'source_manifests_sha256':{n:sha256_file(base/n/'manifest.json') for n in SOURCES},
        'reference_calendar_sha256':sha256_file(base/CALENDAR),'reuse_routes':routes,'fresh_codes':fresh,'all_choices':choices,
        'public_evidence_sha256':{n:sha256_file(repo/n) for n in PUBLIC_FILES},
        'new_network_queries':0,'2026_values_read':False,'source_admitted_for_replay':False,
        'corporate_action_completeness_verified':False,'historical_arrival_verified':False,'objective_achieved':False},sessions


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--output',required=True)
    p.add_argument('--inventory-only',action='store_true');p.add_argument('--request');p.add_argument('--expected-request-sha256')
    a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output)
    if out.exists():raise ValueError('preserve original source output; no automatic retry')
    current,sessions=inventory(base,repo)
    if a.inventory_only:
        write_packet_once(out,current);print('inventory',len(current['reuse_routes']),'reused',current['fresh_codes'],'fresh',flush=True);return 0
    if not a.request or sha256_file(a.request)!=a.expected_request_sha256:raise ValueError('frozen source request required')
    r=read(a.request)
    if (r['status']!='FROZEN_ASSET_EXPANSION_PRE2026_RAW_SOURCE_CAPTURE'
            or r['inventory']!=current or r['baostock_version']!=version('baostock')
            or r['max_attempts_per_query']!=1 or r['administrative_login_budget']!=1
            or r['maximum_new_query_reservations']!=4*len(current['fresh_codes'])
            or r['maximum_new_query_reservations']>16 or r['socket_timeout_seconds']!=20
            or set(r['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(repo/n)!=h for n,h in r['method_code_sha256'].items())
            or sha256_file(repo/r['protocol_file'])!=r['protocol_sha256']):
        raise ValueError('fixed source capture methods/budget changed')
    (out/'codes').mkdir(parents=True);(out/'request.json').write_bytes(Path(a.request).read_bytes())
    atomic_json(out/'calendar.json',{'sessions':sessions,'origin_sha256':current['reference_calendar_sha256']})
    progress={};errors={};bs=None
    try:
        for code,route in current['reuse_routes'].items():
            source=base/route['directory']/'codes'/(code+'.json')
            if sha256_file(source)!=route['packet_sha256']:raise ValueError('original reuse changed')
            (out/'codes'/(code+'.json')).write_bytes(source.read_bytes());progress[code]=route['packet_sha256']
        atomic_json(out/'progress.json',progress)
        journal=QueryJournal(out,max_queries=max(1,r['maximum_new_query_reservations']),max_attempts=1)
        if current['fresh_codes']:
            import baostock as bs
            socket.setdefaulttimeout(20);write_packet_once(out/'login-reserved.json',{'attempt':1})
            login=bs.login();write_packet_once(out/'login-response.json',{'error_code':login.error_code,'error_msg':login.error_msg})
            if login.error_code!='0':raise RuntimeError('source login failed')
        for code in current['fresh_codes']:
            symbol=source_code(code)
            def fetch(component,parameters):
                if component=='daily':response=bs.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),**parameters)
                elif component.startswith('dividend'):response=bs.query_dividend_data(symbol,**parameters)
                else:response=bs.query_adjust_factor(symbol,**parameters)
                return read_vendor_response(response)
            try:
                packet=fetch_packet(journal,code,a.expected_request_sha256,fetch)
                source_fingerprint(packet)
                if not calendar_diagnostic(packet['bars'],sessions)['full_explicit_calendar_covered']:
                    raise ValueError('fresh source calendar gap requires separate review')
                atomic_json(out/'codes'/(code+'.json'),packet)
                progress[code]=sha256_file(out/'codes'/(code+'.json'));atomic_json(out/'progress.json',progress)
            except Exception as exc:
                write_packet_once(out/(code+'-error.json'),{'error_type':type(exc).__name__,'error':str(exc),'source_responses_retained':True})
                errors[code]=sha256_file(out/(code+'-error.json'));raise
    finally:
        if bs is not None:
            try:bs.logout()
            except Exception as exc:write_packet_once(out/'logout-error.json',{'error_type':type(exc).__name__,'error':str(exc)})
        unchanged=(inventory(base,repo)[0]==current and all(sha256_file(repo/n)==h for n,h in r['method_code_sha256'].items()))
        totals={'bar_rows':0,'distributions':0,'adjustments':0,'quarantines':0}
        for code,h in progress.items():
            packet,_=load_reuse_packet(out/'codes'/(code+'.json'),code,h,sessions)
            for key,field in (('bar_rows','bars'),('distributions','distributions'),('adjustments','adjustments'),('quarantines','quarantine')):totals[key]+=len(packet[field])
        atomic_json(out/'manifest.json',{'status':'ASSET_EXPANSION_RAW_CAPTURE_COMPLETE_NOT_ADMITTED' if len(progress)==36 and not errors and unchanged else 'INCOMPLETE_SOURCE_CAPTURE_RETAINED',
            'request_sha256':a.expected_request_sha256,'window':[START,END],'names':len(progress),'requested_names':36,
            'target_sha256':current['target_sha256'],'calendar_sha256':sha256_file(out/'calendar.json'),
            'per_code_sha256':progress,'errors_sha256':errors,'pending_codes':sorted(set(current['codes'])-set(progress)-set(errors)),
            'totals':totals,'query_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
            'original_inputs_unchanged':unchanged,'source_admitted_for_replay':False,'historical_arrival_verified':False,
            '2026_values_read':False,'portfolio_return_computed':False,'objective_achieved':False})
    print('source capture complete',len(progress),'names; no account returns',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
