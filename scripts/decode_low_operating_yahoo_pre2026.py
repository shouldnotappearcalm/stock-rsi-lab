"""Frozen source-only Yahoo probe and shared-projector artifact reconstruction."""
import argparse,hashlib,json
from pathlib import Path
from stock_rsi.yahoo_history import decode
from stock_rsi.tencent_history import JsonSlices
from scripts import decode_low_operating_tencent_pre2026 as legacy
from scripts import audit_low_operating_tencent_pre2026 as comparator
from scripts.immutable_http_capture import need

sha,read,persist,tree,changed,bound_body=legacy.sha,legacy.read,legacy.persist,legacy.tree,legacy.changed,legacy.bound_body
START,END,CANDIDATE,RAW=legacy.START,legacy.END,legacy.CANDIDATE,legacy.RAW
OPAQUE='low-operating-yahoo-opaque-pre2026-v1-20261023';OUTPUT='low-operating-yahoo-decode-pre2026-v1-20261023'
PREFIX='experiments/qlib/';PROOF=PREFIX+'low-operating-yahoo-opaque-source-check.json'
PROOF_SHA='7a39ebadddcdf1e70a37e443ce07843487386399cf7035e0ae5ff404b183fccd'
OLD_REQUEST=PREFIX+'low-operating-yahoo-opaque-source-request.json'
METHODS=('src/stock_rsi/yahoo_history.py','scripts/decode_low_operating_yahoo_pre2026.py','tests/test_low_operating_yahoo_decode.py')
DESIGN='docs/research/low-operating-yahoo-decode-design-2026-10-23.md';PLAN='docs/superpowers/plans/2026-10-23-low-operating-yahoo-decode.md';REVIEW=PREFIX+'low-operating-yahoo-decode-review.json'

def context(base,root):
    need(sha(root/PROOF)==PROOF_SHA,'same original opaque acquisition proof')
    p=json.loads(bound_body(root/PROOF,PROOF_SHA));need(p['status']=='PASS_OPAQUE_CAPTURE_FULL_INPUT_OUTPUT_REHASH_NOT_SOURCE_ADMISSION'
        and p['raw_body_values_decoded'] is False and p['accepted_rows']==0,'original opaque acquisition only')
    required={('repo/'+OLD_REQUEST if k=='frozen_request' else k):h for k,h in p['all_input_sha256'].items()}
    required.update({'source/'+OPAQUE+'/'+n:h for n,h in p['all_capture_sha256'].items()});required['repo/'+PROOF]=sha(root/PROOF)
    paths={k:legacy.resolve(k,root,base) for k in required}
    for k,f in paths.items():need(not f.is_symlink() and sha(f)==required[k],'unchanged complete opaque graph '+k)
    sessions=json.loads(bound_body(base/RAW/'calendar.json',required['source/'+RAW+'/calendar.json']))['sessions']
    packet=json.loads(bound_body(base/RAW/'codes/SH600118.json',required['source/'+RAW+'/codes/SH600118.json']))
    need(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END]
        and packet['instrument']=='SH600118' and packet['window']==[START,END] and [r['date'] for r in packet['bars']]==sessions,'same explicit sessions/raw control')
    return sessions,packet['bars'],paths

