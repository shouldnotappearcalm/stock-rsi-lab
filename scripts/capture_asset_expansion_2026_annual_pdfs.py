"""All400 registered annual originals; source bytes only, no fiscal/ROI parsing."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re,time

from scripts.frozen_curl_http import FrozenCurlOpener
from scripts.immutable_http_capture import ImmutableHttpCapture,file_sha,need,write_once

SOURCE='asset-expansion-2026-metadata-completed-20261023'
OUTPUT='asset-expansion-2026-annual-pdfs-20261023'
PROTOCOL='docs/research/asset-expansion-2026-annual-pdf-plan-2026-10-23.md'
METHODS=('scripts/capture_asset_expansion_2026_annual_pdfs.py','scripts/frozen_curl_http.py',
    'scripts/immutable_http_capture.py','tests/test_asset_expansion_2026_pdfs.py')
PUBLIC=('experiments/qlib/asset-expansion-2026-completed-metadata-results.json',
    'experiments/qlib/asset-expansion-2026-completed-metadata-audit.json',
    'experiments/qlib/audit_sources/2026-10-23-asset-expansion-completed-metadata-audit.py',PROTOCOL)


def read(p):return json.loads(Path(p).read_text())


def specifications(cases):
    documents=[];resources={};ids=set()
    for code,case in sorted(cases.items()):
        need(re.fullmatch(r'(?:SH60|SZ00)\d{4}',code) and case['status'] in
            ('METADATA_CAPTURED_WITH_CANDIDATES','METADATA_CAPTURED_NO_FULL_CANDIDATE'),'complete accepted metadata cases only')
        for row in case['full_report_candidates']:
            day=row['day'];aid=row['announcement_id'];year=row['fiscal_year'];path=row['pdf_path']
            need(row['instrument']==code and 'CANDIDATE' in row['classification']
                and type(aid) is str and aid.isdigit() and aid not in ids
                and date.fromisoformat(day).isoformat()==day and '2026-01-01'<=day<='2026-10-21'
                and (year is None or type(year) is int and 1900<=year<=2025 and year<int(day[:4]))
                and type(path) is str and re.fullmatch('finalpage/'+re.escape(day)+'/'+aid+r'\.[pP][dD][fF]',path),
                'unique literal issuer/fiscal metadata/date/original PDF identity')
            ids.add(aid);key=code+'-'+aid;url='https://static.cninfo.com.cn/'+path
            doc={'key':key,'instrument':code,'announcement_id':aid,'day':day,'metadata_fiscal_year':year,
                'metadata_classification':row['classification'],'file':key+'.pdf','url':url,
                'cover_fiscal_identity_verified':False}
            documents.append(doc);resources[key]={'method':'GET','url':url,'payload':None}
    return documents,resources


def run(base,repo,request,expected,out):
    need(not out.exists() and out.resolve()==(base/OUTPUT).resolve() and file_sha(request)==expected,'fresh frozen400PDF source request')
    r=read(request)
    need(r['status']=='FROZEN_ALL400_ASSET_EXPANSION_2026_ANNUAL_PDF_BYTES'
        and r['maximum_logical_attempts']==400 and r['per_resource_attempts']==1 and r['max_body_bytes']==67108864
        and r['timeout_seconds']==20 and r['minimum_request_interval_seconds']==.2
        and r['financial_numeric_parsing_permitted'] is False and r['portfolio_returns_permitted'] is False
        and set(r['method_sha256'])==set(METHODS) and set(r['public_sha256'])==set(PUBLIC),'fixed400 original-byte budget and scope')
    bound={request:expected}
    for group in ('method_sha256','public_sha256'):
        for name,h in r[group].items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts,'repo-relative PDF source binding')
            bound[repo/name]=h
    qa=read(repo/PUBLIC[1]);need(qa['all_394_sources_accepted'] is True and qa['source_issuers_checked']==394
        and qa['full_report_candidates']==400 and qa['publication_clock_preserved'] is True
        and qa['PDF_bytes_or_financial_values_read'] is False,'complete separately audited metadata before PDF bytes')
    for name,h in qa['all_output_sha256'].items():bound[base/SOURCE/name]=h
    for p,h in bound.items():need(file_sha(p)==h,'frozen PDF input before '+str(p))
    docs,resources=specifications(read(base/SOURCE/'case_results.json'))
    need(len(docs)==400 and docs==r['documents'] and resources==r['resources'],'all exact candidate editions required')
    out.mkdir(parents=True);results={};journal=None;primary=None;persistence=[]
    try:
        write_once(out/'input-before.json',{str(p):h for p,h in bound.items()})
        transport=FrozenCurlOpener(out/'curl-transport',resources,max_body_bytes=67108864)
        journal=ImmutableHttpCapture(out/'http',resources,max_attempts=400,max_body_bytes=67108864,opener=transport)
        consecutive=0
        for number,doc in enumerate(docs,1):
            key=doc['key'];receipt=None
            try:
                receipt,body=journal.fetch(key)
                need(receipt['record']['http_status']==200,'original PDF HTTP status not200')
                with body.open('rb') as f:need(f.read(5)==b'%PDF-','source body is not original PDF')
                (out/doc['file']).write_bytes(body.read_bytes())
                value={**doc,'status':'ORIGINAL_PDF_BYTES_CAPTURED_NOT_FISCAL_ADMISSION','source_sha256':file_sha(out/doc['file']),
                    'source_path':OUTPUT+'/'+doc['file'],'captured_at_utc':receipt['record']['captured_at_utc'],'receipt':receipt}
                consecutive=0
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                if getattr(exc,'capture_evidence_persistence_error',False):raise
                value={**doc,'status':'PDF_SOURCE_REJECTED','receipt':receipt,'error_type':type(exc).__name__,'error':str(exc)};consecutive+=1
            results[key]=value;write_once(out/(key+'.json'),value)
            print('2026annualPDF',number,'/400',key,value['status'],flush=True)
            if consecutive==3:raise ValueError('three consecutive PDF source rejections; remaining originals not attempted')
            time.sleep(.2)
    except BaseException as exc:primary=exc
    finally:
        changed=[]
        for p,h in bound.items():
            try:
                if file_sha(p)!=h:changed.append(str(p))
            except BaseException as exc:changed.append(str(p)+':'+type(exc).__name__)
        terminal={'status':'ASSET_2026_PDF_CAPTURE_TERMINAL','logical_attempts':journal.attempts if journal else 0,
            'completed_resources':len(results),'pending':[d['key'] for d in docs if d['key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'changed_original_inputs':changed,'persistence_errors':persistence}
        successful=[v for v in results.values() if v['status']=='ORIGINAL_PDF_BYTES_CAPTURED_NOT_FISCAL_ADMISSION']
        for name,value in (('case_results.json',results),('documents.json',successful),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:raise primary
    need(not changed and not persistence and len(results)==400,'complete immutable PDF capture results')
    summary={'status':'ALL400_PDF_RESOURCES_PROCESSED_NOT_FINANCIAL_ADMISSION','request_sha256':expected,
        'resource_count':400,'logical_attempts':journal.attempts,'status_counts':dict(Counter(v['status'] for v in results.values())),
        'successful_original_PDFs':len(successful),'original_PDF_bytes':sum((out/v['file']).stat().st_size for v in successful),
        'all_original_inputs_unchanged':True,'cover_fiscal_identity_verified':False,'financial_numeric_values_decoded':False,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'2026_portfolio_returns_computed':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);print(summary['status'],summary['status_counts'],flush=True);return summary


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[1]
    result=run(base,repo,Path(a.request).resolve(),a.expected_request_sha256,base/OUTPUT)
    return 2 if result['status_counts'].get('PDF_SOURCE_REJECTED',0) else 0

if __name__=='__main__':raise SystemExit(main())
