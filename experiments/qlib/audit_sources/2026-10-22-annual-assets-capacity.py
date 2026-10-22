"""Metadata-only latest-edition asset capacity; no price/ratio/rank or strategy."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)


def main():
    root=Path(__file__).resolve().parents[3]
    base=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
    qa_path=root/'experiments/qlib/annual-assets-all1236-source-audit.json';qa=read(qa_path)
    source=base/'annual-total-assets-all1236-v1-20261022/case_results.json'
    need(sha(source)==qa['all_output_sha256']['case_results.json'],'complete independently audited new asset cases')
    old_request=root/'experiments/qlib/gross-profitability-pre2026-request.json'
    need(sha(old_request)=='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5','immutable existing metadata-view closure')
    parent=read(old_request);cases=read(source)
    paths={'source/annual-total-assets-all1236-v1-20261022/case_results.json':source,
        'repo/experiments/qlib/annual-assets-all1236-source-audit.json':qa_path,
        'repo/experiments/qlib/gross-profitability-pre2026-request.json':old_request}
    membership=base/'qlib-price-delay-pre2026-clock-v2-20261021/instruments/csi500.txt'
    key='source/qlib-price-delay-pre2026-clock-v2-20261021/instruments/csi500.txt'
    need(sha(membership)==parent['input_sha256'][key],'same historical membership source');paths[key]=membership
    intervals={}
    for line in membership.read_text().splitlines():
        c,a,b=line.split();intervals.setdefault(c,[]).append((a,b))
    results=[]
    for q in parent['formations']:
        key='source/gross-profitability-monthly-availability-v1-20261022/'+q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'
        path=base/key[7:];need(sha(path)==parent['input_sha256'][key],'same audited metadata selection receipt');paths[key]=path
    expected={k:sha(v) for k,v in paths.items()}
    for q in parent['formations']:
        key='source/gross-profitability-monthly-availability-v1-20261022/'+q['execution_session']+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'
        view=read(paths[key]);day=q['as_of'][:10];counts=Counter();active=Counter();nonfinancial=Counter();nonfinancial_active=Counter()
        need(datetime.fromisoformat(view['as_of'])==datetime.fromisoformat(q['as_of'])
             and [r['instrument'] for r in view['classifications']]==parent['cohort'],'complete same clock/cohort metadata')
        for row in view['classifications']:
            if 'selected_capture_key' not in row:status=row['annual_status']
            else:
                case=cases[row['selected_capture_key']]
                need(case['instrument']==row['instrument'] and case['fiscal_year']==row['latest_fiscal_year']
                     and case['source_sha256']==row['selected_source_sha256'],'latest edition identity independent of GP parse status')
                report=case['asset_report']
                if report is None:status='LATEST_'+case['status']
                else:
                    need(datetime.fromisoformat(report['public_day_end_at'])<=datetime.fromisoformat(q['as_of']), 'no future public asset payload')
                    status='LATEST_EXPLICIT_TWO_YEAR_ASSETS' if len(report['payload']['balances'])==2 else 'LATEST_CURRENT_ONLY_ASSETS'
            member=any(a<=day<=b for a,b in intervals.get(row['instrument'],()))
            nf=row['industry_status']=='NONFINANCIAL_IN_SOURCE_VINTAGE'
            counts[status]+=1
            if member:active[status]+=1
            if nf:nonfinancial[status]+=1
            if member and nf:nonfinancial_active[status]+=1
        need(sum(counts.values())==394,'all394 source issuers retained')
        results.append({**q,'full394_status_counts':dict(counts),'active_initial_cohort_status_counts':dict(active),
            'reported2021_nonfinancial_status_counts':dict(nonfinancial),'active_reported2021_nonfinancial_status_counts':dict(nonfinancial_active)})
    for k,path in paths.items():need(sha(path)==expected[k],'source unchanged after capacity check '+k)
    result={'status':'LATEST_ANNUAL_ASSET_SOURCE_CAPACITY_NOT_INVESTMENT_ELIGIBILITY','input_sha256':expected,
        'discovery_code_sha256':sha(Path(__file__)),'all_read_source_inputs_unchanged':True,'cohort_count':394,'queries':results,
        'metadata_selection_reused_before_GP_numeric_status_filter':True,'asset_growth_values_or_ranks_computed':False,
        'freshness_or_price_eligibility_applied':False,'price_features_read':False,'portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'new_strategy_registered':False,'current_business_identity_verified':False,'objective_achieved':False}
    out=root/'experiments/qlib/annual-assets-latest-capacity-discovery.json'
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    field='LATEST_EXPLICIT_TWO_YEAR_ASSETS'
    print('latest paired assets,2021nonfinancial full:',min(r['reported2021_nonfinancial_status_counts'].get(field,0) for r in results),max(r['reported2021_nonfinancial_status_counts'].get(field,0) for r in results))
    print('latest paired assets,2021nonfinancial active:',min(r['active_reported2021_nonfinancial_status_counts'].get(field,0) for r in results),max(r['active_reported2021_nonfinancial_status_counts'].get(field,0) for r in results))


if __name__=='__main__':main()
