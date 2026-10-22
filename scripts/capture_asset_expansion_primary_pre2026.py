"""Two exact-day originals plus one authenticated existing PDF; no account ROI."""
import argparse
import json
from pathlib import Path
import time

from scripts.audit_cninfo_report_admission import CNINFO,query
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.capture_low_market_residual_vol_primary_pre2026 import select_implementation_notice,validate_listing
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

CASES=({'instrument':'SH600535','publication_day':'2025-03-20'},
       {'instrument':'SH600737','publication_day':'2025-08-05'})
OLD='low-market-residual-vol1m-primary-pre2026-20261021'
PROTOCOL='docs/research/asset-expansion-primary-and-raw-plan-2026-10-22.md'
METHOD_FILES=('scripts/capture_asset_expansion_primary_pre2026.py',
    'scripts/capture_low_market_residual_vol_primary_pre2026.py',
    'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py',
    'tests/test_asset_expansion_primary_capture.py')
PUBLIC_FILES=('experiments/qlib/asset-expansion-raw-source-audit.json',
    'experiments/qlib/asset-expansion-noncash-primary-observation.json')
LOCAL_FILES=('asset-expansion-raw-pre2026-20261022/manifest.json','cninfo-csi500-reports-20261017/plan.json',
    OLD+'/manifest.json',OLD+'/SH603688-2024-05-16.pdf')


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);root=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir);request=Path(a.request)
    if out.exists():raise ValueError('preserve original primary capture; no automatic retry')
    if sha256_file(request)!=a.expected_request_sha256:raise ValueError('frozen primary request changed')
    r=json.loads(request.read_text())
    if (r['status']!='FROZEN_ASSET_EXPANSION_TWO_EXACT_DAY_PRIMARY_NOTICES'
            or r['cases']!=list(CASES) or r['maximum_HTTP_reservations']!=6 or r['max_attempts_per_identity']!=1
            or r['protocol_file']!=PROTOCOL or sha256_file(root/PROTOCOL)!=r['protocol_sha256']
            or set(r['method_code_sha256'])!=set(METHOD_FILES) or set(r['public_inputs_sha256'])!=set(PUBLIC_FILES)
            or set(r['local_inputs_sha256'])!=set(LOCAL_FILES)):
        raise ValueError('fixed two-case pre2026 protocol required')
    bound={request:a.expected_request_sha256,root/PROTOCOL:r['protocol_sha256']}
    for field,directory in (('method_code_sha256',root),('public_inputs_sha256',root),('local_inputs_sha256',base)):
        for name,h in r[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('local relative input required')
            bound[directory/name]=h
    for path,h in bound.items():
        if sha256_file(path)!=h:raise ValueError('primary source input changed: '+str(path))
    original=json.loads((base/OLD/'manifest.json').read_text())['documents']['SH603688|2024-05-22']
    if sha256_file(base/OLD/original['file'])!=original['sha256']:raise ValueError('cached primary bytes changed')
    orgs=json.loads((base/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
    out.mkdir(parents=True);(out/'request.json').write_bytes(request.read_bytes());documents={};errors={}
    name=original['file'];(out/name).write_bytes((base/OLD/name).read_bytes())
    documents['SH603688']={'instrument':'SH603688','publication_day':'2024-05-16','file':name,
        'sha256':original['sha256'],'url':original['url'],'route':'BYTE_IDENTICAL_ORIGINAL_REUSE',
        'original_capture_manifest_sha256':r['local_inputs_sha256'][OLD+'/manifest.json']}
    atomic_json(out/'progress.json',documents);journal=QueryJournal(out,max_queries=6,max_attempts=1)
    for case in CASES:
        code,day=case['instrument'],case['publication_day'];listing_receipts=[];previous_total=None
        def fetch(url,payload):
            nonlocal previous_total
            data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':payload,
                'primary_request_sha256':a.expected_request_sha256},lambda:read_wire(url,payload))
            obj=json.loads(data);previous_total=validate_listing(obj,case,int(payload['pageNum']),previous_total)
            listing_receipts.append(receipt);time.sleep(.3);return obj
        try:
            rows=query(orgs[code],code[2:],'',day,day,max_pages=2,fetch=fetch)
            notice=select_implementation_notice(rows,case);url='https://static.cninfo.com.cn/'+notice['pdf_path']
            data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':url,'payload':None,
                'primary_request_sha256':a.expected_request_sha256},lambda:read_wire(url,None))
            file=code+'-'+day+'.pdf';(out/file).write_bytes(data)
            if not data.startswith(b'%PDF'):raise ValueError('original response is not PDF')
            documents[code]={**case,'file':file,'sha256':sha256_file(out/file),'url':url,'listing_row':notice,
                'HTTP_listing_receipts':listing_receipts,'HTTP_PDF_receipt':receipt,'route':'JOURNALED_PRIMARY_ORIGINAL'}
            atomic_json(out/'progress.json',documents);print('primary captured',code,day,flush=True)
        except Exception as exc:
            error={'error_type':type(exc).__name__,'error':str(exc),'case':case,'HTTP_listing_receipts':listing_receipts}
            write_packet_once(out/(code+'-error.json'),error);errors[code]=sha256_file(out/(code+'-error.json'))
            print('primary failure retained',code,type(exc).__name__,flush=True)
    changed=[str(path) for path,h in bound.items() if not path.is_file() or sha256_file(path)!=h]
    atomic_json(out/'manifest.json',{'status':'ASSET_EXPANSION_PRIMARY_BYTES_CAPTURED_REVIEW_SEPARATE',
        'request_sha256':a.expected_request_sha256,'documents':documents,'errors':errors,
        'pending_codes':sorted({'SH600535','SH600737','SH603688'}-set(documents)-set(errors)),
        'capture_complete':len(documents)==3 and not errors and not changed,'changed_original_inputs':changed,
        'HTTP_reservations_consumed':len(list(out.rglob('reserved-*.json'))),
        'documents_financially_reviewed':False,'capital_tax_verified':False,'raw_account_admitted':False,
        'new_2026_queries':False,'portfolio_return_computed':False,'objective_achieved':False})
    return 0 if len(documents)==3 and not errors and not changed else 2


if __name__=='__main__':raise SystemExit(main())
