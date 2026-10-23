"""Separate primary-boundary source continuation; no account, returns or2026."""
import argparse
from datetime import date
from importlib.metadata import version
import os
from pathlib import Path

from scripts import capture_low_operating_raw_pre2026 as old
from scripts.capture_low_operating_raw_pre2026 import read,sha,hash_bytes,need,write_once
from stock_rsi.lifecycle_source_rows import source_rows_on

START,END=old.START,old.END
CANDIDATE,FAMILY=old.CANDIDATE,old.FAMILY
OUTPUT='low-operating-lifecycle-raw-pre2026-v1-20261023'
STATUS='FROZEN_LOW_OPERATING_PRIMARY_LIFECYCLE_SOURCE_CONTINUATION'
PREFIX=old.PREFIX
FAILURE=PREFIX+'low-operating-profitability-raw-source-inventory-failure.json'
FAILURE_SHA='a27f135dcbfefc4db8005987bbc8f73a7e8ec6cfbb9ca3adcd0c3f4bc01f31b6'
LIFE=PREFIX+'illiquidity-lifecycle-source-evidence.json'
LIFE_SHA='cb70d2a27a81b2fc1e117d9a5d623c41d28be7cf6a7e330187f0194b04cf3780'
REVIEWED='illiquidity-corporate-reviewed-20261020/reviewed-manifest.json'
REVIEWED_SHA='d589c067f1498df1f6cffb810863751414155f05429dc44c934e5be861fa9ae4'
PDF='illiquidity-corporate-reviewed-20261020/SZ002505-delisting-announcement-20240830.pdf'
PDF_SHA='ef704fd9e654757548c8c36725edd22d726a6d7cf71de850b3096f315fe63e9b'
BOUNDARIES={'SZ002505':{'kind':'DELISTING_END','effective_date':'2024-08-30','verified_primary_boundary':True,
    'primary_document_sha256':PDF_SHA,'source_file':Path(PDF).name}}
INVENTORY=PREFIX+'low-operating-lifecycle-source-inventory.json'
REVIEW=PREFIX+'low-operating-lifecycle-source-review.json'
DESIGN='docs/research/low-operating-lifecycle-source-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-lifecycle-sources.md'
METHODS=tuple(dict.fromkeys((*old.METHODS,'scripts/capture_low_operating_lifecycle_sources_pre2026.py',
    'scripts/audit_low_operating_lifecycle_sources_pre2026.py','src/stock_rsi/lifecycle_source_rows.py',
    'tests/test_low_operating_lifecycle_sources.py')))
PUBLIC=(old.SELECTION,FAILURE,LIFE,INVENTORY,REVIEW,DESIGN,PLAN)


def validate_primary(boundary,document):
    need(boundary==BOUNDARIES['SZ002505'] and document['instrument']=='SZ002505'
        and document['day']=='2024-08-30' and document['file']==Path(PDF).name
        and document['sha256']==PDF_SHA,'exact previously reviewed primary delisting proof required')


def primary(base,root):
    paths={'repo/'+LIFE:root/LIFE,'source/'+REVIEWED:base/REVIEWED,'source/'+PDF:base/PDF}
    for k,h in (('repo/'+LIFE,LIFE_SHA),('source/'+REVIEWED,REVIEWED_SHA),('source/'+PDF,PDF_SHA)):
        need(sha(paths[k])==h,'original primary evidence '+k)
    p=read(base/REVIEWED);b=p['lifecycles']['SZ002505'];docs=[d for d in p['documents'] if d['file']==Path(PDF).name]
    need(len(docs)==1,'unique reviewed primary document');validate_primary(b,docs[0])
    reviews=[v for v in read(root/LIFE)['reviews'] if v['instrument']=='SZ002505']
    need(len(reviews)==1 and reviews[0]['primary_document_sha256']==PDF_SHA
        and reviews[0]['listing_or_delisting_boundary']=='2024-08-30','original public primary review')
    return BOUNDARIES,paths


def coverage(packet,sessions,boundaries):
    need(boundaries==BOUNDARIES and sessions==sorted(set(sessions)),'exact primary boundaries and explicit sessions required')
    code=packet['instrument'];days=[v['date'] for v in packet['bars']]
    expected=[d for d in sessions if d<='2024-08-30'] if code=='SZ002505' else sessions
    need(days==expected,'only exact primary delisting tail is allowed, no interior or other gap')
    bars={code:{v['date']:v for v in packet['bars']}};intervals=[]
    for day in sessions:
        _,ex=source_rows_on(bars,date.fromisoformat(day),(),{code:boundaries[code]} if code in boundaries else {})
        intervals.extend(ex)
    return {'full_explicit_calendar_covered':days==sessions,'source_coverage_explained':True,'observed_rows':len(days),
        'missing_sessions':sorted(set(sessions)-set(days)),'lifecycle_intervals':intervals,
        'actual_flat_inventory_proven':False,'synthetic_source_rows_created':0}


