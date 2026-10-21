"""Initial FY2022 primary PDF bytes over the historical394 source cohort.
Explicit-year title aliases; preserves all candidate editions, not financial data.
"""
import argparse
from pathlib import Path
import re
import time
from scripts import capture_profitability_historical_metadata as initial
from scripts.immutable_http_capture import ImmutableHttpCapture, need, file_sha, write_once
read = initial.read
META_REQUEST = 'experiments/qlib/profitability-historical394-metadata-request.json'
META_SHA = 'adf0c0d546695aae8b08030c1ad9594800c60dcf5d889b8380aa04391ef56913'
META_AUDIT = 'experiments/qlib/profitability-historical394-metadata-audit.json'
META_CODE = 'experiments/qlib/audit_sources/2026-10-22-historical395-metadata-audit.py'
OUTPUT = 'gross-profitability-historical394-initial2022-pdfs-20261022'
STATUS = 'FROZEN_BEFORE_HISTORICAL394_INITIAL2022_PDF_CAPTURE'
METHODS = (*initial.METHODS, 'scripts/capture_profitability_historical_initial_pdfs.py')
PUBLIC = (META_REQUEST, META_AUDIT, META_CODE,
    'experiments/qlib/profitability-historical394-metadata-results.json',
    'experiments/qlib/profitability-historical394-metadata-title-review.json',
    'docs/research/profitability-historical394-initial-pdf-plan-2026-10-22.md',
    'tests/test_profitability_historical_initial_pdfs.py')


def full_title(title, year=2022):
    clean = re.sub(r'[\s_《》]+', '', re.sub(r'<[^>]+>', '', title))
    if any(word in clean for word in ('摘要', '英文', '可视')):
        return False
    return re.search(str(year) + r'年?(?:年度报告|年报)(?:全文|[（(](?:全文|修订版?|修订稿|更正稿|更正后|更正版|更新后|更新版|中文版)[）)])?$', clean) is not None


