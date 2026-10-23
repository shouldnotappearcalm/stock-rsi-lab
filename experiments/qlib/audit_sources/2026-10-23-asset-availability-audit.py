"""Stdlib-only reconstruction of all asset-edition joins; no production imports."""
import argparse,copy,hashlib,json
from collections import Counter
from datetime import date,datetime,time,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SUPPORTED='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA'
SUPPORTED_ROW='LATEST_ASSET_SOURCE_SUPPORTED_NOT_INVESTMENT_ADMITTED'
FAILURES={'ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED','SOURCE_PDF_EXTRACTION_UNSUPPORTED'}
FIELDS=('instrument','industry_status','industry_classification_period','current_business_identity_verified',
    'financial_version_history_complete','financial_reporting_compatibility_verified','investment_factor_admitted',
    'latest_fiscal_year','latest_publication_day','selected_edition_capture_keys','selected_capture_key','selected_source_sha256')
FLAGS=('current_business_identity_verified','financial_version_history_complete','financial_reporting_compatibility_verified','investment_factor_admitted')


def need(ok,message):
    if not ok:raise ValueError(message)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def utc(value):
    d=datetime.fromisoformat(value);need(d.tzinfo is not None,'explicit source timezone');return d.astimezone(timezone.utc)
def public(day):return datetime.combine(date.fromisoformat(day),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)


def expected_view(documents,cases,catalog,cohort,as_of,mode):
    need(mode in ('OBSERVED','RECONSTRUCTED_PUBLICATION_DAY_END'),'known QA visibility mode')
    clock=utc(as_of);sector_public,sector_observed=utc(catalog['public_content_available_by']),utc(catalog['observed_at'])
    sector_visible=clock>=(max(sector_public,sector_observed) if mode=='OBSERVED' else sector_public)
    sectors={r['stock_code']:r for r in catalog['records']} if sector_visible else {}
    eligible=[]
    for d in documents:
        publication,arrival=public(d['day']),utc(d['captured_at_utc'])
        need(publication<=arrival,'QA source chronology')
        if clock>=(max(publication,arrival) if mode=='OBSERVED' else publication):eligible.append(d)
    rows=[]
    for code in sorted(cohort):
        sector=sectors.get(code[2:])
        kind=('NOT_AVAILABLE_AT_CLOCK' if not sector_visible else 'NOT_IN_SOURCE_VINTAGE' if sector is None
            else 'FINANCIAL_IN_SOURCE_VINTAGE' if sector['sector_code']=='J' else 'NONFINANCIAL_IN_SOURCE_VINTAGE')
        row={'instrument':code,'industry_status':kind,'industry_classification_period':'2021Q3',**dict.fromkeys(FLAGS,False)}
        candidates=[d for d in eligible if d['instrument']==code]
        if not candidates:
            rows.append({**row,'annual_status':'NO_VISIBLE_ANNUAL_REPORT'});continue
        year=sorted({d['effective_fiscal_year'] for d in candidates})[-1]
        annual=[d for d in candidates if d['effective_fiscal_year']==year]
        day=sorted({d['day'] for d in annual})[-1]
        editions=sorted([d for d in annual if d['day']==day],key=lambda d:(int(d['announcement_id']),d['capture_key']))
        row.update(latest_fiscal_year=year,latest_publication_day=day,selected_edition_capture_keys=[d['capture_key'] for d in editions])
        if len({d['source_sha256'] for d in editions})!=1:
            rows.append({**row,'annual_status':'AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'});continue
        d=editions[0];c=cases[d['capture_key']]
        need(c['capture_key']==d['capture_key'] and c['instrument']==code and c['source_sha256']==d['source_sha256']
            and c.get('fiscal_year',c.get('metadata_fiscal_year'))==year,'QA selected original case identity')
        row.update(selected_capture_key=d['capture_key'],selected_source_sha256=d['source_sha256'],selected_source_status=c['status'])
        if c['status'] in FAILURES:
            need(c['asset_report'] is None,'QA failed latest source has no asset report')
            rows.append({**row,'annual_status':'LATEST_'+c['status']});continue
        need(c['status']==SUPPORTED,'QA known asset source state');r=c['asset_report']
        need(r['record_id']==digest({k:v for k,v in r.items() if k!='record_id'})
            and r['contract']=='CONSOLIDATED_ANNUAL_TOTAL_ASSETS_EDITION_V1' and r['instrument']==code
            and r['report_year']==year and r['publication_day']==day and utc(r['public_day_end_at'])==public(day)
            and utc(r['observed_at'])==utc(d['captured_at_utc']) and r['payload']['scope']=='CONSOLIDATED'
            and r['payload']['document_sha256']==d['source_sha256'] and r['payload']['announcement_id']==d['announcement_id'],
            'QA immutable current annual report and clocks')
        periods=sorted(r['payload']['balances']);current,prior=f'{year}-12-31',f'{year-1}-12-31'
        need(current in periods and set(periods)<={current,prior},'QA explicit dated annual balance periods')
        rows.append({**row,'annual_status':SUPPORTED_ROW,'asset_record_id':r['record_id'],
            'balance_periods':periods,'has_explicit_prior_year_end':prior in periods})
    return {'as_of':clock.isoformat(),'visibility_mode':mode,'cohort_count':len(cohort),'classifications':rows,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'source_only_no_asset_amounts_exposed':True,
        'security_ranking_or_portfolio_returns_computed':False}


