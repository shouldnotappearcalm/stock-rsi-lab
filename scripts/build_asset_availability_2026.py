"""Frozen full-cohort asset source joins, with unchanged pre2026 selection."""
import argparse
from collections import Counter
from datetime import date
import hashlib,json
from pathlib import Path

from scripts.immutable_http_capture import need,write_once
from stock_rsi import asset_availability as source

OUTPUT='asset-expansion-monthly-availability-through2026-v1-20261023'
OLD_ASSETS='annual-total-assets-all1236-v1-20261022'
NEW_ASSETS='asset-expansion-2026-assets-20261023'
INDUSTRY='gross-profitability-2021Q3-industry-catalog-v1-20261022'
LEGACY='gross-profitability-monthly-availability-v1-20261022'
CALENDAR='qlib-enhanced-dev/calendars/day.txt'
PROTOCOL='docs/research/asset-expansion-2026-availability-plan-2026-10-23.md'
STATUS='FROZEN_1636_EDITION_ASSET_AVAILABILITY_THROUGH_2026_OCT'
OLD_REQUEST='experiments/qlib/annual-assets-all1236-request.json'
NEW_REQUEST='experiments/qlib/asset-expansion-2026-assets-request.json'
OLD_AUDIT='experiments/qlib/annual-assets-all1236-source-audit.json'
NEW_AUDIT='experiments/qlib/asset-expansion-2026-assets-source-audit.json'
LEGACY_REQUEST='experiments/qlib/profitability-monthly-availability-request.json'
LEGACY_AUDIT='experiments/qlib/profitability-monthly-availability-audit.json'
INDUSTRY_AUDIT='experiments/qlib/profitability-2021Q3-industry-catalog-source-audit.json'
SEED_REQUEST='experiments/qlib/asset-expansion-pre2026-request.json'
PUBLIC=(OLD_REQUEST,NEW_REQUEST,OLD_AUDIT,NEW_AUDIT,LEGACY_REQUEST,LEGACY_AUDIT,INDUSTRY_AUDIT,SEED_REQUEST,PROTOCOL)
METHODS=('src/stock_rsi/asset_availability.py','src/stock_rsi/annual_assets.py',
    'src/stock_rsi/annual_profitability.py','src/stock_rsi/data.py','src/stock_rsi/industry_catalog.py',
    'src/stock_rsi/profitability_availability.py','src/stock_rsi/asset_expansion_monthly.py',
    'scripts/immutable_http_capture.py','scripts/build_asset_availability_2026.py',
    'tests/test_asset_availability.py','tests/test_asset_availability_runner.py')
SELECTION_FIELDS=('instrument','industry_status','industry_classification_period','current_business_identity_verified',
    'financial_version_history_complete','financial_reporting_compatibility_verified','investment_factor_admitted',
    'latest_fiscal_year','latest_publication_day','selected_edition_capture_keys','selected_capture_key','selected_source_sha256')


def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}


def formations(lines):
    days=[date.fromisoformat(s) for s in lines]
    need(days and days==sorted(set(days)) and all(d.isoformat()==s for d,s in zip(days,lines))
        and days[0]<date(2024,1,2),'unique ordered explicit sessions with preceding anchor')
    return [{'execution_session':b.isoformat(),'as_of':a.isoformat()+'T15:05:00+08:00'}
        for a,b in zip(days,days[1:]) if '2024-01-02'<=b.isoformat()<='2026-10-21' and a.strftime('%Y-%m')!=b.strftime('%Y-%m')]


def assert_legacy_selection_parity(new,old):
    def project(view):
        rows=[]
        for row in view['classifications']:
            unresolved=row['annual_status'] if row['annual_status'] in ('NO_VISIBLE_ANNUAL_REPORT','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS') else None
            rows.append({**{k:row.get(k) for k in SELECTION_FIELDS},'unresolved_metadata_status':unresolved})
        return {**{k:view[k] for k in ('as_of','visibility_mode','cohort_count')},'classifications':rows}
    need(project(new)==project(old),'legacy selection parity: no changed clock, cohort, industry or selected annual edition')


def canonical_documents(old,new,new_cases):
    docs=list(old['documents'])
    for d in new['documents']:
        year=d['metadata_fiscal_year']
        if year is None:
            case=new_cases[d['key']]
            need(case['year_resolved_from_literal_cover'] is True and type(case['fiscal_year']) is int,
                'yearless metadata needs previously authenticated literal-cover resolution')
            year=case['fiscal_year']
        docs.append({**d,'capture_key':d['key'],'effective_fiscal_year':year})
    need(len(docs)==len({d['capture_key'] for d in docs}),'all original editions have unique source keys')
    return docs


