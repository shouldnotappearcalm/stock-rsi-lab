"""Frozen original107-page industry-table extraction and clocked cohort views.
No network,stock ranking,price read,portfolio/account or current-sector assertion.
"""
import argparse
import base64
from collections import Counter
from datetime import timedelta
import email.utils
import hashlib
import json
from pathlib import Path
import sys
from scripts.immutable_http_capture import file_sha,write_once,need
from stock_rsi import industry_catalog as catalog

RESEARCH='experiments/qlib/profitability-historical-sector-2021Q3-archival-evidence.json'
COHORT='experiments/qlib/profitability-historical394-source-inventory.json'
LAYOUT='gross-profitability-industry-catalog-layout-evidence-20261022/first-two-page-layout-excerpts.json'
FIXTURE='tests/fixtures/industry-2021Q3-real-layout-excerpts.json'
OUTPUT='gross-profitability-2021Q3-industry-catalog-v1-20261022'
STATUS='FROZEN_BEFORE_COMPLETE107_PAGE_ARCHIVED2021Q3_CLASSIFICATION_EXTRACTION'
SOURCE_SHA='0e8af6662353037135bb8e8a08a409dcebea9c47f71e7e25b48fe66a24f8c62b'
PUBLIC_BY='2021-12-27T20:06:27+00:00'
METHODS=('src/stock_rsi/data.py','src/stock_rsi/industry_catalog.py','scripts/immutable_http_capture.py','scripts/build_profitability_industry_catalog.py')
PUBLIC=(RESEARCH,COHORT,FIXTURE,'docs/research/profitability-industry-catalog-plan-2026-10-22.md',
        'tests/test_industry_catalog.py','tests/test_industry_catalog_runner.py')


def read(path):return json.loads(Path(path).read_text())
def queries(public,observed):
    before=(catalog.aware(public)-timedelta(microseconds=1)).isoformat()
    return [{'id':label,'as_of':clock,'mode':mode} for label,clock,mode in (
        ('before_archive_bound',before,catalog.ARCHIVE_RECONSTRUCTED),('at_archive_bound',public,catalog.ARCHIVE_RECONSTRUCTED),
        ('observed2024','2024-01-02T09:00:00+08:00',catalog.OBSERVED),('observed2025','2025-12-31T15:05:00+08:00',catalog.OBSERVED),
        ('reconstructed2024','2024-01-02T09:00:00+08:00',catalog.ARCHIVE_RECONSTRUCTED),
        ('reconstructed2025','2025-12-31T15:05:00+08:00',catalog.ARCHIVE_RECONSTRUCTED),('at_source_observation',observed,catalog.OBSERVED))]