def metadata_artifacts(base, root, membership):
    req,_ = initial.verify(base,root,membership,root/META_REQUEST,META_SHA)
    audit = read(root/META_AUDIT)
    need(audit['status'] == 'PASS_SEPARATE395_METADATA_AND_SINGLE_ATTEMPT_AUDIT_NOT_FINANCIAL_DATA_ADMISSION'
         and audit['request_sha256'] == META_SHA and audit['audit_code_sha256'] == file_sha(root/META_CODE)
         and audit['all445_input_sha256'] == {**req['input_sha256'],'frozen_source_request':META_SHA}, 'complete395 metadata audit required')
    folder = base/initial.OUTPUT
    actual = {str(p.relative_to(folder)):file_sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
    need(actual == audit['all_output_sha256'] and len(actual) == 1980, 'all1980 captured metadata outputs unchanged')
    summary = read(folder/'summary.json')
    need(summary['logical_attempts'] == summary['resource_count'] == 395 and not summary['status_counts'].get('METADATA_SOURCE_REJECTED'),
         'all395 original metadata resources classified without rejection')
    return read(folder/'case_results.json')


def derive_documents(base, root, membership):
    cases = metadata_artifacts(base,root,membership)
    cohort = read(root/initial.CATALOG)['dated_cohort']
    cached = [d for d in read(base/initial.DOCS) if d['fiscal_year'] == 2022]
    need(len(cached) == 12 and len({d['instrument'] for d in cached}) == 12, 'exact12 old initial originals')
    rows = [(d['instrument'],d,'AUTHENTICATED_FIXED12_INITIAL_RECORD',base/initial.DOCS,d) for d in cached]
    for key,case in cases.items():
        if case['fiscal_year'] != 2022:
            continue
        need(case['status'] in ('METADATA_CAPTURED_WITH_FULL_REPORT_CANDIDATES','METADATA_CAPTURED_NO_LITERAL_FULL_REPORT_CANDIDATE'), 'complete original initial metadata packet')
        for row in case['all_normalized_rows']:
            if full_title(row['title']):
                rows.append((case['instrument'],row,'SOURCE_BACKED_EXPLICIT_YEAR_TITLE_ALIASES',base/initial.OUTPUT/(key+'.json'),None))
    documents,seen = [],set()
    for code,row,origin,packet,cache in rows:
        identity = row['announcement_id']
        need(identity not in seen and code in cohort and '2023-01-01'<=row['day']<='2023-12-31'
             and full_title(row['title']) and type(row['pdf_path']) is str and re.fullmatch(
                 r'finalpage/\d{4}-\d{2}-\d{2}/'+re.escape(identity)+r'\.[pP][dD][fF]',row['pdf_path']),
             'unique safe source candidate with explicit2022 title and2023 publication')
        seen.add(identity)
        record={k:row[k] for k in ('title','day','timestamp_ms','announcement_id','pdf_path')}
        record.update(instrument=code,fiscal_year=2022,url='https://static.cninfo.com.cn/'+row['pdf_path'],
            capture_key=code+'-2022-'+identity,metadata_origin=origin,metadata_source_artifact_sha256=file_sha(packet),
            original_candidate_classification=row.get('classification','PRIOR_AUTHENTICATED_SOURCE_RECORD'))
        if cache is not None:
            need(file_sha(base/cache['source_path']) == cache['source_sha256'],'original cached source bytes')
            record.update(source_kind='REUSE_AUTHENTICATED_ORIGINAL_PDF',source_path=cache['source_path'],
                source_sha256=cache['source_sha256'],captured_at_utc=cache['captured_at_utc'])
        else:
            record['source_kind']='FRESH_FROZEN_PDF_GET'
        documents.append(record)
    return documents


def resources(documents):
    return {d['capture_key']:{'method':'GET','url':d['url'],'payload':None} for d in documents if d['source_kind']=='FRESH_FROZEN_PDF_GET'}


def required_paths(base, root, membership):
    paths=initial.required_paths(base,root,membership)
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    for name in read(root/META_AUDIT)['all_output_sha256']:
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe metadata artifact path')
        paths['source/'+initial.OUTPUT+'/'+name]=base/initial.OUTPUT/name
    return paths


def verify(base, root, membership, request_file, expected_sha):
    need(file_sha(request_file)==expected_sha,'frozen initial PDF request changed')
    req=read(request_file)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['metadata_request_sha256']==META_SHA
         and req['per_resource_attempts']==1 and req['max_body_bytes']==67108864 and req['timeout_seconds']==20
         and req['minimum_request_interval_seconds']==0.2 and req['cache_reuse_count']==12
         and req['financial_numeric_parsing_permitted'] is False and req['ranking_or_portfolio_returns_permitted'] is False
         and req['2026_financial_or_market_values_permitted'] is False,'fixed initial2022 bytes-only request')
    paths=required_paths(base,root,membership);initial.check(paths,req['input_sha256'])
    need(set(req['method_sha256'])==set(METHODS),'complete PDF method closure')
    for name,h in req['method_sha256'].items():need(h==req['input_sha256']['repo/'+name],'method/input identity')
    docs=derive_documents(base,root,membership);network=resources(docs)
    need(req['documents']==docs and req['resources']==network and req['document_count']==len(docs)
         and req['max_logical_attempts']==len(network) and len(docs)==len(network)+12,'every source candidate, original cache and URL required')
    cohort=read(root/initial.CATALOG)['dated_cohort']
    need(req['source_issuer_count']==len({d['instrument'] for d in docs}) and req['remaining_gap_issuers']==[c for c in cohort if c not in {d['instrument'] for d in docs}], 'all394 source outcomes retained')
    return req,paths


