"""Bounded400-document source extraction with the unchanged annual-assets grammar."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib,json,re,sys
from pathlib import Path

from scripts.immutable_http_capture import need,write_once
from stock_rsi import annual_assets as assets

SOURCE='asset-expansion-2026-annual-pdfs-20261023'
OUTPUT='asset-expansion-2026-assets-20261023'
PROTOCOL='docs/research/asset-expansion-2026-assets-extraction-plan-2026-10-23.md'
WORKERS=4
METHODS=('scripts/inspect_asset_expansion_2026_assets.py','scripts/immutable_http_capture.py',
    'src/stock_rsi/annual_assets.py','src/stock_rsi/annual_profitability.py',
    *(f'src/stock_rsi/annual_profitability_v{i}.py' for i in range(2,8)),
    'src/stock_rsi/data.py','src/stock_rsi/calendar.py','src/stock_rsi/time.py',
    'tests/test_asset_expansion_2026_assets.py')
PUBLIC=('experiments/qlib/asset-expansion-2026-annual-pdf-results.json',
    'experiments/qlib/asset-expansion-2026-annual-pdf-byte-audit.json',
    'experiments/qlib/audit_sources/2026-10-23-asset-expansion-annual-pdf-byte-audit.py',PROTOCOL)
CURRENCY=tuple('gross-profitability-cas-currency-primary-20261022/cas19/'+n for n in ('body.bin','response.json','text.txt'))


def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def inspect_pages(document,pages,normative_basis):
    metadata_year=document['metadata_fiscal_year'];year=metadata_year;resolved=False
    if year is None:
        first=re.sub(r'\s+','','\n'.join(pages[:5]))
        years={int(v) for v in re.findall(r'((?:19|20)\d{2})年?年度报告',first)}
        if len(years)==1 and next(iter(years))<=2025:year=next(iter(years));resolved=True
    identity=(assets.grammar.document_identity(pages,document['instrument'],year) if type(year) is int
        else {'code_consistent':False,'annual_year_consistent':False,'error':'NO_UNAMBIGUOUS_LITERAL_ANNUAL_COVER_YEAR'})
    result={'capture_key':document['key'],'instrument':document['instrument'],'metadata_fiscal_year':metadata_year,
        'fiscal_year':year,'year_resolved_from_literal_cover':resolved,'source_sha256':document['source_sha256'],
        'publication_day':document['day'],'observed_at':document['captured_at_utc'],'page_count':len(pages),
        'identity_evidence':identity,'cover_code_consistent':identity['code_consistent'],
        'cover_annual_year_consistent':identity['annual_year_consistent'],
        'all_extracted_page_text_sha256':{str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)},
        'parser_contract':assets.CONTRACT,'asset_report':None,'historical_arrival_verified':False,
        'financial_version_history_complete':False,'economic_sector_compatibility_verified':False,
        'manual_numeric_visual_review_complete':False,'investment_factor_admitted':False}
    if not(identity['code_consistent'] and identity['annual_year_consistent']):return {**result,'status':'COVER_IDENTITY_UNVERIFIED'}
    try:
        balances=assets.parse_balance_only(pages,year,normative_basis=normative_basis)
        report=assets.make_report(document['instrument'],year,document['day'],document['captured_at_utc'],
            document['source_sha256'],document['announcement_id'],balances)
        return {**result,'status':'ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA','asset_report':report}
    except (ValueError,KeyError,ArithmeticError) as exc:
        return {**result,'status':'ASSET_SOURCE_SCHEMA_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc)}


def inspect_one(base,document,normative_basis):
    import pypdf
    need(pypdf.__version__=='6.10.0','fixed original PDF extractor')
    f=Path(base)/document['source_path'];need(sha(f)==document['source_sha256'],'source PDF before decode')
    try:
        reader=pypdf.PdfReader(f);need(not reader.is_encrypted,'encrypted source PDF unsupported')
        need(1<=len(reader.pages)<=1200,'original source physical page cap1200')
        pages=[page.extract_text() or '' for page in reader.pages]
    except (ValueError,pypdf.errors.PdfReadError,pypdf.errors.DependencyError) as exc:
        need(sha(f)==document['source_sha256'],'source PDF after failed decode')
        return {'capture_key':document['key'],'instrument':document['instrument'],
            'metadata_fiscal_year':document['metadata_fiscal_year'],'source_sha256':document['source_sha256'],
            'status':'SOURCE_PDF_EXTRACTION_UNSUPPORTED','error_type':type(exc).__name__,'error':str(exc),
            'page_count':None,'asset_report':None,'all_extracted_page_text_sha256':{},
            'historical_arrival_verified':False,'financial_version_history_complete':False,'investment_factor_admitted':False},None
    result=inspect_pages(document,pages,normative_basis)
    need(sha(f)==document['source_sha256'],'source PDF after source cells');return result,pages


def verify(base,repo,request,expected):
    import pypdf
    need(sha(request)==expected,'frozen400 annual-assets request');r=read(request)
    need(r['status']=='FROZEN_400_ORIGINAL_2026_ANNUAL_ASSET_EXTRACTION'
        and r['document_count']==400 and r['workers']==r['maximum_outstanding_documents']==WORKERS
        and r['runtime_python']==sys.version.split()[0] and r['pypdf_version']==pypdf.__version__=='6.10.0'
        and r['parser_contract']==assets.CONTRACT and r['normative_basis']==assets.CAS19_REFERENCE
        and r['network_permitted'] is False and r['ranking_or_portfolio_returns_permitted'] is False
        and set(r['method_sha256'])==set(METHODS) and set(r['public_sha256'])==set(PUBLIC)
        and set(r['currency_source_sha256'])==set(CURRENCY)
        and r['currency_source_sha256'][CURRENCY[0]]==assets.CAS19_REFERENCE['archived_body_sha256']
        and r['currency_source_sha256'][CURRENCY[2]]==assets.CAS19_REFERENCE['archived_text_sha256'],
        'fixed source-only grammar/runtime/work scope')
    bound={request:expected}
    for group,parent in (('method_sha256',repo),('public_sha256',repo),('currency_source_sha256',base)):
        for name,h in r[group].items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts,'root-relative source binding')
            bound[parent/name]=h
    qa=read(repo/PUBLIC[1]);need(qa['all400_originals_captured'] is True and not qa['source_rejections'] and not qa['pending'],
        'all original400 PDFs separately byte-audited before text')
    for name,h in qa['all_output_sha256'].items():bound[base/SOURCE/name]=h
    for p,h in bound.items():need(sha(p)==h,'assets input before '+str(p))
    need(read(base/SOURCE/'documents.json')==r['documents'] and len({d['key'] for d in r['documents']})==400,'same complete400 metadata editions')
    return r,bound


def run(base,repo,request,expected,out,*,executor_factory=ProcessPoolExecutor,worker=inspect_one):
    need(not out.exists() and out.resolve()==(base/OUTPUT).resolve(),'fresh asset-source output,no retry/resume')
    r,bound=verify(base,repo,request,expected);out.mkdir(parents=True);results={};submitted=[];primary=None;persistence=[]
    try:
        write_once(out/'input-before.json',{str(p):h for p,h in bound.items()})
        with executor_factory(max_workers=WORKERS) as pool:
            for start in range(0,len(r['documents']),WORKERS):
                batch=r['documents'][start:start+WORKERS];futures=[]
                for doc in batch:submitted.append(doc['key']);futures.append(pool.submit(worker,str(base),doc,r['normative_basis']))
                for doc,future in zip(batch,futures):
                    case,pages=future.result();key=doc['key']
                    need(case['capture_key']==key and case['source_sha256']==doc['source_sha256'],'worker original identity')
                    if pages is not None:
                        cache=out/(key+'.pages.json');write_once(cache,{'source_sha256':doc['source_sha256'],'extractor':'pypdf6.10.0','pages':pages})
                        case['source_page_cache_sha256']=sha(cache)
                    write_once(out/(key+'.json'),case);results[key]=case
                    print('2026annualassets',len(results),'/400',key,case['status'],flush=True)
    except BaseException as exc:primary=exc
    finally:
        changed=[]
        for p,h in bound.items():
            try:
                if sha(p)!=h:changed.append(str(p))
            except BaseException as exc:changed.append(str(p)+':'+type(exc).__name__)
        terminal={'status':'ASSET_2026_SOURCE_EXTRACTION_TERMINAL','submitted':submitted,'completed_resources':len(results),
            'pending':[d['key'] for d in r['documents'] if d['key'] not in results],
            'original_error':None if primary is None else {'type':type(primary).__name__,'message':str(primary)},
            'changed_original_inputs':changed,'persistence_errors':persistence}
        reports=[c['asset_report'] for c in results.values() if c['asset_report'] is not None]
        for name,value in (('case_results.json',results),('asset_reports.json',reports),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if primary is not None:raise primary
    need(not changed and not persistence and len(results)==400,'complete immutable400 source extraction')
    visibility={}
    for mode in (assets.OBSERVED,assets.RECONSTRUCTED):
        view=assets.visible_reports(reports,'2026-10-21T15:05:00+08:00',mode=mode)
        visibility[mode]={'count':len(view['reports']),'record_ids':[x['record_id'] for x in view['reports']]}
    need(visibility[assets.OBSERVED]['count']==0,'actual postcutoff capture must not appear as historical observed feed')
    summary={'status':'ALL400_2026_ANNUAL_ASSET_CASES_COMPLETE_PENDING_INDEPENDENT_SOURCE_QA','request_sha256':expected,
        'document_count':400,'status_counts':dict(Counter(c['status'] for c in results.values())),
        'asset_report_count':len(reports),'asset_cell_count':sum(len(x['payload']['balances']) for x in reports),
        'paired_report_count':sum(len(x['payload']['balances'])==2 for x in reports),
        'physical_pages_decoded':sum(c['page_count'] or 0 for c in results.values()),'visibility_at_cutoff':visibility,
        'all_original_inputs_unchanged':True,'unchanged_parser_contract':assets.CONTRACT,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'investment_factor_admitted':False,
        '2026_ranks_or_portfolio_returns_computed':False,'objective_achieved':False}
    write_once(out/'summary.json',summary);print(summary['status'],summary['status_counts'],flush=True);return summary


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[1]
    run(base,repo,Path(a.request).resolve(),a.expected_request_sha256,base/OUTPUT)

if __name__=='__main__':main()