def validate_view(actual,documents,cases,catalog,cohort,as_of,mode):
    need(actual==expected_view(documents,cases,catalog,cohort,as_of,mode),'independent full-cohort visibility and selected source reconstruction')
    need(all(actual[f] is False for f in ('historical_arrival_verified','investment_factor_admitted','security_ranking_or_portfolio_returns_computed'))
        and actual['source_only_no_asset_amounts_exposed'] is True,'strict source evidence flags')
    need(all(r[f] is False for r in actual['classifications'] for f in FLAGS),'strict row evidence flags')
    return actual


def receipt(q,mode,view):
    rows=view['classifications']
    return {**q,'mode':mode,'artifact':q['execution_session']+'-'+mode+'.json',
        'annual_status_counts':dict(Counter(r['annual_status'] for r in rows)),
        'industry_annual_status_counts':dict(Counter(r['industry_status']+'/'+r['annual_status'] for r in rows)),
        'supported_selected_reports':len([r for r in rows if 'asset_record_id' in r]),
        'explicit_paired_selected_reports':len([r for r in rows if r.get('has_explicit_prior_year_end') is True])}


def negative_controls(latest,early,documents,cases,catalog,cohort):
    checked=[]
    def reject(name,view,q,edit):
        altered=copy.deepcopy(view);edit(altered)
        try:validate_view(altered,documents,cases,catalog,cohort,q['as_of'],q['mode'])
        except ValueError:checked.append(name)
        else:raise ValueError('semantic negative not rejected: '+name)
    view,q=latest;rows=view['classifications'];supported=next(i for i,r in enumerate(rows) if 'asset_record_id' in r)
    failed=next(i for i,r in enumerate(rows) if r.get('selected_source_status') in FAILURES)
    reject('wrong_query_clock',view,q,lambda v:v.update(as_of='2026-10-21T07:05:00+00:00'))
    reject('omitted_source_cohort_member',view,q,lambda v:v['classifications'].pop())
    reject('forged_2021_sector',view,q,lambda v:v['classifications'][0].update(industry_status='FORGED_FINANCIAL_LABEL'))
    reject('monetary_payload_exposed',view,q,lambda v:v['classifications'][supported].update(total_assets_CNY='1.00'))
    reject('unsupported_latest_promoted_or_backfilled',view,q,lambda v:v['classifications'][failed].update(
        selected_capture_key='forged-older-edition',annual_status=SUPPORTED_ROW,asset_record_id='f'*64))
    reject('invented_or_erased_prior_year_end',view,q,lambda v:v['classifications'][supported].update(
        has_explicit_prior_year_end=not rows[supported]['has_explicit_prior_year_end']))
    view,q=early;d=next(d for d in documents if d['day'].startswith('2026'));i=cohort.index(d['instrument'])
    reject('future_2026_annual_edition_at_2025_close',view,q,lambda v:v['classifications'][i].update(
        selected_capture_key=d['capture_key'],selected_source_sha256=d['source_sha256'],latest_fiscal_year=d['effective_fiscal_year']))
    return checked