def required_paths(base,root,membership):
    paths={'membership':membership,'source/'+LAYOUT:base/LAYOUT}
    for name in (*METHODS,*PUBLIC):paths['repo/'+name]=root/name
    research=read(root/RESEARCH);folder=base/research['local_archive_relative_source_root']
    for name,value in research['all_local_artifact_sha256'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe archived source path')
        path=folder/name;need(file_sha(path)==value,'original archived source bytes changed')
        paths['source/'+str(path.relative_to(base))]=path
    return paths


def source_observed_at(base,research):
    folder=base/research['local_archive_relative_source_root']
    return max(catalog.aware(read(folder/name)['captured_at_utc']) for name in research['all_local_artifact_sha256'] if name.endswith('response.json')).isoformat()


def verify(base,root,membership,request_file,expected_sha):
    import pdfplumber,pdfminer
    need(sys.version.split()[0]=='3.12.14' and pdfplumber.__version__=='0.11.9' and pdfminer.__version__=='20251230','registered original-table runtime')
    need(file_sha(request_file)==expected_sha,'frozen classification request changed')
    req=read(request_file);research=read(root/RESEARCH);folder=base/research['local_archive_relative_source_root']
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['physical_pages']==107 and req['cohort_count']==394
         and req['source_pdf_sha256']==SOURCE_SHA and req['catalog_contract']==catalog.CONTRACT
         and req['public_content_available_by']==PUBLIC_BY and req['source_observed_at']==source_observed_at(base,research)
         and req['snapshot_queries']==queries(PUBLIC_BY,req['source_observed_at'])
         and req['classification_labels_are_2021_vintage_only'] is True and req['network_permitted'] is False
         and req['stock_ranking_or_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'complete107-page source-only protocol')
    paths=required_paths(base,root,membership)
    need(set(paths)==set(req['input_sha256']) and set(req['method_sha256'])==set(METHODS),'complete source/method bindings')
    for key,path in paths.items():need(file_sha(path)==req['input_sha256'][key],'changed bound input: '+key)
    for name,value in req['method_sha256'].items():need(value==req['input_sha256']['repo/'+name],'method/input identity')
    pdf=folder/'classification/body.bin';archive=folder/'archive-payload/body.bin'
    need(file_sha(pdf)==file_sha(archive)==SOURCE_SHA and req['source_pdf_relative_path']==str(pdf.relative_to(base)),'byte-identical current and2021 archived original PDF')
    response=read(folder/'archive-payload/response.json');headers={k.lower():v for k,v in response['headers'].items()}
    need(email.utils.parsedate_to_datetime(headers['memento-datetime']).isoformat()==PUBLIC_BY,'actual archived payload timestamp')
    cdx=read(folder/'archive-cdx/decoded.json');digest=base64.b32encode(hashlib.sha1(pdf.read_bytes()).digest()).decode()
    need(any(row[0]=='20211227200627' and row[2]==digest for row in cdx[1:]),'original pre2024 CDX digest')
    notice=read(folder/'archived-notice-link-research.json')
    need(notice['archive_timestamp_utc']=='20211227184941' and len(notice['matching_attachment_links'])==1
         and notice['matching_attachment_links'][0]['original_absolute_url'].endswith('/1638277734844_11692.pdf')
         and research['publication_date_field_conflicts_retained'] is True,'historical official notice/attachment and retained date conflict')
    names=sorted({c for c,start,end in (line.split() for line in membership.read_text().splitlines())
                  if start<='2024-01-02'<=end and c.startswith(('SH60','SZ00'))})
    need(len(names)==394 and names==req['cohort']==read(root/COHORT)['dated_cohort'],'full dated394 source range,not parsed-success names')
    return req,paths,names


def extract_packets(pdf,source_sha,expected_pages):
    import pdfplumber,pdfminer
    with pdfplumber.open(pdf) as doc:
        need(len(doc.pages)==expected_pages,'all original physical pages required')
        for i,page in enumerate(doc.pages):
            tables=[]
            for j,table in enumerate(page.find_tables()):
                values=table.extract();geometry=table.rows;need(len(values)==len(geometry),'source text/geometry row alignment')
                rows=[{'row_index':n,'cells':[{'literal':literal,'bbox':None if b is None else list(b)} for literal,b in zip(row,geometry[n].cells)]} for n,row in enumerate(values)]
                tables.append({'table_index':j,'bbox':list(table.bbox),'rows':rows})
            text=page.extract_text() or ''
            yield {'physical_page':i+1,'source_sha256':source_sha,'width':page.width,'height':page.height,
                   'extractor':{'pdfplumber':pdfplumber.__version__,'pdfminer':pdfminer.__version__},'tables':tables,
                   'page_text':text,'page_text_sha256':hashlib.sha256(text.encode()).hexdigest()}
            page.close()


def run(base,root,membership,request_file,expected_sha,out,*,extractor=extract_packets):
    need(out.resolve()==(base/OUTPUT).resolve() and not out.exists(),'fresh classification output only; no retry/resume')
    req,paths,cohort=verify(base,root,membership,request_file,expected_sha)
    paths={**paths,'frozen_source_request':Path(request_file)};expected={**req['input_sha256'],'frozen_source_request':expected_sha}
    for key,path in paths.items():need(file_sha(path)==expected[key],'source input before: '+key)
    out.mkdir(parents=True);packets=[];primary=None;errors=[];mismatches=[];iterator=None
    try:
        write_once(out/'input-before.json',expected)
        iterator=extractor(base/req['source_pdf_relative_path'],req['source_pdf_sha256'],req['physical_pages'])
        for index,packet in enumerate(iterator,1):
            need(index<=req['physical_pages'],'source extractor exceeded registered physical page budget')
            write_once(out/('page-'+str(index).zfill(3)+'.json'),packet)
            need(packet['physical_page']==index and packet['source_sha256']==req['source_pdf_sha256'],'complete ordered original PDF packets')
            packets.append(packet);print('industry source geometry',index,'/',req['physical_pages'],flush=True)
        need(len(packets)==req['physical_pages'],'complete original table extraction required')
        product=catalog.parse_catalog(packets,source_sha256=req['source_pdf_sha256'],public_by=req['public_content_available_by'],
            observed_at=req['source_observed_at'],expected_pages=req['physical_pages'])
        write_once(out/'catalog.json',product)
        snapshots={q['id']:catalog.snapshot_catalog(product,cohort,q['as_of'],mode=q['mode']) for q in req['snapshot_queries']}
        write_once(out/'cohort-snapshots.json',snapshots)
    except BaseException as exc:primary=exc
    finally:
        if iterator is not None and hasattr(iterator,'close'):
            try:iterator.close()
            except BaseException as exc:
                if primary is None:primary=exc
                else:primary.add_note('source reader cleanup: '+type(exc).__name__)
        for key,path in paths.items():
            try:
                if file_sha(path)!=expected[key]:mismatches.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:mismatches.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not mismatches,'count':len(paths),'mismatches':mismatches,'source_request_rehashed_after_processing':True}
        terminal={'status':'ARCHIVED_INDUSTRY_CATALOG_TERMINAL','completed_geometry_pages':len(packets),
            'pending_physical_pages':list(range(len(packets)+1,req['physical_pages']+1)),
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'postcheck':post,'persistence_errors':errors,'stock_ranking_or_returns_computed':False}
        for name,value in (('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:errors.append(name+':'+type(exc).__name__)
    if primary is not None:
        if errors:primary.add_note('classification terminal persistence: '+str(errors))
        raise primary
    need(not mismatches and not errors,'complete unchanged source classification required')
    counts=lambda key:dict(Counter(r['status'] for r in snapshots[key]['classifications']))
    first=snapshots['reconstructed2024']['classifications'];second=snapshots['reconstructed2025']['classifications']
    equal={r['instrument']:r.get('record_id') for r in first}=={r['instrument']:r.get('record_id') for r in second}
    observed_visible=sum(r['status']!='NOT_AVAILABLE_AT_CLOCK' for key in ('observed2024','observed2025') for r in snapshots[key]['classifications'])
    need(equal and observed_visible==0,'source vintage and default observed clock controls')
    summary={'status':'ARCHIVED2021Q3_INDUSTRY_CATALOG_EXTRACTED_NOT_FACTOR_ADMITTED','request_sha256':expected_sha,
        'source_pdf_sha256':req['source_pdf_sha256'],'physical_pages':len(packets),'source_classification_records':product['record_count'],
        'dated_cohort_count':len(cohort),'classification_period':catalog.PERIOD,'reconstructed2024_source_vintage_status_counts':counts('reconstructed2024'),
        'unmatched_dated_cohort':[r['instrument'] for r in first if r['status']=='NOT_IN_SOURCE_VINTAGE'],
        'source_vintage_financial_cohort':[r['instrument'] for r in first if r['status']=='FINANCIAL_IN_SOURCE_VINTAGE'],
        'source_vintage_nonfinancial_cohort':[r['instrument'] for r in first if r['status']=='NONFINANCIAL_IN_SOURCE_VINTAGE'],
        'observed_pre2026_visible_classifications':observed_visible,'reconstructed2024_2025_record_ids_equal':equal,
        'public_content_available_by':req['public_content_available_by'],'source_observed_at':req['source_observed_at'],
        'input_count':len(paths),'all_inputs_unchanged':True,'current_business_identity_verified':False,'classification_history_complete':False,
        'financial_reporting_compatibility_verified':False,'historical_nonfinancial_identity_complete':False,'investment_factor_admitted':False,
        'stock_ranking_or_portfolio_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    a=p.parse_args();base,root=Path(a.source_root).resolve(),Path(__file__).resolve().parents[1]
    result=run(base,root,Path(a.membership_file).resolve(),Path(a.request),a.expected_request_sha256,base/OUTPUT)
    print(result['status'],result['reconstructed2024_source_vintage_status_counts'],flush=True)


if __name__=='__main__':main()
