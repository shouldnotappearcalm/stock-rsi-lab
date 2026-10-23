"""Fresh date-quarantine experiment; frozen selective producer/checker reused."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from stock_rsi.tencent_window import prepare,verify_records
from scripts import decode_low_operating_tencent_pre2026 as legacy
from scripts import audit_low_operating_tencent_pre2026 as checker
from scripts.immutable_http_capture import need

sha,read,persist,tree,changed=legacy.sha,legacy.read,legacy.persist,legacy.tree,legacy.changed
START,END,CANDIDATE,OPAQUE,RAW=legacy.START,legacy.END,legacy.CANDIDATE,legacy.OPAQUE,legacy.RAW
OUTPUT='low-operating-tencent-window-pre2026-v1-20261023'
PREFIX='experiments/qlib/'
PROOF=PREFIX+'low-operating-tencent-decode-source-check.json'
PROOF_SHA='bba3fe8d6e8316510cafae4d66187e735f4659beb915ce1af3029132097d2190'
OLD_REQUEST=PREFIX+'low-operating-tencent-decode-request.json'
DESIGN='docs/research/low-operating-tencent-window-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-tencent-window.md'
REVIEW=PREFIX+'low-operating-tencent-window-review.json'
METHODS=('src/stock_rsi/tencent_window.py','scripts/run_low_operating_tencent_window_pre2026.py','tests/test_low_operating_tencent_window.py')


def context(base,root):
    need(sha(root/PROOF)==PROOF_SHA,'unchanged prior strict-window failure');p=read(root/PROOF)
    need(p['source_outcome_error_retained'] is True and p['control_rows']==p['target_rows']==0 and p['component_projection_complete'] is False,'prior empty failure preserved')
    required={('repo/'+OLD_REQUEST if k=='frozen_request' else k):h for k,h in p['all_input_sha256'].items()}
    required.update({'source/'+legacy.OUTPUT+'/'+n:h for n,h in p['all_capture_sha256'].items()});required['repo/'+PROOF]=PROOF_SHA
    paths={k:legacy.resolve(k,root,base) for k in required}
    for k,f in paths.items():need(not f.is_symlink() and sha(f)==required[k],'entire original failure/source graph '+k)
    sessions=json.loads(legacy.bound_body(base/RAW/'calendar.json',required['source/'+RAW+'/calendar.json']))['sessions']
    packet=json.loads(legacy.bound_body(base/RAW/'codes/SH600118.json',required['source/'+RAW+'/codes/SH600118.json']))
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END]
        and packet['instrument']=='SH600118' and packet['window']==[START,END] and [r['date'] for r in packet['bars']]==sessions,'same exact sessions/control')
    return sessions,packet['bars'],paths


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'exact frozen quarantine request');r=read(request)
    need(r['status']=='FROZEN_EARLIER_PREFIX_QUARANTINE_STRICT_TENCENT_SOURCE' and r['candidate']==CANDIDATE and r['window']==[START,END]
        and r['earlier_prefix_policy']=='DATE_HASH_ONLY_NO_VALUE_DECODE' and r['kept_policy']=='VERBATIM_ROWS_THEN_FROZEN_STRICT_PROJECTOR'
        and r['later_or_offcalendar_rows']=='REJECT' and r['volume_scale']==100 and r['amount_scale']==10000
        and r['network_or_account_or_returns_permitted'] is False and r['2026_quote_values_permitted'] is False,'fixed date-only source policy')
    sessions,original,paths=context(base,root)
    for p in (*METHODS,DESIGN,PLAN,REVIEW):paths['repo/'+p]=root/p
    need(set(paths)==set(r['input_sha256']) and set(r['method_sha256'])==set(METHODS),'exact complete window binding closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'window method/context '+k)
    need(all(r['method_sha256'][p]==r['input_sha256']['repo/'+p] for p in METHODS),'explicit current methods')
    return r,sessions,original,{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}


def experiment(control_body,target_loader,sessions,original,on_row=None,on_report=None,on_window=None,before_target=None,after_target_prepare=None):
    prepared,receipt=prepare(control_body,'SH600118',sessions)
    if on_window:on_window('SH600118',prepared,receipt)
    def target():
        b,r=prepare(target_loader(),'SZ002326',sessions)
        if on_window:on_window('SZ002326',b,r)
        if after_target_prepare:after_target_prepare()
        return b
    return legacy.evaluate(prepared,target,sessions,original,on_row,on_report,before_target)


def write_bytes(out,name,value,outputs):
    need(name not in outputs,'one prepared binary write');outputs[name]=hashlib.sha256(value).hexdigest()
    with (out/name).open('xb') as f:f.write(value);f.flush();os.fsync(f.fileno())
    need(sha(out/name)==outputs[name],'original prepared bytes persisted')


def run(base,root,request,expected):
    r,sessions,original,known=authenticate(base,root,request,expected);out=base/OUTPUT;need(not out.exists(),'fresh window experiment');out.mkdir();outputs={};stage='CONTROL';primary=None
    terminal={'status':'SELECTIVE_HISTORY_INCOMPLETE','candidate':CANDIDATE,'request_sha256':expected,'complete':False,
        'window_adapter':'EARLIER_PREFIX_DATE_QUARANTINE','control_price_volume_gate_passed':False,'target_decoder_invoked':False,
        'target_preparation_attempted':False,'control_rows_completed':0,'target_rows_completed':0,
        'physical_account_admitted':False,'historical_arrival_verified':False,'corporate_action_completeness_verified':False,
        'tax_treatment_admitted':False,'portfolio_return_computed':False,'2026_project_values_decoded':False,'objective_achieved':False}
    def save(name,value):persist(out,name,value,outputs)
    def current():need(not changed(known) and tree(out)==outputs,'entire context/output at target boundary')
    def window_done(code,b,receipt):save('window-'+code+'.json',receipt);write_bytes(out,'prepared-'+code+'.bin',b,outputs)
    def row_done(code,row):save('rows/'+code+'/'+row['date']+'.json',row);terminal['control_rows_completed' if code=='SH600118' else 'target_rows_completed']+=1
    def summary(report):save('control-summary.json',report);terminal['control_price_volume_gate_passed']=report['price_volume_gate_passed']
    def before_target():current();save('target-started.json',{'only_after_control_price_volume_gate':True});current()
    def load(code):
        p=base/OPAQUE/code/'body.bin';return legacy.bound_body(p,known[str(p.resolve())])
    def target():
        nonlocal stage
        stage='TARGET';terminal['target_preparation_attempted']=True;b=load('SZ002326');current();return b
    def numeric_target():current();terminal['target_decoder_invoked']=True
    def durable(name,h):
        try:return sha(out/name)==h
        except OSError:return False
    try:
        data=experiment(load('SH600118'),target,sessions,original,row_done,summary,window_done,before_target,numeric_target)
        save('control-rows.json',data['control_rows'])
        if terminal['target_decoder_invoked']:save('target-rows.json',data['target_rows'])
        missing=[d for d in sessions if d not in {v['date'] for v in data['target_rows']}]
        terminal.update(status='SELECTIVE_COMPONENT_PROJECTION_FINISHED_NOT_ACCOUNT_ADMITTED',target_missing_sessions=missing,
            complete=terminal['control_price_volume_gate_passed'] and not missing)
    except BaseException as exc:
        primary=exc
        try:
            for code,key in (('SH600118','control_rows_completed'),('SZ002326','target_rows_completed')):
                terminal[key]=sum(n.startswith('rows/'+code+'/') and durable(n,h) for n,h in outputs.items())
            if 'control-summary.json' in outputs and durable('control-summary.json',outputs['control-summary.json']):terminal['control_price_volume_gate_passed']=read(out/'control-summary.json')['price_volume_gate_passed']
            if hasattr(exc,'window_records'):
                code=exc.window_code;p=base/OPAQUE/code/'body.bin'
                save('window-partial-'+code+'.json',{'instrument':code,'records':exc.window_records,'failed_source_index':exc.window_failed_index,
                    'original_body_sha256':known[str(p.resolve())],'numeric_or_ignored_values_decoded':False})
        except BaseException as secondary:primary.add_note('partial evidence error: '+type(secondary).__name__)
        terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',error_type=type(primary).__name__,error=str(primary),failed_stage=stage,
            failed_row_index=terminal['control_rows_completed' if stage=='CONTROL' else 'target_rows_completed'])
    try:result=legacy.finish_source(out,terminal,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal error: '+type(exc).__name__)
    if primary is not None:raise primary
    return result


def verify_artifacts(out,sessions,original,terminal,raw_loader,pre_target=None):
    names=set();prepared={};counts={};partial={};error='error_type' in terminal
    for code in ('SH600118','SZ002326'):
        full=out/('window-'+code+'.json');binary=out/('prepared-'+code+'.bin');part=out/('window-partial-'+code+'.json')
        if code=='SZ002326' and any(p.exists() for p in (full,binary,part)):
            need(terminal['control_price_volume_gate_passed'] and terminal['target_preparation_attempted'],'target window only after control gate')
            if pre_target:pre_target()
        need(not(full.exists() and part.exists()),'one completed or partial preparation per resource')
        if full.exists():
            b,r=prepare(raw_loader(code),code,sessions);need(read(full)==r,'reconstructed exact window receipt');prepared[code]=b;names.add(full.name)
            counts[code]={'earlier':r['earlier_count'],'kept':r['kept_count']}
            if binary.exists():need(binary.read_bytes()==b,'prepared bytes exactly from kept source rows');names.add(binary.name)
            else:need(error,'successful projection requires persisted prepared bytes')
        else:need(not binary.exists(),'no prepared bytes without window receipt')
        if part.exists():
            p=read(part);b=raw_loader(code);need(error and p['instrument']==code and p['original_body_sha256']==hashlib.sha256(b).hexdigest()
                and p['failed_source_index']==len(p['records']) and p['numeric_or_ignored_values_decoded'] is False,'retained date-only prefix identity')
            verify_records(b,code,sessions,p['records'],False);partial[code]=len(p['records']);names.add(part.name)
    def component_body(code):
        if code in prepared:return prepared[code]
        need(error and terminal['control_rows_completed' if code=='SH600118' else 'target_rows_completed']==0,'no numeric rows without complete preparation')
        return raw_loader(code)  # The frozen checker returns immediately for a zero completed prefix.
    facts=checker.verify_projection_artifacts(out,sessions,original,terminal,component_body,pre_target)
    facts['names']|=names;facts.update(window_counts=counts,partial_window_records=partial)
    return facts


def audit(base,root,out,request,expected):
    r,sessions,original,known=authenticate(base,root,request,expected);before=tree(out);terminal=read(out/'terminal.json')
    need(terminal['request_sha256']==expected and terminal['window_adapter']=='EARLIER_PREFIX_DATE_QUARANTINE'
        and terminal['capture_sha256']=={k:h for k,h in before.items() if k!='terminal.json'} and terminal['all_inputs_unchanged'] is True
        and terminal['all_outputs_unchanged'] is True and not any(n.startswith('.') for n in before),'exact published immutable window evidence')
    def boundary():need(not changed(known) and tree(out)==before,'entire audit context before target preparation/projector')
    def raw(code):
        p=base/OPAQUE/code/'body.bin';return legacy.bound_body(p,known[str(p.resolve())])
    facts=verify_artifacts(out,sessions,original,terminal,raw,boundary);need(set(before)==facts['names'],'all window/row/marker/aggregate artifacts checked')
    for k in ('physical_account_admitted','historical_arrival_verified','corporate_action_completeness_verified','tax_treatment_admitted','portfolio_return_computed','2026_project_values_decoded','objective_achieved'):
        need(terminal[k] is False,'source components cannot admit physical account/goal')
    boundary()
    return {'status':'PASS_SHARED_WINDOW_BOUNDARY_SEPARATE_COMPONENT_PROJECTOR_NOT_ACCOUNT_ADMISSION','request_sha256':expected,
        'all_input_sha256':{**r['input_sha256'],'frozen_request':expected},'all_capture_sha256':before,'all_inputs_outputs_unchanged':True,
        'shared_window_selector_and_authentication':True,'separate_frozen_component_projector':True,'control':facts['control'],
        'control_rows':len(facts['control_rows']),'target_rows':len(facts['target_rows']),'window_counts':facts['window_counts'],
        'partial_window_records':facts['partial_window_records'],'source_outcome_error_retained':facts['error'],'component_projection_complete':facts['complete'],
        'full_source_or_account_admitted':False,'portfolio_return_computed':False,'2026_quote_values_decoded':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    p.add_argument('--audit-output');p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
    base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];request=Path(a.request).resolve()
    if a.preflight_only:authenticate(base,root,request,a.expected_request_sha256);print('window source preflight PASS; no new date/value scan');return 0
    if a.audit_output:
        dest=Path(a.audit_output);need(not dest.exists() and not dest.resolve().is_relative_to(base/OUTPUT),'fresh external window proof')
        try:result=audit(base,root,base/OUTPUT,request,a.expected_request_sha256)
        except BaseException as exc:
            legacy.write_once(dest,{'status':'FAILED_WINDOW_COMPONENT_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False});raise
        legacy.write_once(dest,result)
    else:result=run(base,root,request,a.expected_request_sha256)
    print(result['status'],flush=True);return 0 if a.audit_output or result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
