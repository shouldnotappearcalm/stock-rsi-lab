"""Local source reconstruction; primary exit metadata remains evaluator-only."""
import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from scripts import asset_expansion_extension_sources as source
from scripts import capture_asset_expansion_raw_extension as capture
from scripts.fundamental_query_journal import digest
from scripts.inventory_asset_expansion_raw_horizon_v2 import sha,read,save,relative

START,END=source.START,source.END
RAW='asset-expansion-raw-extension-20261023'
ORIGINAL='asset-expansion-SH603056-delisting-original-20261023'
REVIEW='experiments/qlib/asset-expansion-2026-delisting-content-review.json'
PLAN='docs/research/asset-expansion-2026-source-reconstruction-plan-2026-10-23.md'
OUTPUT='asset-expansion-raw-reconstructed-20261023'
NEW_METHODS=('scripts/reconstruct_asset_expansion_raw_horizon.py',
    'tests/test_asset_expansion_source_reconstruction.py','src/stock_rsi/lifecycle_source_rows.py',
    'tests/test_lifecycle_source_rows.py')


def read_query(root,identity):
    key=digest(identity);folder=root/'queries'/key
    if read(folder/'request.json')!=identity:raise ValueError('full query identity differs')
    reserved=read(folder/'reserved-1.json');response=read(folder/'response-1.json')
    if (reserved['identity_sha256']!=key or reserved['attempt']!=1
            or response['identity_sha256']!=key or response['status']!='CAPTURED'
            or response['reservation_sha256']!=sha(folder/'reserved-1.json')
            or response['payload_sha256']!=digest(response['payload'])
            or sorted(p.name for p in folder.iterdir())!=['request.json','reserved-1.json','response-1.json']):
        raise ValueError('single reserved response/payload chain differs')
    a=datetime.fromisoformat(reserved['reserved_at_utc']);b=datetime.fromisoformat(response['payload']['captured_at_utc'])
    if a.tzinfo is None or b.tzinfo is None or a>b:raise ValueError('ordered aware source capture timestamps required')
    receipt={}
    for k,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
        receipt[k+'_file']=str((folder/name).relative_to(root));receipt[k+'_sha256']=sha(folder/name)
    return source.unwrap(response['payload']),receipt


def reconstruct_packet(code,original,sessions,data,lifecycle=None):
    if lifecycle is None:
        packet=source.assemble_packet(code,original,sessions,data)
        return packet,{'active_source_sessions':len(sessions),'active_end':sessions[-1],
            'global_session_count':len(sessions),'post_exit_sessions_not_synthesized':0}
    effective=lifecycle['effective_date']
    if (lifecycle['kind']!='DELISTING_END' or lifecycle['verified_primary_boundary'] is not True
            or not re.fullmatch('[0-9a-f]{64}',lifecycle['primary_document_sha256'])
            or source.day(effective) not in sessions or not original['window'][1]<effective<=END):
        raise ValueError('verified primary exit within fixed source horizon required')
    active=[d for d in sessions if d<effective]
    if not active or active[0]!=START:raise ValueError('explicit active source prefix required')
    source.validate_packet(original,code,[d for d in active if d<=original['window'][1]],original['window'])
    old_end=original['window'][1]
    bars=source.records(data['daily'],source.BAR_FIELDS)
    if any(not old_end<source.day(r['date'])<effective for r in bars):raise ValueError('unexpected post-exit/outside-tail bar')
    dividends=[]
    for r in source.records(data['dividend2026'],source.DIVIDEND_FIELDS):
        at=r['dividOperateDate']
        if not at or not source.day(at).startswith('2026') or at>=effective:
            raise ValueError('unresolved missing-date/year or post-exit distribution')
        dividends.append(r)
    old2026=[source.canonical(r,'distributions') for r in original['distributions'] if r['dividOperateDate'].startswith('2026')]
    fresh2026=[source.canonical(r,'distributions') for r in dividends if r['dividOperateDate']<=old_end]
    if old2026!=fresh2026:raise ValueError('annual original distribution prefix differs')
    adjustments=source.records(data['adjustments'],source.ADJUST_FIELDS)
    if any(not old_end<source.day(r['dividOperateDate'])<effective for r in adjustments):
        raise ValueError('unexpected post-exit/outside-tail adjustment')
    packet={'instrument':code,'window':[START,active[-1]],'bars':copy.deepcopy(original['bars'])+bars,
        'distributions':copy.deepcopy(original['distributions'])+[r for r in dividends if r['dividOperateDate']>old_end],
        'adjustments':copy.deepcopy(original['adjustments'])+adjustments,'quarantine':copy.deepcopy(original['quarantine'])}
    source.validate_packet(packet,code,active,packet['window'])
    if packet['quarantine'] or source.compare_packets(original,packet):raise ValueError('original prefix/quarantine unresolved')
    return packet,{'active_source_sessions':len(active),'active_end':active[-1],'global_session_count':len(sessions),
        'post_exit_sessions_not_synthesized':len(sessions)-len(active),'effective_date':effective,
        'primary_document_sha256':lifecycle['primary_document_sha256']}


