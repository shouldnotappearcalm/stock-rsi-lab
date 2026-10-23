"""Frozen selective historical decode, control first and no new transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from stock_rsi.tencent_history import decode,compare
from scripts.recover_low_operating_quotes_pre2026 import persist,changed,tree,sha
from scripts.immutable_http_capture import need,write_once

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
OPAQUE='low-operating-tencent-opaque-pre2026-v1-20261023'
RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
OUTPUT='low-operating-tencent-decode-pre2026-v1-20261023'
PREFIX='experiments/qlib/'
PROOF=PREFIX+'low-operating-tencent-opaque-source-check.json'
PROOF_SHA='a326865a8f0a02b092d06839d06565f31803f7f19b06c9875296cea696d4f701'
OLD_REQUEST=PREFIX+'low-operating-tencent-opaque-source-request.json'
DESIGN='docs/research/low-operating-tencent-decode-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-tencent-decode.md'
REVIEW=PREFIX+'low-operating-tencent-decode-review.json'
METHODS=('src/stock_rsi/tencent_history.py','scripts/decode_low_operating_tencent_pre2026.py',
    'scripts/audit_low_operating_tencent_pre2026.py','tests/test_low_operating_tencent_decode.py')

def read(p):return json.loads(Path(p).read_text())
def resolve(k,root,base):
    if k=='runtime/curl':return Path('/usr/bin/curl')
    if k.startswith('repo/'):return root/k[5:]
    need(k.startswith('source/') and '..' not in Path(k).parts,'known source namespace');return base/k[7:]


def bound_body(path,expected):
    need(not path.is_symlink(),'regular bound body');b=path.read_bytes()
    need(hashlib.sha256(b).hexdigest()==expected,'actual authenticated source buffer');need(len(b)<=1048576,'body byte limit');return b


def evaluate(control_body,target_loader,sessions,original,on_row=None,on_control=None,before_target=None):
    rows=decode(control_body,'SH600118',sessions,None if on_row is None else lambda r:on_row('SH600118',r));report=compare(rows,original)
    if on_control:on_control(report)
    target=[]
    if report['price_volume_gate_passed']:
        if before_target:before_target()
        target=decode(target_loader(),'SZ002326',sessions,None if on_row is None else lambda r:on_row('SZ002326',r))
    return {'control_rows':rows,'control':report,'target_rows':target}


def context(base,root):
    need(sha(root/PROOF)==PROOF_SHA,'fixed opaque source proof');p=read(root/PROOF);need(p['accepted_bar_rows']==0 and p['response_body_values_decoded'] is False,'unchanged unadmitted opaque stage')
    required={('repo/'+OLD_REQUEST if k=='request' else 'runtime/curl' if k=='curl' else k):h for k,h in p['all_input_sha256'].items()}
    required.update({'source/'+OPAQUE+'/'+name:h for name,h in p['all_capture_sha256'].items()});required['repo/'+PROOF]=PROOF_SHA
    paths={k:resolve(k,root,base) for k in required}
    for k,path in paths.items():need(not path.is_symlink() and sha(path)==required[k],'entire retained source context '+k)
    calendar=base/RAW/'calendar.json';sessions=json.loads(bound_body(calendar,required['source/'+RAW+'/calendar.json']))['sessions']
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'exact486source sessions')
    control=base/RAW/'codes/SH600118.json';packet=json.loads(bound_body(control,required['source/'+RAW+'/codes/SH600118.json']))
    need(packet['instrument']=='SH600118' and packet['window']==[START,END] and [v['date'] for v in packet['bars']]==sessions,'same full original control')
    return sessions,packet['bars'],paths


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'exact frozen selective request');r=read(request)
    need(r['status']=='FROZEN_SELECTIVE_PRE2026_TENCENT_COMPONENT_DECODE' and r['candidate']==CANDIDATE and r['window']==[START,END]
        and r['volume_scale']==100 and r['amount_scale']==10000 and r['amount_gate']=='SEPARATE_EXACT_UNADMITTED_DIAGNOSTIC'
        and r['selected_pre2026_day_only'] is True and r['network_or_account_or_returns_permitted'] is False and r['2026_project_values_permitted'] is False,'fixed source-only selective rules')
    sessions,original,paths=context(base,root)
    for name in (*METHODS,DESIGN,PLAN,REVIEW):paths['repo/'+name]=root/name
    need(set(paths)==set(r['input_sha256']) and set(r['method_sha256'])==set(METHODS),'full selective binding closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'unchanged selective input '+k)
    need(all(r['method_sha256'][p]==r['input_sha256']['repo/'+p] for p in METHODS),'exact method binding')
    return r,sessions,original,{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}


def finish_source(out,state,known,outputs):
    """Verify intended terminal bytes and all evidence after its atomic publication."""
    expected=dict(outputs)
    terminal={**state,'capture_sha256':expected,'all_inputs_unchanged':not changed(known),'all_outputs_unchanged':tree(out)==expected}
    try:
        need(terminal['all_inputs_unchanged'] and terminal['all_outputs_unchanged'],'source context before terminal persistence')
        encoded=(json.dumps(terminal,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode();terminal_sha=hashlib.sha256(encoded).hexdigest()
        pending=out/'.terminal-pending.json';write_once(pending,terminal)
        need(not changed(known) and tree(out)=={**expected,'.terminal-pending.json':terminal_sha},'source context during terminal persistence')
        os.replace(pending,out/'terminal.json')
        need(not changed(known) and tree(out)=={**expected,'terminal.json':terminal_sha},'source context after terminal publication')
        return terminal
    except BaseException as primary:
        archives={}
        try:
            for source,name in ((out/'terminal.json','terminal-rejected-published.json'),(out/'.terminal-pending.json','terminal-rejected-staged.json')):
                if source.exists():
                    os.replace(source,out/name);archives[name]=sha(out/name)
            current=tree(out);data={k:h for k,h in current.items() if k not in archives}
            failure={**state,'status':'SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED','complete':False,
                'capture_sha256':{**expected,**archives},'rejected_terminal_sha256':archives,
                'all_inputs_unchanged':not changed(known),'all_outputs_unchanged':data==expected,
                'error_type':type(primary).__name__,'error':str(primary),'failed_stage':'TERMINAL','failed_row_index':None}
            if 'error_type' in state:failure['prior_failure']={k:state[k] for k in ('error_type','error','failed_stage','failed_row_index')}
            write_once(out/'.terminal-failure-pending.json',failure);os.replace(out/'.terminal-failure-pending.json',out/'terminal.json')
        except BaseException as secondary:primary.add_note('failure receipt persistence error: '+type(secondary).__name__)
        raise primary


def run(base,root,request,expected):
    r,sessions,original,known=authenticate(base,root,request,expected);out=base/OUTPUT;need(not out.exists(),'fresh selective output');out.mkdir();outputs={};primary=None;stage='CONTROL'
    terminal={'status':'SELECTIVE_HISTORY_INCOMPLETE','candidate':CANDIDATE,'request_sha256':expected,'complete':False,
        'control_price_volume_gate_passed':False,'target_decoder_invoked':False,'control_rows_completed':0,'target_rows_completed':0,
        'physical_account_admitted':False,'historical_arrival_verified':False,'corporate_action_completeness_verified':False,
        'tax_treatment_admitted':False,'portfolio_return_computed':False,'2026_project_values_decoded':False,'objective_achieved':False}
    def save(name,value):persist(out,name,value,outputs)
    def row_done(code,row):
        save('rows/'+code+'/'+row['date']+'.json',row);terminal['control_rows_completed' if code=='SH600118' else 'target_rows_completed']+=1
    def summary(report):save('control-summary.json',report);terminal['control_price_volume_gate_passed']=report['price_volume_gate_passed']
    def require_current():need(not changed(known) and tree(out)==outputs,'complete context/control evidence before target decode')
    def boundary():
        require_current()
        save('target-started.json',{'only_after_control_price_volume_gate':True})
        require_current()
    def load(code):
        path=base/OPAQUE/code/'body.bin';return bound_body(path,known[str(path.resolve())])
    def target():
        nonlocal stage
        stage='TARGET';body=load('SZ002326');require_current();terminal['target_decoder_invoked']=True;return body
    try:
        data=evaluate(load('SH600118'),target,sessions,original,row_done,summary,boundary)
        save('control-rows.json',data['control_rows'])
        if terminal['target_decoder_invoked']:save('target-rows.json',data['target_rows'])
        target_days={r['date'] for r in data['target_rows']};terminal.update(target_missing_sessions=[d for d in sessions if d not in target_days],
            complete=terminal['control_price_volume_gate_passed'] and len(target_days)==len(sessions),
            status='SELECTIVE_COMPONENT_PROJECTION_FINISHED_NOT_ACCOUNT_ADMITTED')
    except BaseException as exc:
        for code,key in (('SH600118','control_rows_completed'),('SZ002326','target_rows_completed')):
            terminal[key]=sum(name.startswith('rows/'+code+'/') and (out/name).is_file() and sha(out/name)==h for name,h in outputs.items())
        report=out/'control-summary.json'
        if 'control-summary.json' in outputs and report.is_file() and sha(report)==outputs['control-summary.json']:
            terminal['control_price_volume_gate_passed']=read(report)['price_volume_gate_passed']
        primary=exc;terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',error_type=type(exc).__name__,error=str(exc),
            failed_stage=stage,failed_row_index=terminal['control_rows_completed' if stage=='CONTROL' else 'target_rows_completed'])
    try:result=finish_source(out,terminal,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal error: '+type(exc).__name__)
    if primary is not None:raise primary
    return result


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];request=Path(a.request).resolve()
    if a.preflight_only:authenticate(base,root,request,a.expected_request_sha256);print('selective source preflight PASS; no body-value decode');return 0
    result=run(base,root,request,a.expected_request_sha256);print(result['status'],'control gate',result['control_price_volume_gate_passed'],'target rows',result['target_rows_completed'],flush=True)
    return 0 if result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