def capture(base, root, membership, request_file, expected_sha, out, *, opener=None, pause=time.sleep):
    need(out.resolve() == (base / OUTPUT).resolve() and not out.exists(), 'fixed fresh PDF output only; no retry/resume')
    req, paths = verify(base, root, membership, request_file, expected_sha)
    paths = {**paths, 'frozen_source_request': Path(request_file)}
    expected = {**req['input_sha256'], 'frozen_source_request': expected_sha}
    initial.check(paths, expected)
    out.mkdir(parents=True)
    results, primary, mismatches, persistence_errors, journal = {}, None, [], [], None
    try:
        write_once(out / 'input-before.json', expected)
        kwargs = {} if opener is None else {'opener': opener}
        journal = ImmutableHttpCapture(out / 'http', req['resources'], max_attempts=len(req['resources']),
                                       max_body_bytes=67108864, **kwargs)
        consecutive = 0
        for document in req['documents']:
            key = document['capture_key']
            try:
                if document['source_kind'] == 'REUSE_AUTHENTICATED_ORIGINAL_PDF':
                    need(file_sha(base / document['source_path']) == document['source_sha256'], 'old cached PDF mutated')
                    record = {**document, 'status': 'ORIGINAL_PDF_BYTES_REUSED_IDENTITY_REVIEW_SEPARATE'}
                else:
                    receipt, body = journal.fetch(key)
                    need(receipt['record']['http_status'] == 200 and receipt['record']['body_complete'] is True,
                         'complete original PDF HTTP200 required')
                    with body.open('rb') as stream:
                        header = stream.read(5)
                    need(header == b'%PDF-' and body.stat().st_size >= 1000, 'raw response is not a nontrivial PDF; original bytes retained')
                    record = {**document, 'status': 'PDF_MAGIC_CAPTURED_NUMERIC_IDENTITY_REVIEW_PENDING', 'receipt': receipt,
                              'source_path': str(body.relative_to(base)), 'source_sha256': file_sha(body),
                              'captured_at_utc': receipt['record']['captured_at_utc']}
                results[key] = record
                consecutive = 0
            except (OSError, ValueError, KeyError, TypeError) as exc:
                if getattr(exc, 'capture_evidence_persistence_error', False):
                    raise
                results[key] = {**document, 'status': 'PDF_SOURCE_REJECTED', 'error_type': type(exc).__name__, 'error': str(exc)}
                consecutive += 1
            write_once(out / (key + '.json'), results[key])
            print('historical initial2022 PDF', key, results[key]['status'], flush=True)
            if consecutive == 3:
                raise ValueError('three consecutive PDF source rejections; remaining resources not attempted')
            if document['source_kind'] == 'FRESH_FROZEN_PDF_GET':
                pause(0.2)
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if file_sha(path) != expected[key]:
                    mismatches.append({'input': key, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': key, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches,
                'source_request_rehashed_after_processing': True}
        terminal = {'status': 'HISTORICAL_INITIAL2022_PDF_CAPTURE_TERMINAL', 'logical_attempts': journal.attempts if journal else 0,
                    'completed_documents': len(results), 'pending': [d['capture_key'] for d in req['documents'] if d['capture_key'] not in results],
                    'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
                    'postcheck': post, 'persistence_errors': persistence_errors, 'financial_numeric_values_decoded': False}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try:
                write_once(out / name, value)
            except BaseException as exc:
                persistence_errors.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence_errors:
            primary.add_note('PDF terminal persistence errors: ' + str(persistence_errors))
        raise primary
    need(not mismatches and not persistence_errors, 'PDF input changed or terminal evidence failed')
    rejected = sum(r['status'] == 'PDF_SOURCE_REJECTED' for r in results.values())
    summary = {'status': 'HISTORICAL_INITIAL2022_PDF_BYTES_CAPTURED_REVIEW_PENDING' if not rejected else 'HISTORICAL_INITIAL2022_PDF_CAPTURE_INCOMPLETE',
        'request_sha256': expected_sha, 'documents_recorded': len(results), 'rejected_documents': rejected,
        'logical_attempts': journal.attempts, 'cached_reused': req['cache_reuse_count'], 'results_by_document': results,
        'input_count': len(paths), 'all_inputs_unchanged': True, 'financial_numeric_values_decoded': False,
        'financial_version_history_complete': False, 'historical_arrival_verified': False,
        'investment_factor_admitted': False, 'portfolio_returns_computed': False, 'objective_achieved': False}
    write_once(out / 'documents.json', list(results.values()))
    write_once(out / 'summary.json', summary)
    return summary



def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=capture(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['rejected_documents'],flush=True)
    return 2 if result['rejected_documents'] else 0


if __name__=='__main__':raise SystemExit(main())