def dependency_contract(repo,base):
    result={}
    def add(path,h=None):
        path=path.resolve()
        if path.is_relative_to(repo.resolve()):name='repo/'+str(path.relative_to(repo.resolve()))
        elif path.is_relative_to(base.resolve()):name='source/'+str(path.relative_to(base.resolve()))
        else:raise ValueError('input outside exact two roots')
        actual=sha(path)
        if h is not None and h!=actual:raise ValueError('original capture input changed')
        result[name]=actual
    original_inputs=read(base/RAW/'inputs-before.json')
    if len(original_inputs)!=272:raise ValueError('complete original source/method bindings required')
    for path,h in original_inputs.items():add(Path(path),h)
    files=[p for p in (base/RAW).rglob('*') if p.is_file()]
    if len(files)!=528:raise ValueError('all original complete/incomplete source evidence required')
    for p in files:add(p)
    for p in (base/ORIGINAL).rglob('*'):
        if p.is_file():add(p)
    for n in (REVIEW,PLAN,*NEW_METHODS):add(repo/n)
    add(base/'asset-expansion-SH603056-delisting-content-review-20261023.json')
    return result


def authenticate(path,expected,repo,base):
    if sha(path)!=expected:raise ValueError('frozen reconstruction request checksum differs')
    r=read(path)
    if (r['status']!='FROZEN_ALL47_RAW_RECONSTRUCTION_ONE_PRIMARY_EXIT' or r['window']!=[START,END]
            or r['network_query_budget']!=0 or r['output_directory']!=OUTPUT
            or r['strategy_changes_allowed'] is not False or r['portfolio_returns_to_compute'] is not False
            or r['bound_sha256']!=dependency_contract(repo,base)):
        raise ValueError('fixed complete source reconstruction protocol required')
    inputs={str(path.resolve()):expected}
    for name,h in r['bound_sha256'].items():
        kind,relative_name=name.split('/',1);root={'repo':repo,'source':base}[kind]
        p=relative(root,relative_name)
        if sha(p)!=h:raise ValueError('bound input changed')
        inputs[str(p)]=h
    raw=read(base/RAW/'manifest.json');ext=read(base/RAW/'request.json')
    if (raw['names']!=46 or sorted(raw['errors_sha256'])!=['SH603056'] or raw['pending_codes']
            or raw['query_reservations_consumed']!=142 or not raw['original_inputs_unchanged']
            or raw['original_exception'] is not None or raw['persistence_errors']
            or len(ext['codes'])!=47 or r['codes']!=ext['codes']):
        raise ValueError('unchanged complete142-query/one rejected issuer source state required')
    if (base/RAW/'request.json').read_bytes()!=(repo/'experiments/qlib/asset-expansion-2026-raw-extension-request.json').read_bytes():
        raise ValueError('original frozen source request differs')
    primary=read(repo/REVIEW);archive=read(base/ORIGINAL/'manifest.json');pdf=base/ORIGINAL/'SH603056-original.pdf'
    if (primary!=read(base/'asset-expansion-SH603056-delisting-content-review-20261023.json')
            or primary['instrument']!='SH603056' or primary['notice_number']!='2026-037'
            or primary['delisting_effective_date']!='2026-03-31'
            or primary['source_literal_exit_date_agrees_between_extractors'] is not True
            or primary['pypdf_pages_checked']!=[0,1] or primary['pdfminer_pages_checked']!=[0,1]
            or primary['pages']!=4 or not archive['capture_complete'] or archive['changed_inputs']
            or sha(pdf)!=primary['source_sha256'] or sha(pdf)!=archive['PDF_sha256']):
        raise ValueError('bound primary issuer/date/bytes content evidence required')
    proof={'kind':'DELISTING_END','effective_date':'2026-03-31','verified_primary_boundary':True,
        'primary_document_sha256':sha(pdf)}
    if r['lifecycle']!={'SH603056':proof}:raise ValueError('only authenticated evaluator exit permitted')
    return r,ext,raw,inputs


