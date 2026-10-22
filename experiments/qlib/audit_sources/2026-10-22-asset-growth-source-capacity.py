"""Read-only paired-year capacity discovery; no scores,prices,returns or policy.
Existing GP parser support underestimates possible balance-sheet-only coverage.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)


def main():
    root=Path(__file__).resolve().parents[3]
    base=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
    request=root/'experiments/qlib/gross-profitability-pre2026-request.json'
    request_sha='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5'
    need(sha(request)==request_sha,'same immutable GP data inventory')
    req=read(request);paths={
        'source/gross-profitability-all1236-header-v7-20261022/case_results.json':base/'gross-profitability-all1236-header-v7-20261022/case_results.json',
        'source/qlib-price-delay-pre2026-clock-v2-20261021/instruments/csi500.txt':base/'qlib-price-delay-pre2026-clock-v2-20261021/instruments/csi500.txt'}
    for q in req['formations']:
        name='gross-profitability-monthly-availability-v1-20261022/'+q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'
        paths['source/'+name]=base/name
    for key,path in paths.items():need(sha(path)==req['input_sha256'][key],'existing audited source identity '+key)
    cases=read(next(p for k,p in paths.items() if k.endswith('/case_results.json')))
    memberships={}
    for line in (base/'qlib-price-delay-pre2026-clock-v2-20261021/instruments/csi500.txt').read_text().splitlines():
        code,a,b=line.split();memberships.setdefault(code,[]).append((a,b))
    results=[]
    for q in req['formations']:
        day=q['as_of'][:10]
        view=read(base/'gross-profitability-monthly-availability-v1-20261022'/(q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
        counts=Counter();active=Counter()
        for row in view['classifications']:
            code=row['instrument'];reason=None
            if row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif row['annual_status']!='LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED':reason=row['annual_status']
            else:
                c=cases[row['selected_capture_key']];year=row['latest_fiscal_year'];records=c['source_observations']
                current=[r for r in records if r['fiscal_end']==f'{year}-12-31']
                prior=[r for r in records if r['fiscal_end']==f'{year-1}-12-31']
                need(len(current)==1,'one same-case current annual observation')
                current=current[0];balance=current['payload']['cells']['total_assets']
                if balance.get('comparative_date_is_unresolved'):reason='UNDATED_OPENING_COLUMN_NOT_ANNUAL_PRIOR'
                elif balance.get('reported_comparative_balance_date')==f'{year}-01-01':reason='EXPLICIT_JAN1_NOT_PRIOR_DEC31'
                elif len(prior)!=1:reason='NO_SAME_EDITION_PRIOR_YEAR_OBSERVATION'
                else:
                    previous=prior[0];p=previous['payload'];now=current['payload']
                    need(p['document_sha256']==now['document_sha256']==row['selected_source_sha256']
                         and p['announcement_id']==now['announcement_id'] and p['column_role']=='COMPARATIVE'
                         and previous['public_day_end_at']==current['public_day_end_at']
                         and balance['reported_comparative_balance_date']==previous['fiscal_end'],
                         'coherent explicit prior column in the same visible annual edition')
                    reason='SAME_EDITION_EXPLICIT_PRIOR_DEC31_AVAILABLE_NOT_RANKED'
            counts[reason]+=1
            if any(a<=day<=b for a,b in memberships.get(code,())):active[reason]+=1
        need(sum(counts.values())==394,'full source cohort retained')
        results.append({**q,'full394_status_counts':dict(counts),'active_initial_cohort_status_counts':dict(active)})
    for key,path in paths.items():need(sha(path)==req['input_sha256'][key],'source unchanged after capacity discovery')
    need(sha(request)==request_sha,'request unchanged after discovery')
    result={'status':'EXISTING_PARSER_PAIRED_BALANCE_CAPACITY_DISCOVERY_ONLY',
        'discovery_code_sha256':sha(Path(__file__)),'parent_GP_request_sha256':request_sha,
        'source_files_read':len(paths),'input_sha256':{k:req['input_sha256'][k] for k in paths},
        'all_read_source_inputs_unchanged':True,'queries':results,'cohort_count':394,
        'asset_growth_values_or_ranks_computed':False,'price_features_read':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'new_strategy_registered':False,
        'scope_limit':'Counts only current GP-supported editions. GP parsing requires revenue and cost; missing paired observations do not prove absence of usable balance-only asset cells.',
        'current_business_identity_verified':False,'complete_financial_history_verified':False,'objective_achieved':False}
    out=root/'experiments/qlib/asset-growth-source-capacity-discovery.json'
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    key='SAME_EDITION_EXPLICIT_PRIOR_DEC31_AVAILABLE_NOT_RANKED'
    print('existing paired source capacity,full394:',min(r['full394_status_counts'].get(key,0) for r in results),max(r['full394_status_counts'].get(key,0) for r in results))
    print('existing paired source capacity,active:',min(r['active_initial_cohort_status_counts'].get(key,0) for r in results),max(r['active_initial_cohort_status_counts'].get(key,0) for r in results))


if __name__=='__main__':main()
