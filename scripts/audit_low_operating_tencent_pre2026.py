"""Separate component projector/control check; shared byte-slice boundary disclosed."""
import argparse
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from stock_rsi.tencent_history import JsonSlices
from scripts.immutable_http_capture import need,file_sha as sha

START,END='2023-12-29','2025-12-31'
OPAQUE='low-operating-tencent-opaque-pre2026-v1-20261023'
RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
PREFIX='experiments/qlib/'
PROOF=PREFIX+'low-operating-tencent-opaque-source-check.json'
PROOF_SHA='a326865a8f0a02b092d06839d06565f31803f7f19b06c9875296cea696d4f701'
OLD_REQUEST=PREFIX+'low-operating-tencent-opaque-source-request.json'
METHODS=('src/stock_rsi/tencent_history.py','scripts/decode_low_operating_tencent_pre2026.py',
    'scripts/audit_low_operating_tencent_pre2026.py','tests/test_low_operating_tencent_decode.py')
PUBLIC=('docs/research/low-operating-tencent-decode-design-2026-10-23.md',
    'docs/superpowers/plans/2026-10-23-low-operating-tencent-decode.md',PREFIX+'low-operating-tencent-decode-review.json')
def read(p):return json.loads(Path(p).read_text())
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def resolve(k,root,base):
    if k=='runtime/curl':return Path('/usr/bin/curl')
    if k.startswith('repo/'):return root/k[5:]
    need(k.startswith('source/') and '..' not in Path(k).parts,'separate source namespace');return base/k[7:]
def scale(n,places):
    sign,digits,exponent=n.as_tuple();return Decimal((sign,digits,exponent+places))
def canonical(n):
    text=format(n,'f');return text.rstrip('0').rstrip('.') if '.' in text else text


def project(body,code,sessions,prefix_rows=None):
    if prefix_rows==0:return []  # Do not continue a row that the producer never completed.
    slices=JsonSlices(body);need(slices.path(('code',))==b'0','separate source success');result=[]
    tokens=JsonSlices.items(slices.path(('data',code.lower(),'day')));previous=None
    def number(token,optional=False):
        if optional and token in (b'null',b'""'):return None
        need(token[:1] not in (b'{',b'[') and token not in (b'true',b'false',b'null'),'separate scalar numeric token')
        literal=json.loads(token,parse_float=str,parse_int=str);need(type(literal) is str,'separate numeric text');n=Decimal(literal)
        need(n.is_finite(),'separate finite number');return n
    for index,row in enumerate(tokens):
        if prefix_rows is not None and index>=prefix_rows:break
        fields=JsonSlices.items(row);need(len(fields)==6 or len(fields)>=9,'separate six/extended schema')
        need(fields[0][:1]==b'"','separate date scalar first');at=json.loads(fields[0])
        need(date.fromisoformat(at).isoformat()==at and START<=at<=END and at in sessions and (previous is None or at>previous),'separate canonical ordered source date');previous=at
        o,c,h,l,v=[number(p) for p in fields[1:6]]
        need(all(x>0 and scale(x,2)==scale(x,2).to_integral_value() for x in (o,c,h,l)) and l<=min(o,c)<=max(o,c)<=h,'separate exact cent/range')
        shares=scale(v,2);need(v>=0 and shares==shares.to_integral_value(),'separate integer-share units')
        turnover=number(fields[7],True) if len(fields)>=9 else None;amount=number(fields[8],True) if len(fields)>=9 else None
        need((turnover is None or turnover>=0) and (amount is None or amount>=0),'separate optional activity')
        result.append({'date':at,'open':str(o),'close':str(c),'high':str(h),'low':str(l),'volume_lots':str(v),'volume_shares':canonical(shares),
            'turnover_percent':None if turnover is None else str(turnover),'amount_10k':None if amount is None else str(amount),
            'amount_cny':None if amount is None else canonical(scale(amount,4)),'source_kind':'HISTORICAL_UNADJUSTED_COMPONENTS_NOT_STATE_OR_ACCOUNT'})
    return result


