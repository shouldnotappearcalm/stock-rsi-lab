"""Fixed31-name raw capture:30 unchanged packets and one four-query source."""
import argparse,json,socket
from importlib.metadata import version
from pathlib import Path
from scripts.capture_budgeted_residual_raw_pre2026 import fetch_packet,load_reuse_packet
from scripts.capture_asset_expansion_raw_pre2026 import source_fingerprint
from scripts.capture_illiquidity_raw_development import read_vendor_response,calendar_diagnostic
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,source_code
from scripts.fundamental_query_journal import QueryJournal,write_packet_once
from scripts import inspect_cash_accrual_cfo_corpus as shared

OUTPUT='cash-accrual-raw-pre2026-v1-20261028'
METHODS=('scripts/capture_cash_accrual_raw_pre2026.py','scripts/capture_budgeted_residual_raw_pre2026.py',
         'scripts/capture_asset_expansion_raw_pre2026.py','scripts/capture_illiquidity_raw_development.py',
         'scripts/capture_low_risk_raw_account_data.py','scripts/capture_cninfo_csi500_reports_pre2026.py',
         'scripts/capture_frozen_target_development_data.py','scripts/fundamental_query_journal.py','tests/test_cash_accrual_raw_capture.py')
PROFILE={'status':'FROZEN_CASH_ACCRUAL_RAW_SOURCE_CAPTURE','output_subdir':OUTPUT,'window':['2023-12-29','2025-12-31'],
         'names':31,'fresh_codes':['SH600129'],'maximum_new_query_reservations':4,'max_attempts_per_identity':1,
         'administrative_login_budget':1,'socket_timeout_seconds':20,'baostock_version':'0.9.4',
         'portfolio_or_2026_computation_permitted':False}

def validate(req):
    shared.need(all(type(req.get(k)) is type(v) and req[k]==v for k,v in PROFILE.items()),'fixed31source/onefresh/fourquery budget')
    inv=req['inventory'];shared.need(len(inv['codes'])==len(set(inv['codes']))==31 and inv['fresh_codes']==['SH600129']
        and not inv['source_conflicts'] and set(inv['reuse_routes'])==set(inv['codes'])-{'SH600129'},'complete unchanged primary target source routing')

def capture(req,known,base,request_sha,*,sdk=None,fetcher=fetch_packet):
    validate(req);out=base/OUTPUT;shared.need(not out.exists() and not shared.changed(known),'fresh unchanged raw capture');out.mkdir();outputs={};progress={};error=None;service=sdk
    terminal={'status':'CASH_ACCRUAL_RAW_SOURCE_INCOMPLETE','complete':False,'request_sha256':request_sha,
              'portfolio_return_computed':False,'2026_values_read':False,'source_admitted_for_replay':False,'objective_achieved':False}
    def save(n,v):shared.persist(out,n,v,outputs)
    try:
        save('calendar.json',{'sessions':req['inventory']['sessions']});(out/'codes').mkdir()
        for c,route in req['inventory']['reuse_routes'].items():
            p=base/route['directory']/'codes'/(c+'.json');packet,diag=load_reuse_packet(p,c,route['packet_sha256'],req['inventory']['sessions'])
            shared.need(source_fingerprint(packet)==route['fingerprint'] and diag['full_explicit_calendar_covered'],'identical complete reuse source')
            (out/'codes'/(c+'.json')).write_bytes(p.read_bytes());progress[c]=shared.sha(out/'codes'/(c+'.json'))
        save('progress.json',progress)
        socket.setdefaulttimeout(20)
        if service is None:
            import baostock as service
        write_packet_once(out/'login-reserved.json',{'attempt':1,'request_sha256':request_sha})
        response=service.login();write_packet_once(out/'login-response.json',{'error_code':response.error_code,'error_msg':response.error_msg})
        shared.need(response.error_code=='0','public data login succeeded')
        journal=QueryJournal(out,max_queries=4,max_attempts=1)
        for code in req['fresh_codes']:
            symbol=source_code(code)
            def fetch(component,parameters):
                if component=='daily':result=service.query_history_k_data_plus(symbol,','.join(BAR_FIELDS),**parameters)
                elif component.startswith('dividend'):result=service.query_dividend_data(symbol,**parameters)
                else:result=service.query_adjust_factor(symbol,**parameters)
                return read_vendor_response(result)
            packet=fetcher(journal,code,request_sha,fetch)
            shared.need(calendar_diagnostic(packet['bars'],req['inventory']['sessions'])['full_explicit_calendar_covered'],'fresh source requires complete explicit calendar')
            source_fingerprint(packet);write_packet_once(out/'codes'/(code+'.json'),packet);progress[code]=shared.sha(out/'codes'/(code+'.json'))
        shared.need(set(progress)==set(req['inventory']['codes']),'all31source packets required')
        save('progress-final.json',progress)
        save('manifest.json',{'status':'CASH_ACCRUAL_RAW_PACKETS_CAPTURED_NOT_ACCOUNT_ADMITTED','window':req['window'],'names':31,
                             'target_sha256':req['inventory']['target_sha256'],'calendar_sha256':shared.sha(out/'calendar.json'),
                             'per_code_sha256':progress,'historical_arrival_verified':False,'source_admitted_for_replay':False})
        terminal.update(status='CASH_ACCRUAL_RAW_SOURCE_CAPTURE_COMPLETE_NOT_ADMITTED',complete=True)
    except BaseException as exc:
        error=exc;terminal.update(error_type=type(exc).__name__,error=str(exc),completed_codes=sorted(progress),failed_stage='RAW_CAPTURE')
    finally:
        if service is not None:
            try:
                response=service.logout();write_packet_once(out/'logout-response.json',{'cleanup_called':True,'error_code':getattr(response,'error_code',None),'error_msg':getattr(response,'error_msg',None)})
            except BaseException as exc:
                if error is None:error=exc;terminal.update(complete=False,error_type=type(exc).__name__,error=str(exc))
        try:
            for code,h in progress.items():
                load_reuse_packet(out/'codes'/(code+'.json'),code,h,req['inventory']['sessions'])
        except BaseException as exc:
            if error is None:error=exc;terminal.update(complete=False,error_type=type(exc).__name__,error=str(exc),failed_stage='RAW_INTEGRITY')
        outputs=shared.tree(out)
        try:value=shared.legacy.finish_source(out,terminal,known,outputs)
        except BaseException as exc:
            if error is None:error=exc
            else:error.add_note('finalization failure: '+type(exc).__name__)
    if error is not None:raise error
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args();base=Path(a.source_root).resolve();root=Path(__file__).resolve().parents[1];request=Path(a.request).resolve()
    req=shared.read_bound(request,a.expected_request_sha256);validate(req);shared.need(version('baostock')==req['baostock_version'],'installed frozen SDK')
    shared.need(set(req['method_sha256'])==set(METHODS) and all(shared.sha(root/n)==h for n,h in req['method_sha256'].items()),'frozen capture methods')
    known=dict(req['input_sha256']);known[str(request)]=a.expected_request_sha256;shared.need(not shared.changed(known),'entire frozen raw input closure')
    print(capture(req,known,base,a.expected_request_sha256)['status'])
if __name__=='__main__':main()