def execute(request,expected,repo,base,out):
    if out.exists():raise ValueError('fresh output required; no overwrite/resume')
    r,ext,raw,inputs=authenticate(request,expected,repo,base)
    if out.resolve()!=(base/OUTPUT).resolve():raise ValueError('fixed reconstruction output required')
    (out/'codes').mkdir(parents=True);(out/'coverage').mkdir()
    (out/'request.json').write_bytes(request.read_bytes());save(out/'inputs-before.json',inputs)
    progress={};coverage={};original=None;error=None;sessions=[];query_count=0
    try:
        dataset={};receipts={}
        if len(list((base/RAW/'queries').iterdir()))!=142:raise ValueError('exact142 original queries required')
        for q in ext['query_whitelist']:
            identity={'source':'BaoStock',**q,'asset_expansion_extension_request_sha256':raw['request_sha256']}
            key=(q['instrument'],q['component'])
            if key in dataset:raise ValueError('duplicate original source identity')
            dataset[key],receipts[key]=read_query(base/RAW,identity);query_count+=1
        if len(list((base/RAW).glob('login-reserved-*.json')))!=1:raise ValueError('one administrative login required')
        for n in ('login-response-1.json','logout-response.json'):
            if read(base/RAW/n)['error_code']!='0':raise ValueError('complete administrative response required')
        calendars={n:read(base/n/'calendar.json')['sessions'] for n in read(repo/capture.old.INVENTORY)['cache_manifests']}
        sessions=source.parse_calendar(dataset['CN_STOCK_CALENDAR','calendar'],calendars)
        if len(sessions)!=677:raise ValueError('fixed complete677 observed sessions required')
        save(out/'calendar.json',{'sessions':sessions,'source_calendar_sha256':sha(base/RAW/'calendar.json')})
        save(out/'lifecycles.json',r['lifecycle'])
        for code in r['codes']:
            route=ext['reuse_routes'][code];oldpath=base/route['cache']/'codes'/(code+'.json')
            if sha(oldpath)!=route['packet_sha256']:raise ValueError('original selected prefix differs')
            packet,coverage[code]=reconstruct_packet(code,read(oldpath),sessions,
                {k:dataset[code,k] for k in ('daily','dividend2026','adjustments')},r['lifecycle'].get(code))
            packet.update(source_query_receipts={k:receipts[code,k] for k in ('daily','dividend2026','adjustments')},
                original_packet_semantic_sha256=hashlib.sha256(json.dumps(read(oldpath),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                request_sha256=raw['request_sha256'])
            target=out/'codes'/(code+'.json')
            if code in raw['per_code_sha256']:
                origin=base/RAW/'codes'/(code+'.json')
                if sha(origin)!=raw['per_code_sha256'][code] or packet!=read(origin):raise ValueError('successful original packet does not equal source reconstruction')
                target.write_bytes(origin.read_bytes())
            else:save(target,packet)
            save(out/'coverage'/(code+'.json'),coverage[code]);progress[code]=sha(target)
            print('local reconstruction',len(progress),'/',len(r['codes']),code,coverage[code]['active_source_sessions'],flush=True)
    except BaseException as exc:original=exc;error={'error_type':type(exc).__name__,'error':str(exc)}
    changes=[]
    for name,h in inputs.items():
        try:
            if sha(Path(name))!=h:changes.append(name)
        except BaseException as exc:
            changes.append(name)
            if original is None:original=exc;error={'error_type':type(exc).__name__,'error':str(exc)}
    persistence=[];final_error=None
    def persist(name,value):
        nonlocal final_error
        try:save(out/name,value);return True
        except BaseException as exc:
            persistence.append({'file':name,'error_type':type(exc).__name__,'error':str(exc)})
            if final_error is None:final_error=exc
            return False
    persist('inputs-after.json',{'unchanged':not changes,'changed_or_missing':changes,'consumed_files':len(inputs)})
    result={'status':'ALL47_SOURCE_RECONSTRUCTION_PENDING_SEPARATE_QA','request_sha256':expected,'window':[START,END],
        'names':len(progress),'per_code_sha256':progress,'coverage':coverage,'verified_query_chains':query_count,
        'global_sessions':len(sessions),'pending_codes':sorted(set(r['codes'])-set(progress)),
        'original_error':error,'changed_inputs':changes,'persistence_errors':persistence,
        'reconstruction_complete':len(progress)==47 and error is None and not changes and not persistence,
        'original_46_packet_bytes_preserved':len(progress)==47,'synthetic_prices_created':0,'network_queries':0,
        'original_failed_capture_modified':False,'account_clearance_verified':False,'admitted_for_account_replay':False,
        'historical_observed_arrival_verified':False,'portfolio_returns_computed':False,'objective_achieved':False}
    if not result['reconstruction_complete']:result['status']='INCOMPLETE_RECONSTRUCTION_RETAINED'
    if not persist('manifest.json',result):
        result['reconstruction_complete']=False;result['status']='INCOMPLETE_RECONSTRUCTION_RETAINED'
        persist('finalization-error.json',result)
    if original is not None:raise original
    if final_error is not None:raise final_error
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv)
    result=execute(Path(a.request),a.expected_request_sha256,Path(__file__).resolve().parents[1],Path(a.source_root),Path(a.output_dir))
    print('local all47 reconstructed',result['reconstruction_complete'],'pending independent source QA',flush=True)
    return 0 if result['reconstruction_complete'] else 2


if __name__=='__main__':raise SystemExit(main())