def main():
    p=argparse.ArgumentParser()
    for n in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();repo,base,membership,request,run,out=(Path(getattr(a,n)).resolve()
        for n in ('repo_root','source_root','membership_file','request','run_dir','output'))
    need(not out.exists() and not out.is_relative_to(run) and sha(request)==a.expected_request_sha256,'fresh QA and frozen request')
    req=read(request);need(req['document_count']==1636 and req['cohort_count']==394 and req['query_count']==68
        and req['pre2026_parity_query_count']==48 and req['network_permitted'] is False
        and req['market_values_permitted'] is False and req['ranking_or_returns_permitted'] is False
        and req['investment_rule_changed'] is False,'fixed source-only QA contract')
    expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256};paths={'frozen_source_request':request}
    for key in req['input_sha256']:
        if key=='membership':paths[key]=membership;continue
        prefix,name=key.split('/',1);need(prefix in ('repo','source') and not Path(name).is_absolute()
            and '..' not in Path(name).parts,'safe immutable source namespace')
        paths[key]=(repo if prefix=='repo' else base)/name
    for key,f in paths.items():need(sha(f)==expected[key],'input before '+key)
    codehash=sha(Path(__file__));outputs=inventory(run)
    for folder,qa,field in (
        ('annual-total-assets-all1236-v1-20261022','annual-assets-all1236-source-audit.json','all_output_sha256'),
        ('asset-expansion-2026-assets-20261023','asset-expansion-2026-assets-source-audit.json','all_original_extraction_output_sha256'),
        ('gross-profitability-2021Q3-industry-catalog-v1-20261022','profitability-2021Q3-industry-catalog-source-audit.json','all_output_sha256'),
        ('gross-profitability-monthly-availability-v1-20261022','profitability-monthly-availability-audit.json','all_output_sha256')):
        need(inventory(base/folder)==read(repo/'experiments/qlib'/qa)[field],'complete immutable parent output '+folder)
    cases=read(base/'annual-total-assets-all1236-v1-20261022/case_results.json');new=read(base/'asset-expansion-2026-assets-20261023/case_results.json')
    need(not set(cases)&set(new),'separate original source keys');cases.update(new)
    need(len(cases)==len(req['documents'])==1636 and set(cases)=={d['capture_key'] for d in req['documents']},'all original asset cases')
    olddocs=read(repo/'experiments/qlib/annual-assets-all1236-request.json')['documents']
    newdocs=[]
    for d in read(repo/'experiments/qlib/asset-expansion-2026-assets-request.json')['documents']:
        y=d['metadata_fiscal_year']
        if y is None:
            need(new[d['key']]['year_resolved_from_literal_cover'] is True,'existing source-authenticated literal annual year');y=new[d['key']]['fiscal_year']
        newdocs.append({**d,'capture_key':d['key'],'effective_fiscal_year':y})
    need(req['documents']==olddocs+newdocs,'independently reconstructed1636 metadata descriptors')
    cohort=sorted({c for c,start,end in (s.split() for s in membership.read_text().splitlines())
        if start<='2024-01-02'<=end and c.startswith(('SH60','SZ00'))})
    need(cohort==req['cohort'] and len(cohort)==394,'same dated complete cohort')
    days=(base/'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines()
    need(days==sorted(set(days)),'unique ordered explicit calendar')
    clocks=[{'execution_session':d,'as_of':days[i-1]+'T15:05:00+08:00'} for i,d in enumerate(days)
        if i and '2024-01-02'<=d<='2026-10-21' and d[:7]!=days[i-1][:7]]
    need(clocks==req['formations'] and len(clocks)==34,'all34 actual monthly calendar transitions')
    need(req['modes']==['OBSERVED','RECONSTRUCTED_PUBLICATION_DAY_END'],'both visibility modes')
    names={q['execution_session']+'-'+m+'.json' for q in clocks for m in req['modes']}
    need(set(outputs)==names|{'input-before.json','input-postcheck.json','terminal.json','summary.json'} and len(outputs)==72,
        'all and only72 actual output files')
    need(read(run/'input-before.json')==expected,'all consumed inputs bound before source joins')
    catalog=read(base/'gross-profitability-2021Q3-industry-catalog-v1-20261022/catalog.json');queries=[];parity=0;latest=None;early=None
    for q in clocks:
        for mode in req['modes']:
            name=q['execution_session']+'-'+mode+'.json';view=validate_view(read(run/name),req['documents'],cases,catalog,cohort,q['as_of'],mode)
            if q['execution_session']<'2026-01-01':
                old=read(base/'gross-profitability-monthly-availability-v1-20261022'/name)
                need(all(view[k]==old[k] for k in ('as_of','visibility_mode','cohort_count')),'legacy top query identity')
                need([{k:r.get(k) for k in FIELDS} for r in view['classifications']]
                    ==[{k:r.get(k) for k in FIELDS} for r in old['classifications']],'all old-window edition/industry fields unchanged')
                parity+=1
            queries.append(receipt(q,mode,view))
            if mode!='OBSERVED' and q['execution_session'].startswith('2026'):
                latest=(view,{**q,'mode':mode})
                if early is None:early=latest
    need(parity==48,'all48 old-window query selections checked')
    negatives=negative_controls(latest,early,req['documents'],cases,catalog,cohort)
    post,terminal,summary=(read(run/n) for n in ('input-postcheck.json','terminal.json','summary.json'))
    need(post=={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[]}
        and terminal['completed_queries']==queries and terminal['pending_query_count']==0
        and terminal['pre2026_parity_queries']==48 and terminal['original_error'] is None and not terminal['persistence_errors'],
        'complete independently reconstructed terminal and source postcheck')
    need(summary['queries']==queries and summary['pre2026_parity_queries']==48 and summary['document_count']==1636
        and summary['cohort_count']==394 and summary['source_cutoff']=='2026-10-21T15:05:00+08:00'
        and summary['formation_calendar_last_actual_session']==days[-1] and summary['request_sha256']==a.expected_request_sha256,
        'exact source summary clocks and all68 receipts')
    for flag in ('historical_arrival_verified','financial_version_history_complete','current_business_identity_verified',
        'investment_factor_admitted','security_ranking_or_portfolio_returns_computed','market_values_read','investment_rule_changed','objective_achieved'):
        need(summary[flag] is False,'strict summary source limit '+flag)
    for key,f in paths.items():need(sha(f)==expected[key],'input after '+key)
    need(inventory(run)==outputs and sha(Path(__file__))==codehash,'source outputs and separate QA code unchanged')
    result={'status':'SEPARATE_68_FULL_COHORT_ASSET_VISIBILITY_AND_48_LEGACY_SELECTION_QUERIES_PASSED_NOT_INVESTMENT_ADMISSION',
        'audit_code_sha256':codehash,'request_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),
        'queries_checked':68,'cohort_query_rows_checked':68*394,'pre2026_selection_parity_queries':48,'consumed_input_count':len(paths),
        'all_consumed_input_sha256':expected,'all_output_sha256':outputs,'all_consumed_inputs_and_outputs_unchanged':True,
        'semantic_negative_controls_rejected_without_artifact_hash_gate':negatives,'no_production_imports':True,
        'same_researcher_after_source_run':True,'historical_arrival_verified':False,'investment_factor_admitted':False,
        'source_PDF_text_redecoded':False,'market_values_or_security_ranks_or_portfolio_returns_computed':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print(result['status'],'rows',result['cohort_query_rows_checked'],'semantic negatives',len(negatives))


if __name__=='__main__':main()