def resolve(key,root,base):
    prefix,name=key.split('/',1);need(prefix in ('repo','source') and not Path(name).is_absolute() and '..' not in Path(name).parts,'bound root-relative input')
    return (root if prefix=='repo' else base)/name


def inventory(base,root):
    need(sha(root/FAILURE)==FAILURE_SHA,'preserve original strict inventory failure')
    failure=read(root/FAILURE);paths={k:resolve(k,root,base) for k in failure['input_sha256']}
    for k,p in paths.items():need(sha(p)==failure['input_sha256'][k],'unchanged original failed-inventory input '+k)
    boundaries,extra=primary(base,root);paths.update(extra);paths['repo/'+FAILURE]=root/FAILURE
    selected=old.selection(root);need(selected['codes']==failure['codes'],'same adaptive candidate and all target names')
    sessions=[d for d in (base/old.CALENDAR).read_text().splitlines() if START<=d<=END]
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'exact original486sessions')
    choices={};routes={};fresh=[]
    for code in selected['codes']:
        choices[code]=[]
        for item in failure['all_choices'][code]:
            p=base/item['file'];packet,diag=old.load_reuse_packet(p,code,item['packet_sha256'],sessions)
            need(diag==item['calendar_diagnostic'] and old.source_fingerprint(packet)==item['fingerprint'],'unchanged every original overlap economics/calendar')
            c=coverage(packet,sessions,boundaries)
            choices[code].append({k:item[k] for k in ('directory','file','packet_sha256','fingerprint')}|{'coverage':c})
        if not choices[code]:fresh.append(code);continue
        need(len({v['fingerprint'] for v in choices[code]})==1,'all overlap prices/actions must agree')
        routes[code]=choices[code][0]
    need(len(routes)==42 and fresh==['SZ002326'] and sum(map(len,choices.values()))==87,'unchanged42+1/87overlap continuation')
    return {'status':'LOW_OPERATING_PRIMARY_BOUNDARY_SOURCE_INVENTORY_NOT_ACCOUNT_ADMISSION','candidate':CANDIDATE,'target_family':FAMILY,
        'window':[START,END],'codes':selected['codes'],'reuse_routes':routes,'fresh_codes':fresh,'all_choices':choices,
        'source_priority':list(old.SOURCES),'boundaries':boundaries,'original_failure_sha256':FAILURE_SHA,
        'target_sha256':selected['target_sha256'],'reference_calendar_sha256':sha(base/old.CALENDAR),
        'input_sha256':{k:sha(p) for k,p in sorted(paths.items())},'actual_flat_inventory_proven':False,
        'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False},sessions,paths


def validate_scope(r):
    need(r['status']==STATUS and r['candidate']==CANDIDATE and r['target_family']==FAMILY and r['window']==[START,END]
        and len(r['codes'])==len(set(r['codes']))==43 and len(r['reuse_routes'])==42 and r['fresh_codes']==['SZ002326']
        and set(r['reuse_routes'])==set(r['codes'])-{'SZ002326'} and r['boundaries']==BOUNDARIES
        and r['maximum_new_query_reservations']==4 and r['maximum_administrative_login_attempts']==r['max_attempts_per_query']==1
        and r['socket_timeout_seconds']==20 and r['baostock_version']=='0.9.4'
        and r['portfolio_returns_permitted'] is False and r['2026_values_permitted'] is False,'exact primary-boundary source-only scope')


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'frozen continuation request');r=read(request);validate_scope(r)
    inv,sessions,paths=inventory(base,root)
    need(r['inventory']==inv==read(root/INVENTORY) and read(root/old.SELECTION)==old.selection(root)
        and r['codes']==inv['codes'] and r['reuse_routes']==inv['reuse_routes'] and r['fresh_codes']==inv['fresh_codes']
        and r['target_sha256']==inv['target_sha256'] and r['reference_calendar_sha256']==inv['reference_calendar_sha256'],'exact original sources and continuation inventory')
    need(set(r['method_sha256'])==set(METHODS) and version('baostock')=='0.9.4','fixed source methods and installed SDK')
    for p in (*METHODS,*PUBLIC):paths['repo/'+p]=root/p
    need(set(paths)==set(r['input_sha256']),'complete input closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'bound continuation input '+k)
    for p,h in r['method_sha256'].items():need(h==r['input_sha256']['repo/'+p],'explicit method identity')
    return r,{'sessions':sessions,'boundaries':BOUNDARIES,
        'reuse_routes':{c:{**v,'path':str(base/v['file'])} for c,v in r['reuse_routes'].items()},
        'known_hashes':{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}}


def execute(req,auth,out,sdk,*,request_bytes,request_sha):
    need(not out.exists() and not out.is_symlink() and hash_bytes(request_bytes)==request_sha,'fresh capture and exact request bytes')
    def changed():
        result=[]
        for p,h in auth['known_hashes'].items():
            try:
                if sha(p)!=h:result.append(p)
            except BaseException:result.append(p)
        return result
    managed_terminal_names={'.followup-terminal-pending.json','.followup-finalization-failure.json','followup-terminal.json'}
    def captured_outputs():
        return {str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*'))
            if p.is_file() and str(p.relative_to(out)) not in managed_terminal_names}
    original_outputs=None
    def changed_outputs():
        if original_outputs is None:return []
        current=captured_outputs()
        return sorted(k for k in set(current)|set(original_outputs) if current.get(k)!=original_outputs.get(k))
    result={'status':'LOW_OPERATING_LIFECYCLE_SOURCE_FAILURE_RETAINED','candidate':CANDIDATE,'original_target_family':FAMILY,
        'request_sha256':request_sha,'complete':False,'historical_arrival_verified':False,'corporate_action_completeness_verified':False,
        'actual_flat_inventory_proven':False,'physical_account_admitted':False,'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False,
        'all_capture_outputs_unchanged':False,'changed_capture_outputs':[]}
    primary_error=None;rc=None
    try:rc=old.core.capture(req,auth,out,sdk,request_bytes=request_bytes,request_sha=request_sha)
    except BaseException as exc:primary_error=exc
    try:
        out.mkdir(exist_ok=True);original_outputs=captured_outputs();result['capture_output_sha256']=original_outputs
        m=read(out/'manifest.json') if (out/'manifest.json').exists() else {};checked={}
        result.update(shared_adapter_origin_status=m.get('status'),adapter_return_code=rc,adapter_abnormal_exit=m.get('abnormal_exit'),
            adapter_errors_sha256=m.get('errors_sha256',{}),original_error=None if primary_error is None else {'type':type(primary_error).__name__,'message':str(primary_error)})
        for code,h in m.get('per_code_sha256',{}).items():
            packet,_=old.load_reuse_packet(out/'codes'/(code+'.json'),code,h,auth['sessions'])
            old.source_fingerprint(packet);checked[code]=coverage(packet,auth['sessions'],auth['boundaries'])
        changes=changed();complete=(rc==0 and m.get('capture_complete') is True and set(checked)==set(req['codes']) and not changes and primary_error is None)
        result.update(status='LOW_OPERATING_PRIMARY_BOUNDARY_SOURCES_COMPLETE_NOT_ADMITTED' if complete else result['status'],complete=complete,
            all_source_calendars_complete=m.get('all_source_calendars_complete'),source_coverage=checked,all_inputs_unchanged=not changes,changed_inputs=changes,
            all_capture_outputs_unchanged=True)
        write_once(out/'.followup-terminal-pending.json',result)
        late=changed();late_outputs=changed_outputs()
        result.update(all_capture_outputs_unchanged=not late_outputs,changed_capture_outputs=late_outputs)
        if late_outputs:raise ValueError('capture outputs changed during final persistence')
        if late:
            result.update(complete=False,status='LOW_OPERATING_LIFECYCLE_SOURCE_FAILURE_RETAINED',all_inputs_unchanged=False,changed_inputs=late)
            raise ValueError('continuation inputs changed during final persistence')
        os.replace(out/'.followup-terminal-pending.json',out/'followup-terminal.json')
    except BaseException as exc:
        if primary_error is None:primary_error=exc
        late=changed();late_outputs=changed_outputs();result.update(status='LOW_OPERATING_LIFECYCLE_SOURCE_FAILURE_RETAINED',complete=False,all_inputs_unchanged=not late,
            changed_inputs=late,all_capture_outputs_unchanged=not late_outputs,changed_capture_outputs=late_outputs,
            original_error={'type':type(primary_error).__name__,'message':str(primary_error)})
        try:write_once(out/'.followup-finalization-failure.json',result);os.replace(out/'.followup-finalization-failure.json',out/'followup-terminal.json')
        except BaseException as secondary:primary_error.add_note('terminal persistence failed: '+type(secondary).__name__)
    if primary_error is not None:raise primary_error
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True)
    p.add_argument('--expected-request-sha256',required=True);p.add_argument('--output',required=True);p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];base=Path(a.source_root).resolve();request=Path(a.request).resolve();out=Path(a.output).resolve()
    need(out==base/OUTPUT and not out.exists(),'fixed fresh continuation output');r,auth=authenticate(base,root,request,a.expected_request_sha256)
    if a.preflight_only:print('all original sources/primary-boundary continuation preflight PASS; no SDK',flush=True);return 0
    class DeferredSDK:
        def __init__(self):self.client=None
        def login(self):self.client=old.core.load_sdk();return self.client.login()
        def logout(self):return self.client.logout() if self.client is not None else None
        def __getattr__(self,name):return getattr(self.client,name)
    result=execute(r,auth,out,DeferredSDK(),request_bytes=request.read_bytes(),request_sha=a.expected_request_sha256)
    print(result['status'],flush=True);return 0 if result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