def control(rows,original):
    dates=[v['date'] for v in rows];need(dates==sorted(set(dates)),'separate source uniqueness');lookup={v['date']:v for v in rows}
    trade=excluded=checked=matched=volume=amount_checked=amount_match=amount_missing=0;missing=[];bad=[];amount_bad=[]
    for raw in original:
        need(raw['tradestatus'] in ('0','1'),'separate explicit trading state')
        if raw['tradestatus']=='0':excluded+=1;continue
        trade+=1;at=raw['date']
        if at not in lookup:missing.append(at);continue
        row=lookup[at];fields=[]
        for field in ('open','close','high','low'):
            checked+=1
            if Decimal(row[field])==Decimal(raw[field]):matched+=1
            else:fields.append(field)
        if Decimal(row['volume_shares'])==Decimal(raw['volume']):volume+=1
        else:fields.append('volume_shares')
        if fields:bad.append({'date':at,'fields':fields})
        if row['amount_cny'] is None:amount_missing+=1
        else:
            amount_checked+=1
            if Decimal(row['amount_cny'])==Decimal(raw['amount']):amount_match+=1
            else:amount_bad.append({'date':at,'source_cny':row['amount_cny'],'original_cny':raw['amount']})
    gate=trade>0 and not missing and not bad and matched==checked==4*trade and volume==trade
    return {'raw_rows_counted':len(original),'trading_rows_checked':trade,'nontrading_rows_excluded':excluded,'returned_rows':len(rows),
        'missing_trading_dates':missing,'price_cells_checked':checked,'matched_price_cells':matched,'volume_rows_matched':volume,'mismatches':bad,
        'amount_rows_compared':amount_checked,'amount_exact_matches':amount_match,'amount_missing_rows':amount_missing,'amount_mismatches':amount_bad,
        'price_volume_gate_passed':gate,'all_components_exactly_corroborated':gate and amount_checked==amount_match==trade,'account_admitted':False}


def verify_projection_artifacts(out,sessions,original,terminal,body_loader,pre_target=None):
    """Verify actual durable prefixes, markers and aggregates even on native failure."""
    prefix={c:sorted((out/'rows'/c).glob('*.json')) for c in ('SH600118','SZ002326')}
    report_exists=(out/'control-summary.json').exists();error='error_type' in terminal;names={'terminal.json'}
    control_rows=project(body_loader('SH600118'),'SH600118',sessions,None if report_exists else len(prefix['SH600118']))
    for p,w in zip(prefix['SH600118'],control_rows):
        need(read(p)==w and p.stem==w['date'],'separate persisted control prefix');names.add('rows/SH600118/'+p.name)
    need(len(prefix['SH600118'])==len(control_rows)==terminal['control_rows_completed'],'separate full control count')
    gate=False;report=None
    if report_exists:
        report=control(control_rows,original);need(report==read(out/'control-summary.json'),'separate complete control comparison')
        gate=report['price_volume_gate_passed'];names.add('control-summary.json')
    need(terminal['control_price_volume_gate_passed']==gate,'separate exact gate')
    marker=(out/'target-started.json').exists();invoked=terminal['target_decoder_invoked'];target_rows=[];target_body=None
    if marker:
        need(gate and read(out/'target-started.json')=={'only_after_control_price_volume_gate':True},'separate authorized target marker');names.add('target-started.json')
    if invoked:
        need(gate and marker,'separate target invocation after control gate')
        if pre_target:pre_target()
        target_body=body_loader('SZ002326');target_rows=project(target_body,'SZ002326',sessions,len(prefix['SZ002326']) if error else None)
        for p,w in zip(prefix['SZ002326'],target_rows):
            need(read(p)==w and p.stem==w['date'],'separate target prefix');names.add('rows/SZ002326/'+p.name)
    need(len(prefix['SZ002326'])==len(target_rows)==terminal['target_rows_completed'],'separate target count')
    if (out/'control-rows.json').exists():
        need(report_exists and read(out/'control-rows.json')==control_rows,'separate durable control aggregate');names.add('control-rows.json')
    if (out/'target-rows.json').exists():
        need(invoked and read(out/'target-rows.json')==target_rows and len(target_rows)==len(JsonSlices.items(JsonSlices(target_body).path(('data','sz002326','day')))),
            'separate durable full target aggregate');names.add('target-rows.json')
    if not error:
        need(report_exists and invoked==gate and 'control-rows.json' in names and (not invoked or 'target-rows.json' in names),'separate all successful method stages')
        missing=[d for d in sessions if d not in {v['date'] for v in target_rows}];complete=gate and not missing
        need(terminal['target_missing_sessions']==missing and terminal['complete']==complete
            and terminal['status']=='SELECTIVE_COMPONENT_PROJECTION_FINISHED_NOT_ACCOUNT_ADMITTED','separate completed component outcome')
    else:
        complete=False;need(terminal['complete'] is False and terminal['status']=='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED'
            and type(terminal['error_type']) is str and type(terminal['error']) is str,'separate retained native failure')
        stage=terminal['failed_stage'];need(stage in ('CONTROL','TARGET','TERMINAL'),'separate failure stage')
        need(terminal['failed_row_index']==(None if stage=='TERMINAL' else terminal['control_rows_completed' if stage=='CONTROL' else 'target_rows_completed']),
            'separate reconciled completed prefix/failure position')
        archives=terminal.get('rejected_terminal_sha256',{})
        for name,h in archives.items():
            need(stage=='TERMINAL' and name in ('terminal-rejected-published.json','terminal-rejected-staged.json') and sha(out/name)==h,'separate rejected terminal retained')
            names.add(name)
    return {'control':report,'control_rows':control_rows,'target_rows':target_rows,'complete':complete,'error':error,'names':names}


