"""One separately registered retry of a terminal SSL-failed original download."""
import argparse
import json
from pathlib import Path
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes,read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from scripts.fundamental_query_journal import QueryJournal,write_packet_once

PARENT='asset-expansion-primary-pre2026-20261022'
URL='https://static.cninfo.com.cn/finalpage/2025-08-05/1224385530.PDF'
METHOD_FILES=('scripts/continue_asset_expansion_primary_pre2026.py',
    'scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/audit_cninfo_report_admission.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);root=Path(__file__).resolve().parents[1];base=Path(a.source_root);parent=base/PARENT;out=Path(a.output_dir);request=Path(a.request)
    if out.exists() or sha256_file(request)!=a.expected_request_sha256:raise ValueError('fresh frozen source continuation required')
    r=json.loads(request.read_text())
    if (r['status']!='FROZEN_ONE_SSL_FAILED_PRIMARY_DOWNLOAD_CONTINUATION' or r['URL']!=URL
            or r['maximum_additional_HTTP_reservations']!=1 or r['global_attempts_for_this_PDF_including_parent']!=2
            or r['max_attempts_per_identity']!=1 or set(r['method_code_sha256'])!=set(METHOD_FILES)):
        raise ValueError('one original PDF and explicit global two-attempt history required')
    bound={request:a.expected_request_sha256}
    for n,h in r['method_code_sha256'].items():bound[root/n]=h
    for n,h in r['parent_files_sha256'].items():
        if Path(n).is_absolute() or '..' in Path(n).parts:raise ValueError('registered parent-relative source required')
        bound[parent/n]=h
    for path,h in bound.items():
        if sha256_file(path)!=h:raise ValueError('original failure/source/method changed')
    m=json.loads((parent/'manifest.json').read_text())
    if m['capture_complete'] is not False or set(m['errors'])!={'SH600737'} or len(m['documents'])!=2:
        raise ValueError('expected immutable two-document/one-terminal-failure parent')
    failure=json.loads((parent/r['original_failed_response_file']).read_text())
    if failure['status']!='SOURCE_ERROR' or failure['error_type']!='URLError' or 'SSL' not in failure['error']:
        raise ValueError('separate retry only for the preserved terminal SSL error')
    out.mkdir(parents=True);(out/'request.json').write_bytes(request.read_bytes());documents={}
    for code,d in m['documents'].items():
        (out/d['file']).write_bytes((parent/d['file']).read_bytes());documents[code]=d
    error=None;journal=QueryJournal(out,max_queries=1,max_attempts=1)
    try:
        data,receipt=journaled_bytes(journal,{'source':'CNINFO_HTTP','url':URL,'payload':None,
            'primary_continuation_request_sha256':a.expected_request_sha256},lambda:read_wire(URL,None))
        file='SH600737-2025-08-05.pdf';(out/file).write_bytes(data)
        if not data.startswith(b'%PDF'):raise ValueError('original response is not PDF')
        documents['SH600737']={'instrument':'SH600737','publication_day':'2025-08-05','file':file,
            'sha256':sha256_file(out/file),'url':URL,'route':'SEPARATELY_FROZEN_SECOND_ATTEMPT_ORIGINAL_HTTP','HTTP_PDF_receipt':receipt,
            'original_listing_receipts':json.loads((parent/'SH600737-error.json').read_text())['HTTP_listing_receipts']}
    except Exception as exc:
        error={'error_type':type(exc).__name__,'error':str(exc)};write_packet_once(out/'error.json',error)
    changed=[str(path) for path,h in bound.items() if not path.is_file() or sha256_file(path)!=h]
    atomic_json(out/'manifest.json',{'status':'ASSET_EXPANSION_PRIMARY_CONTINUATION_CAPTURE_REVIEW_SEPARATE',
        'request_sha256':a.expected_request_sha256,'parent_manifest_sha256':r['parent_files_sha256']['manifest.json'],
        'documents':documents,'error':error,'changed_original_inputs':changed,
        'capture_complete':len(documents)==3 and error is None and not changed,
        'parent_HTTP_reservations':m['HTTP_reservations_consumed'],
        'additional_HTTP_reservations':len(list(out.rglob('reserved-*.json'))),
        'documents_financially_reviewed':False,'capital_tax_verified':False,'raw_account_admitted':False,
        'new_2026_queries':False,'portfolio_return_computed':False,'objective_achieved':False})
    print('separate original continuation',len(documents),'documents','error',error,flush=True)
    return 0 if len(documents)==3 and error is None and not changed else 2


if __name__=='__main__':raise SystemExit(main())
