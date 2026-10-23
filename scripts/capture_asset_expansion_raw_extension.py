"""Authenticate all47 frozen raw prefixes, then capture bounded SDK responses."""
import argparse
import socket
from importlib.metadata import version
from pathlib import Path

from scripts import inventory_asset_expansion_raw_horizon_v2 as old
from scripts.asset_expansion_extension_sources import capture_extension,query_parameters

PLAN='docs/research/asset-expansion-2026-raw-extension-plan-2026-10-23.md'
PRIOR='experiments/qlib/asset-expansion-2026-raw-overlap-request-v2.json'
OVERLAP='experiments/qlib/asset-expansion-2026-raw-overlap-results-v2.json'
OUTPUT='asset-expansion-raw-extension-20261023'
METHODS=old.METHODS+('scripts/asset_expansion_extension_sources.py',
    'scripts/capture_asset_expansion_raw_extension.py','scripts/fundamental_query_journal.py',
    'tests/test_asset_expansion_raw_extension.py')


def authenticate_request(path,expected,repo,base):
    if old.sha(path)!=expected:raise ValueError('frozen source-extension request checksum changed')
    r=old.read(path)
    if (r['status']!='FROZEN_ASSET_EXPANSION_ALL47_OCT21_RAW_EXTENSION'
            or r['window']!=[old.START,old.END] or r['observation_cutoff']!='2026-10-21T15:05:00+08:00'
            or r['maximum_source_reservations']!=142 or r['max_attempts_per_query']!=1
            or r['maximum_administrative_login_attempts']!=1 or r['socket_timeout_seconds']!=20
            or r['maximum_consecutive_failed_codes']!=3 or r['output_directory']!=OUTPUT
            or r['strategy_changes_allowed'] is not False or r['portfolio_returns_to_compute'] is not False
            or set(r['method_sha256'])!=set(METHODS)):
        raise ValueError('fixed source scope, methods and bounded budget required')
    prior=old.read(repo/PRIOR)
    wanted_public=set(prior['public_evidence_sha256'])|{PRIOR,OVERLAP,PLAN}
    if (set(r['public_evidence_sha256'])!=wanted_public
            or r['local_source_sha256']!=prior['local_source_sha256']):
        raise ValueError('all prior original sources and evidence required')
    inputs={str(Path(path).resolve()):expected}
    for field,root in (('method_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for name,h in r[field].items():
            p=old.relative(root,name)
            if old.sha(p)!=h:raise ValueError('frozen source, evidence or method changed: '+name)
            inputs[str(p)]=h
    old.authenticate(repo/PRIOR,r['public_evidence_sha256'][PRIOR],repo,base)
    result=old.read(repo/OVERLAP);summary=old.read(repo/old.SUMMARY)
    codes=summary['primary_target_union']
    if (len(codes)!=47 or r['codes']!=codes or sorted(result['items'])!=codes
            or result['unresolved_codes'] or result['calendar_errors'] or not result['input_postcheck']['all_inputs_unchanged']
            or len(result['completed_codes'])!=47 or result['pending_codes'] or result['original_error'] is not None
            or r['reuse_routes']!={c:i['route'] for c,i in result['items'].items()}):
        raise ValueError('same audited all47-name routes required')
    originals={};calendars={}
    for name in old.read(repo/old.INVENTORY)['cache_manifests']:
        calendars[name]=old.read(base/name/'calendar.json')['sessions']
    for code,item in result['items'].items():
        route=item['route']
        if item['errors'] or item['conflicts'] or item['unresolved_quarantine'] or route is None:
            raise ValueError('original route remains unresolved')
        p=base/route['cache']/'codes'/(code+'.json')
        if old.sha(p)!=route['packet_sha256']:raise ValueError('original selected packet changed')
        original=old.read(p);old.validate_packet(original,code,calendars[route['cache']],route['window'])
        originals[code]=original
    if r['query_whitelist']!=[{'instrument':c,'component':k,'parameters':p}
            for (c,k),p in query_parameters(originals).items()]:
        raise ValueError('exact calendar and three per-issuer queries required')
    if r['baostock_version']!=version('baostock'):raise ValueError('frozen provider SDK version changed')
    return r,originals,calendars,inputs


class SourceSession:
    def __init__(self,out,request_sha,sdk,allowed):
        self.out,self.request_sha,self.sdk,self.allowed=out,request_sha,sdk,allowed
        self.attempted=False;self.error=None

    def __call__(self,code,component,parameters):
        if (code,component) not in self.allowed or parameters!=self.allowed[code,component]:
            raise ValueError('request outside fixed SDK query whitelist')
        if self.error is not None:raise RuntimeError('administrative login failed; no retry')
        if not self.attempted:
            self.attempted=True
            old.save(self.out/'login-reserved-1.json',{'attempt':1,'request_sha256':self.request_sha})
            record={}
            try:
                login=self.sdk.login();record={'error_code':login.error_code,'error_msg':login.error_msg}
                if login.error_code!='0':raise RuntimeError('provider administrative login failed')
            except BaseException as exc:
                self.error=type(exc).__name__
                old.save(self.out/'login-response-1.json',{**record,'error_type':type(exc).__name__,'error':str(exc)})
                raise
            old.save(self.out/'login-response-1.json',record)
        if component=='calendar':response=self.sdk.query_trade_dates(**parameters)
        else:
            symbol=old.issuer(code)
            if component=='daily':response=self.sdk.query_history_k_data_plus(symbol,','.join(old.BAR_FIELDS),**parameters)
            elif component=='dividend2026':response=self.sdk.query_dividend_data(symbol,**parameters)
            elif component=='adjustments':response=self.sdk.query_adjust_factor(symbol,**parameters)
            else:raise ValueError('unsupported fixed source component')
        record={'initial_error_code':response.error_code,'initial_error_msg':response.error_msg,
            'fields':None if response.fields is None else list(response.fields),'rows':[],
            'iteration_error_type':None,'iteration_error':None}
        if response.error_code=='0':
            try:
                while response.next():record['rows'].append(response.get_row_data())
            except BaseException as exc:record.update(iteration_error_type=type(exc).__name__,iteration_error=str(exc))
        record.update(final_error_code=response.error_code,final_error_msg=response.error_msg)
        return ['provider_response'],[record]

    def close(self):
        if self.attempted:
            try:
                r=self.sdk.logout();record={'error_code':getattr(r,'error_code',None),'error_msg':getattr(r,'error_msg',None)}
            except BaseException as exc:record={'error_type':type(exc).__name__,'error':str(exc)}
            old.save(self.out/'logout-response.json',record)



def close_source(source,out,original_exception):
    try:source.close()
    except BaseException as exc:
        record={'error_type':type(exc).__name__,'error':str(exc),
            'original_exception_type':type(original_exception).__name__ if original_exception else None,
            'original_exception':str(original_exception) if original_exception else None}
        try:old.save(out/'administrative-finalization-error.json',record)
        except BaseException as persistence_error:
            print('administrative finalization error',record,'secondary persistence error',str(persistence_error),flush=True)
        if original_exception is None:raise
    if original_exception is not None:raise original_exception


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+name,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve original capture; no overwrite or automatic resume')
    r,originals,calendars,inputs=authenticate_request(Path(a.request),a.expected_request_sha256,repo,base)
    if out.resolve()!=(base/OUTPUT).resolve():raise ValueError('fixed source output directory required')
    import baostock as bs
    socket.setdefaulttimeout(20)
    source=SourceSession(out,a.expected_request_sha256,bs,query_parameters(originals))
    original_exception=None
    try:manifest=capture_extension(out,originals,calendars,source,request_bytes=Path(a.request).read_bytes(),inputs=inputs)
    except BaseException as exc:original_exception=exc
    close_source(source,out,original_exception)
    print('all47 source capture',manifest['names'],'/',manifest['requested_names'],'complete',manifest['capture_complete'],
        'queries',manifest['query_reservations_consumed'],'pending separate QA',flush=True)
    return 0 if manifest['capture_complete'] else 2


if __name__=='__main__':raise SystemExit(main())