def audit(base,root,out,request,expected):
    need(sha(request)==expected,'separate frozen decode request');r=read(request)
    need(r['status']=='FROZEN_SELECTIVE_PRE2026_TENCENT_COMPONENT_DECODE' and r['candidate']=='low_operating_profitability_followup_v1'
        and r['window']==[START,END] and r['volume_scale']==100 and r['amount_scale']==10000
        and r['amount_gate']=='SEPARATE_EXACT_UNADMITTED_DIAGNOSTIC' and r['selected_pre2026_day_only'] is True
        and r['network_or_account_or_returns_permitted'] is False and r['2026_project_values_permitted'] is False,'separate exact decode scope')
    need(sha(root/PROOF)==PROOF_SHA,'separate fixed opaque authority');prior=read(root/PROOF)
    required={('repo/'+OLD_REQUEST if k=='request' else 'runtime/curl' if k=='curl' else k):h for k,h in prior['all_input_sha256'].items()}
    required.update({'source/'+OPAQUE+'/'+n:h for n,h in prior['all_capture_sha256'].items()});required['repo/'+PROOF]=PROOF_SHA
    need(set(r['input_sha256'])==set(required)|{'repo/'+p for p in (*METHODS,*PUBLIC)} and all(r['input_sha256'][k]==h for k,h in required.items()),'separate entire original/method closure')
    need(set(r['method_sha256'])==set(METHODS) and all(r['method_sha256'][p]==r['input_sha256']['repo/'+p] for p in METHODS),'separate explicit methods')
    paths={k:resolve(k,root,base) for k in r['input_sha256']};paths['frozen_request']=request;want={**r['input_sha256'],'frozen_request':expected}
    for k,p in paths.items():need(not p.is_symlink() and sha(p)==want[k],'separate input before '+k)
    before=tree(out);terminal=read(out/'terminal.json');need(not any(n.startswith('.') for n in before),'no pending source terminal')
    need(terminal['request_sha256']==expected and terminal['capture_sha256']=={k:h for k,h in before.items() if k!='terminal.json'}
        and terminal['all_inputs_unchanged'] is True and terminal['all_outputs_unchanged'] is True,'separate exact output inventory')
    def bound(key):
        b=paths[key].read_bytes();need(hashlib.sha256(b).hexdigest()==want[key],'separate actual buffer '+key);return b
    sessions=json.loads(bound('source/'+RAW+'/calendar.json'))['sessions'];need(len(sessions)==486 and sessions==sorted(set(sessions))
        and [sessions[0],sessions[-1]]==[START,END],'separate exact sessions')
    original=json.loads(bound('source/'+RAW+'/codes/SH600118.json'))['bars'];need([v['date'] for v in original]==sessions,'separate original control calendar')
    def pre_target():
        for k,p in paths.items():need(sha(p)==want[k],'separate full context at target boundary '+k)
        need(tree(out)==before,'separate control evidence at target boundary')
    facts=verify_projection_artifacts(out,sessions,original,terminal,lambda c:bound('source/'+OPAQUE+'/'+c+'/body.bin'),pre_target)
    control_rows=facts['control_rows'];target_rows=facts['target_rows'];report=facts['control'];error=facts['error'];complete=facts['complete']
    need(set(before)==facts['names'],'separate exact artifact closure')
    for k in ('physical_account_admitted','historical_arrival_verified','corporate_action_completeness_verified','tax_treatment_admitted','portfolio_return_computed','2026_project_values_decoded','objective_achieved'):
        need(terminal[k] is False,'component projection cannot admit source/account/goal')
    for k,p in paths.items():need(sha(p)==want[k],'separate input after '+k)
    need(tree(out)==before,'separate outputs unchanged')
    return {'status':'PASS_SHARED_SELECTOR_SEPARATE_COMPONENT_PROJECTOR_NOT_ACCOUNT_ADMISSION','request_sha256':expected,
        'all_input_sha256':want,'all_capture_sha256':before,'shared_byte_slice_boundary':True,'new_producer_projector_or_comparator_imported':False,
        'source_outcome_error_retained':error,'control':report,'control_rows':len(control_rows),'target_rows':len(target_rows),'component_projection_complete':complete,
        'full_source_or_account_admitted':False,'portfolio_return_computed':False,'2026_project_values_decoded':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.output);raw=Path(a.raw_dir).resolve();need(not out.exists() and not out.resolve().is_relative_to(raw),'fresh external selective proof')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],raw,Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with out.open('x') as f:json.dump({'status':'FAILED_SELECTIVE_COMPONENT_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,indent=2)
        raise
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],'control rows',result['control_rows'],'target rows',result['target_rows'],'complete',result['component_projection_complete'],flush=True)


if __name__=='__main__':main()