def dependency_contract(base,repo,membership):
    """Bind consumed immutable source outputs and their parent evidence, no PDFs."""
    paths={'membership':membership,'source/'+CALENDAR:base/CALENDAR}
    expected={k:sha(v) for k,v in paths.items()}
    for name in (*PUBLIC,*METHODS):
        key='repo/'+name;paths[key]=repo/name;expected[key]=sha(repo/name)
    for folder,evidence,field in ((OLD_ASSETS,OLD_AUDIT,'all_output_sha256'),
        (NEW_ASSETS,NEW_AUDIT,'all_original_extraction_output_sha256'),
        (INDUSTRY,INDUSTRY_AUDIT,'all_output_sha256'),(LEGACY,LEGACY_AUDIT,'all_output_sha256')):
        parent=read(repo/evidence);outputs=parent[field]
        need(inventory(base/folder)==outputs,'entire unchanged parent source output '+folder)
        for name,h in outputs.items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe parent output binding')
            key='source/'+folder+'/'+name;paths[key]=base/folder/name;expected[key]=h
    return expected,paths


def verify(base,repo,membership,request,expected_sha):
    need(sha(request)==expected_sha,'frozen asset availability request')
    req=read(request)
    need(req['status']==STATUS and req['output_subdir']==OUTPUT and req['source_cutoff']==source.CUTOFF
        and req['document_count']==1636 and req['cohort_count']==394 and req['query_count']==68
        and req['pre2026_parity_query_count']==48 and req['modes']==[source.OBSERVED,source.RECONSTRUCTED]
        and req['network_permitted'] is False and req['market_values_permitted'] is False
        and req['ranking_or_returns_permitted'] is False and req['newer_failures_block_older_values'] is True
        and req['classification_vintage']=='2021Q3' and req['historical_arrival_verified'] is False
        and req['investment_rule_changed'] is False and set(req['method_sha256'])==set(METHODS),
        'complete fixed source-only asset availability protocol')
    expected,paths=dependency_contract(base,repo,membership)
    need(req['input_sha256']==expected,'exact frozen consumed-source and method closure')
    need(req['method_sha256']=={n:expected['repo/'+n] for n in METHODS},'complete source method binding')
    old,new,legacy=(read(repo/n) for n in (OLD_REQUEST,NEW_REQUEST,LEGACY_REQUEST))
    oldqa,newqa,legacyqa,industryqa=(read(repo/n) for n in (OLD_AUDIT,NEW_AUDIT,LEGACY_AUDIT,INDUSTRY_AUDIT))
    need(oldqa['request_sha256']==sha(repo/OLD_REQUEST) and oldqa['document_count']==1236
        and oldqa['all_inputs_and_outputs_unchanged'] is True and oldqa['asset_report_count']==907
        and newqa['request_sha256']==sha(repo/NEW_REQUEST) and newqa['document_count']==400
        and newqa['supported_asset_cells_checked']==472 and newqa['all_original_inputs_unchanged'] is True
        and legacyqa['request_sha256']==sha(repo/LEGACY_REQUEST) and legacyqa['queries_checked']==48
        and legacyqa['all_inputs_and_outputs_unchanged'] is True and industryqa['all_inputs_and_outputs_unchanged'] is True,
        'authenticated complete parent source evidence')
    need(newqa['summary_sha256']==expected['source/'+NEW_ASSETS+'/summary.json'],'same reviewed original extraction summary')
    new_cases=read(base/NEW_ASSETS/'case_results.json')
    need(set(new_cases)==set(newqa['source_case_results']) and req['documents']==canonical_documents(old,new,new_cases),
        'all1636 original source editions and previously authenticated cover years')
    cohort=sorted({c for c,a,b in (s.split() for s in membership.read_text().splitlines())
        if a<='2024-01-02'<=b and c.startswith(('SH60','SZ00'))})
    need(req['cohort']==cohort==old['cohort']==legacy['cohort']==read(repo/SEED_REQUEST)['cohort'] and len(cohort)==394,
        'same full initial dated source cohort')
    clocks=formations((base/CALENDAR).read_text().splitlines())
    months=[f'{y}-{m:02}' for y in (2024,2025,2026) for m in range(1,13 if y<2026 else 11)]
    need(req['formations']==clocks and len(clocks)==34 and [q['execution_session'][:7] for q in clocks]==months
        and clocks[:24]==legacy['formations'],'same old24 and complete explicit-session34 monthly clocks')
    return req,paths