def authenticate(base,root,request,expected):
    need(sha(request)==expected,'exact frozen Yahoo decode request');r=json.loads(bound_body(request,expected))
    need(r['status']=='FROZEN_SELECTIVE_PRE2026_YAHOO_COMPONENT_PROJECTION' and r['candidate']==CANDIDATE and r['window']==[START,END]
        and r['price_policy']=='EXACT_CENTS_OR_UNIQUE_NATIVE_F32_CELL_NO_GUARD' and r['volume_policy']=='EXACT_INTEGER_SHARES'
        and r['all_timestamps_before_quotes'] is True and r['shared_projector_audit'] is True
        and r['network_or_account_or_returns_permitted'] is False and r['2026_values_permitted'] is False,'fixed Yahoo component policy')
    sessions,original,paths=context(base,root)
    for p in (*METHODS,DESIGN,PLAN,REVIEW):paths['repo/'+p]=root/p
    need(set(paths)==set(r['input_sha256']) and set(r['method_sha256'])==set(METHODS),'exact Yahoo method/input closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'frozen Yahoo context '+k)
    need(all(r['method_sha256'][p]==r['input_sha256']['repo/'+p] for p in METHODS),'explicit Yahoo methods')
    return r,sessions,original,{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}

def evaluate(control_body,target_loader,sessions,original,on_row=None,on_report=None,before_target=None):
    def project(b,c):return decode(b,c,sessions,None if on_row is None else lambda r:on_row(c,r))
    controls=project(control_body,'SH600118');report=comparator.control(controls,original)
    if on_report:on_report(report)
    target=[]
    if report['price_volume_gate_passed']:
        if before_target:before_target()
        target=project(target_loader(),'SZ002326')
    return {'control':report,'control_rows':controls,'target_rows':target}

def run(base,root,request,expected):
    r,sessions,original,known=authenticate(base,root,request,expected);out=base/OUTPUT;need(not out.exists(),'fresh Yahoo projection');out.mkdir();outputs={};stage='CONTROL';primary=None
    terminal={'status':'SELECTIVE_HISTORY_INCOMPLETE','candidate':CANDIDATE,'request_sha256':expected,'complete':False,
        'control_price_volume_gate_passed':False,'target_decoder_invoked':False,'control_rows_completed':0,'target_rows_completed':0,
        'physical_account_admitted':False,'historical_arrival_verified':False,'corporate_action_completeness_verified':False,
        'tax_treatment_admitted':False,'portfolio_return_computed':False,'2026_values_decoded':False,'objective_achieved':False}
    def save(n,v):persist(out,n,v,outputs)
    def current():need(not changed(known) and tree(out)==outputs,'whole context and output before target')
    def load(c):
        p=base/OPAQUE/c/'body.bin';return bound_body(p,known[str(p.resolve())])
    def row(c,v):save('rows/'+c+'/'+v['date']+'.json',v);terminal['control_rows_completed' if c=='SH600118' else 'target_rows_completed']+=1
    def report(v):save('control-summary.json',v);terminal['control_price_volume_gate_passed']=v['price_volume_gate_passed']
    def before():current();save('target-started.json',{'only_after_control_price_volume_gate':True});current()
    def target():
        nonlocal stage
        stage='TARGET';v=load('SZ002326');current();terminal['target_decoder_invoked']=True;return v
    try:
        result=evaluate(load('SH600118'),target,sessions,original,row,report,before)
        save('control-rows.json',result['control_rows'])
        if terminal['target_decoder_invoked']:save('target-rows.json',result['target_rows'])
        missing=[d for d in sessions if d not in {r['date'] for r in result['target_rows']}]
        terminal.update(status='SELECTIVE_COMPONENT_PROJECTION_FINISHED_NOT_ACCOUNT_ADMITTED',target_missing_sessions=missing,
            complete=terminal['control_price_volume_gate_passed'] and not missing)
    except BaseException as exc:
        primary=exc
        try:
            for c,key in (('SH600118','control_rows_completed'),('SZ002326','target_rows_completed')):
                terminal[key]=sum(n.startswith('rows/'+c+'/') and (out/n).exists() and sha(out/n)==h for n,h in outputs.items())
            if 'control-summary.json' in outputs and sha(out/'control-summary.json')==outputs['control-summary.json']:
                terminal['control_price_volume_gate_passed']=read(out/'control-summary.json')['price_volume_gate_passed']
        except BaseException as secondary:primary.add_note('durable reconciliation error: '+type(secondary).__name__)
        terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',error_type=type(primary).__name__,error=str(primary),failed_stage=stage,
            failed_row_index=terminal['control_rows_completed' if stage=='CONTROL' else 'target_rows_completed'])
    try:result=legacy.finish_source(out,terminal,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal persistence error: '+type(exc).__name__)
    if primary is not None:raise primary
    return result

def verify_artifacts(out,sessions,original,terminal,loader,pre_target=None):
    error='error_type' in terminal;names={'terminal.json'};prefix={c:sorted((out/'rows'/c).glob('*.json')) for c in ('SH600118','SZ002326')}
    invoked=terminal['target_decoder_invoked'];marker=(out/'target-started.json').exists()
    need(type(invoked) is bool and all(type(terminal[k]) is int and terminal[k]>=0 for k in ('control_rows_completed','target_rows_completed')),'explicit invocation and durable counts')
    need(len(prefix['SZ002326'])==terminal['target_rows_completed'],'target inventory count before target load')
    allowed={'terminal.json','control-summary.json','control-rows.json','target-rows.json','target-started.json'}|set(terminal.get('rejected_terminal_sha256',{}))
    for code,paths in prefix.items():
        need(all(p.stem in sessions for p in paths),'only explicit historical durable row names')
        allowed.update('rows/'+code+'/'+p.name for p in paths)
    need({str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}<=allowed,'structural artifact closure before target')
    if not error:
        need((out/'control-rows.json').exists() and (not invoked or (out/'target-rows.json').exists()),'successful source requires durable aggregates before target')
    else:
        stage=terminal['failed_stage'];need(stage in ('CONTROL','TARGET','TERMINAL'),'reachable native failure stage')
        need(terminal['complete'] is False and terminal['status']=='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED'
            and type(terminal['error_type']) is str and type(terminal['error']) is str,'native failure identity before target')
        need(terminal['failed_row_index']==(None if stage=='TERMINAL' else terminal['control_rows_completed' if stage=='CONTROL' else 'target_rows_completed']),'native failure position before target')
        if stage=='CONTROL':need(not invoked and not prefix['SZ002326'] and not (out/'target-rows.json').exists(),'control failure precedes target invocation/evidence')
        if stage=='TARGET':need(marker,'target-stage failure requires preceding marker')
    report_exists=(out/'control-summary.json').exists();control=decode(loader('SH600118'),'SH600118',sessions,prefix_rows=None if report_exists else len(prefix['SH600118']))
    def check_rows(code,rows):
        need(len(prefix[code])==len(rows)==terminal['control_rows_completed' if code=='SH600118' else 'target_rows_completed'],'exact durable count '+code)
        for p,v in zip(prefix[code],rows):need(read(p)==v and p.stem==v['date'],'exact durable prefix '+code);names.add('rows/'+code+'/'+p.name)
    check_rows('SH600118',control);report=None;gate=False
    if report_exists:
        report=comparator.control(control,original);need(read(out/'control-summary.json')==report,'exact control comparison');gate=report['price_volume_gate_passed'];names.add('control-summary.json')
    need(terminal['control_price_volume_gate_passed']==gate,'exact control gate')
    if (out/'control-rows.json').exists():need(report_exists and read(out/'control-rows.json')==control,'exact control aggregate before target');names.add('control-rows.json')
    if marker:need(gate and read(out/'target-started.json')=={'only_after_control_price_volume_gate':True},'authorized target marker');names.add('target-started.json')
    target=[]
    if invoked:
        need(gate and marker,'target invocation after full verified control')
        if pre_target:pre_target()
        target=decode(loader('SZ002326'),'SZ002326',sessions,prefix_rows=len(prefix['SZ002326']) if error else None)
    check_rows('SZ002326',target)
    if (out/'target-rows.json').exists():
        need(invoked and read(out/'target-rows.json')==target,'exact target aggregate');names.add('target-rows.json')
        # Count timestamp slices, never finish numeric decoding after a failure.
        result=JsonSlices.items(JsonSlices(loader('SZ002326')).path(('chart','result')))
        need(len(result)==1 and len(target)==len(JsonSlices.items(JsonSlices(result[0]).path(('timestamp',)))),'complete target aggregate')
    complete=False
    if not error:
        missing=[d for d in sessions if d not in {v['date'] for v in target}];complete=gate and not missing
        need(report_exists and invoked==gate and 'control-rows.json' in names and (not invoked or 'target-rows.json' in names)
            and terminal['complete']==complete and terminal['target_missing_sessions']==missing
            and terminal['status']=='SELECTIVE_COMPONENT_PROJECTION_FINISHED_NOT_ACCOUNT_ADMITTED','exact completed source outcome')
    else:
        stage=terminal['failed_stage']
        for n,h in terminal.get('rejected_terminal_sha256',{}).items():
            need(stage=='TERMINAL' and n in ('terminal-rejected-published.json','terminal-rejected-staged.json') and sha(out/n)==h,'rejected publication retained');names.add(n)
    return {'control':report,'control_rows':control,'target_rows':target,'names':names,'error':error,'complete':complete}

def audit(base,root,out,request,expected):
    r,sessions,original,known=authenticate(base,root,request,expected);before=tree(out);terminal=read(out/'terminal.json')
    need(terminal['request_sha256']==expected and terminal['capture_sha256']=={k:h for k,h in before.items() if k!='terminal.json'}
        and terminal['all_inputs_unchanged'] is True and terminal['all_outputs_unchanged'] is True and not any(n.startswith('.') for n in before),'exact immutable source evidence')
    def boundary():need(not changed(known) and tree(out)==before,'whole context at audit target boundary')
    def load(c):
        p=base/OPAQUE/c/'body.bin';v=bound_body(p,known[str(p.resolve())]);boundary();return v
    facts=verify_artifacts(out,sessions,original,terminal,load,boundary);need(set(before)==facts['names'],'exact entire source artifact closure')
    for k in ('physical_account_admitted','historical_arrival_verified','corporate_action_completeness_verified','tax_treatment_admitted','portfolio_return_computed','2026_values_decoded','objective_achieved'):
        need(terminal[k] is False,'source-only no account/return admission')
    boundary()
    return {'status':'PASS_SHARED_YAHOO_PROJECTOR_ARTIFACT_RECONSTRUCTION_NOT_ACCOUNT_ADMISSION','request_sha256':expected,
        'all_input_sha256':{**r['input_sha256'],'frozen_request':expected},'all_capture_sha256':before,'all_inputs_outputs_unchanged':True,
        'shared_selective_projector':True,'separate_frozen_control_comparator':True,'control':facts['control'],'control_rows':len(facts['control_rows']),
        'target_rows':len(facts['target_rows']),'source_outcome_error_retained':facts['error'],'component_projection_complete':facts['complete'],
        'full_source_or_account_admitted':False,'portfolio_return_computed':False,'2026_values_decoded':False,'objective_achieved':False}

def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    p.add_argument('--audit-output');p.add_argument('--preflight-only',action='store_true');a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];request=Path(a.request).resolve()
    if a.preflight_only:authenticate(base,root,request,a.expected_request_sha256);print('preflight PASS; no Yahoo date/quote scan');return 0
    if a.audit_output:
        dest=Path(a.audit_output);need(not dest.exists() and not dest.resolve().is_relative_to(base/OUTPUT),'fresh external shared-projector proof')
        try:result=audit(base,root,base/OUTPUT,request,a.expected_request_sha256)
        except BaseException as exc:legacy.write_once(dest,{'status':'FAILED_YAHOO_COMPONENT_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False});raise
        legacy.write_once(dest,result)
    else:result=run(base,root,request,a.expected_request_sha256)
    print(result['status']);return 0 if a.audit_output or result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