def query_receipt(formation,mode,result):
    rows=result['classifications']
    return {**formation,'mode':mode,'artifact':formation['execution_session']+'-'+mode+'.json',
        'annual_status_counts':dict(Counter(r['annual_status'] for r in rows)),
        'industry_annual_status_counts':dict(Counter(r['industry_status']+'/'+r['annual_status'] for r in rows)),
        'supported_selected_reports':sum('asset_record_id' in r for r in rows),
        'explicit_paired_selected_reports':sum(r.get('has_explicit_prior_year_end',False) for r in rows)}


def run(base,repo,membership,request,expected_sha,*,builder=source.snapshot_availability):
    out=base/OUTPUT;need(not out.exists(),'fresh asset availability output; no resume or overwrite')
    req,paths=verify(base,repo,membership,request,expected_sha)
    paths={**paths,'frozen_source_request':request};expected={**req['input_sha256'],'frozen_source_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'asset availability input before '+key)
    out.mkdir(parents=True);completed=[];parity=0;original=None;changed=[];persistence=[]
    try:
        write_once(out/'input-before.json',expected)
        cases=read(base/OLD_ASSETS/'case_results.json');new=read(base/NEW_ASSETS/'case_results.json')
        need(not set(cases)&set(new),'disjoint original asset edition keys');cases.update(new)
        need(set(cases)=={d['capture_key'] for d in req['documents']},'all and only original asset cases')
        industry=read(base/INDUSTRY/'catalog.json')
        for formation in req['formations']:
            for mode in req['modes']:
                view=builder(req['documents'],cases.__getitem__,industry,req['cohort'],formation['as_of'],mode=mode)
                need(view['as_of']==source.aware(formation['as_of']).isoformat() and view['visibility_mode']==mode
                    and view['cohort_count']==len(req['cohort']),'exact requested source query identity')
                need([r['instrument'] for r in view['classifications']]==sorted(req['cohort']),'complete same-cohort query')
                name=formation['execution_session']+'-'+mode+'.json';old=formation['execution_session']<'2026-01-01'
                if old:assert_legacy_selection_parity(view,read(base/LEGACY/name))
                write_once(out/name,view);completed.append(query_receipt(formation,mode,view));parity+=int(old)
                print('asset availability',len(completed),'/',len(req['formations'])*len(req['modes']),name,flush=True)
    except BaseException as exc:original=exc
    finally:
        for key,path in paths.items():
            try:
                if sha(path)!=expected[key]:changed.append({'input':key,'reason':'SHA256_CHANGED'})
            except BaseException as exc:changed.append({'input':key,'reason':type(exc).__name__})
        post={'all_inputs_unchanged':not changed,'count':len(paths),'mismatches':changed}
        terminal={'completed_queries':completed,'pending_query_count':len(req['formations'])*len(req['modes'])-len(completed),
            'pre2026_parity_queries':parity,'original_error':None if original is None else {'type':type(original).__name__,'message':str(original)},
            'postcheck':post,'persistence_errors':persistence}
        for name,value in (('input-postcheck.json',post),('terminal.json',terminal)):
            try:write_once(out/name,value)
            except BaseException as exc:persistence.append(name+':'+type(exc).__name__)
    if original is not None:raise original
    need(not changed and not persistence,'unchanged asset availability inputs and complete persistence')
    result={'status':'FULL_COHORT_ASSET_AVAILABILITY_THROUGH2026_COMPLETE_PENDING_SEPARATE_QA',
        'request_sha256':expected_sha,'document_count':len(req['documents']),'cohort_count':len(req['cohort']),
        'queries':completed,'pre2026_parity_queries':parity,'source_cutoff':source.CUTOFF,'all_inputs_unchanged':True,
        'formation_calendar_last_actual_session':(base/CALENDAR).read_text().splitlines()[-1] if 'source/'+CALENDAR in paths else None,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'current_business_identity_verified':False,
        'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        'market_values_read':False,'investment_rule_changed':False,'objective_achieved':False}
    write_once(out/'summary.json',result);return result


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','membership-file','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args();run(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),
        Path(a.request).resolve(),a.expected_request_sha256)


if __name__=='__main__':main()
