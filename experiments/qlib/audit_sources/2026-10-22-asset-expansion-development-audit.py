"""Separate same-edition expansion/native-quote QA; no production imports.
Reuses the prior separate signed-order/cash/normalized-account checker.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
from fractions import Fraction
import importlib.util
from pathlib import Path

helper=Path(__file__).with_name('2026-10-22-gross-profitability-development-audit.py')
spec=importlib.util.spec_from_file_location('prior_separate_daily_account_qa',helper)
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
read,sha,digest,need,near,inventory=qa.read,qa.sha,qa.digest,qa.need,qa.near,qa.inventory
PRIMARY='low_asset_expansion_decile_conditional'
HIGH='high_asset_expansion_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',HIGH)
SOURCE='annual-total-assets-all1236-v1-20261022'


def formations(base,req,run,quotes):
    cases=read(base/SOURCE/'case_results.json');targets=read(run/'targets.json');receipts=read(run/'formation_receipts.json')
    need(len(receipts)==len(req['formations'])==24,'all24 explicit monthly formations')
    memberships=defaultdict(list)
    for line in (base/qa.PROVIDER/'instruments/csi500.txt').read_text().splitlines():
        code,first,last=line.split();memberships[code].append((first,last))
    ratios=0;rows_checked=0;details=[]
    for q,receipt in zip(req['formations'],receipts):
        execution,previous=q['execution_session'],q['as_of'][:10];clock=datetime.fromisoformat(q['as_of'])
        view=read(base/qa.SOURCE/(execution+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
        need(datetime.fromisoformat(view['as_of'])==clock and view['visibility_mode']=='RECONSTRUCTED_PUBLICATION_DAY_END'
             and [r['instrument'] for r in view['classifications']]==req['cohort'],'same whole-cohort metadata-only selection view')
        active={c for c in req['cohort'] if any(a<=previous<=b for a,b in memberships[c])}
        minimum=int(previous[:4])-(2 if previous[5:7]<='06' else 1)
        admission=[];scores={};evidence={}
        for row in view['classifications']:
            code=row['instrument'];reason=None
            if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif 'selected_capture_key' not in row:
                need(row['annual_status'] in ('NO_VISIBLE_ANNUAL_REPORT','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'),'explicit unresolved metadata')
                reason=row['annual_status']
            elif row['latest_fiscal_year']<minimum:reason='STALE_ANNUAL_ASSETS'
            if reason is None:
                case=cases[row['selected_capture_key']]
                need(case['instrument']==code and case['fiscal_year']==row['latest_fiscal_year']
                     and case['source_sha256']==row['selected_source_sha256'],'unchanged latest asset edition')
                report=case['asset_report']
                if report is None:
                    need(case['status'] in ('ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED'),'latest failure cannot backfill older values')
                    reason='LATEST_'+case['status']
                else:
                    need(case['status']=='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA' and report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'})
                         and datetime.fromisoformat(report['public_day_end_at'])<=clock and report['publication_day']==row['latest_publication_day']
                         and report['instrument']==code and report['report_year']==row['latest_fiscal_year']
                         and report['payload']['document_sha256']==row['selected_source_sha256'],'visible one-document current annual source')
                    year=row['latest_fiscal_year'];current,prior=f'{year}-12-31',f'{year-1}-12-31'
                    balances=report['payload']['balances'];need(current in balances and set(balances)<={current,prior},'only exact adjacent annual columns')
                    if prior not in balances:reason='LATEST_HAS_NO_EXPLICIT_PRIOR_YEAR_END'
                    else:
                        values={}
                        for column,period in enumerate((current,prior)):
                            c=balances[period];need(c['column_index']==column and c['fiscal_end']==period
                                and c['statement']=='合并资产负债表' and c['row_text_sha256']==digest(c['row_text']),'explicit asset column identity')
                            value=Fraction(c['literal'].replace(',',''))*{'元':1,'万元':10000}[c['unit']]
                            need(value>0 and value==Fraction(c['value_CNY']),'exact independent normalized assets')
                            values[period]=value
                        price=[quotes.value(code,f,previous,as_of=previous) for f in ('close','volume','factor')]
                        if any(v is None or v<=0 for v in price):reason='NO_POSITIVE_FORMATION_QUOTE'
                        else:
                            scores[code]=(values[current]-values[prior])/values[prior];ratios+=1
                            evidence[code]={'record_id':report['record_id'],'source_sha256':row['selected_source_sha256'],
                                'capture_key':row['selected_capture_key'],'report_year':year,'current_fiscal_end':current,'prior_fiscal_end':prior,
                                'publication_day':report['publication_day'],'expansion_fraction':str(scores[code])}
                            reason='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'
            admission.append({'instrument':code,'reason':reason});rows_checked+=1
        need(len(scores)>=100,'registered100-name structural diversification floor')
        n=len(scores)//10
        selected={PRIMARY:sorted(scores,key=lambda c:(scores[c],c))[:n],
            'eligible_equal_weight':sorted(scores),HIGH:sorted(scores,key=lambda c:(-scores[c],c))[:n]}
        need(receipt['cohort_admission']==admission and receipt['ranked_source']==evidence and receipt['selections']==selected
             and receipt['eligible']==len(scores) and receipt['formation_members']==len(active)
             and receipt['admission_counts']==dict(Counter(r['reason'] for r in admission))
             and receipt['minimum_fiscal_year']==minimum and receipt['latest_factor_price_read']==previous,
             'independent expansion admission/rank/evidence receipts')
        near(receipt['eligible_fraction_of_active_initial_cohort'],len(scores)/len(active),'reported full active-cohort coverage')
        for name,chosen in selected.items():
            target=targets[name][execution];need(target['as_of']==previous and list(target['weights'])==chosen,'exact ordered monthly targets')
            for weight in target['weights'].values():near(weight,.95/len(chosen),'equal95% allocation')
        need(read(run/'formations'/(execution+'.json'))=={'targets':{n:targets[n][execution] for n in NAMES},'receipt':receipt},'persisted completed formation')
        details.append({'execution_session':execution,'eligible':len(scores),'primary_names':selected[PRIMARY]})
    return {'formation_count':24,'cohort_formation_rows_checked':rows_checked,'exact_eligible_asset_expansions_checked':ratios,'formations':details}


def main():
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root,base,membership,request,run,output=(Path(getattr(a,k)).resolve() for k in
        ('repo_root','source_root','membership_file','request','run_dir','output'))
    need(not output.exists() and not output.is_relative_to(run),'fresh external expansion QA output')
    need(sha(request)==a.expected_request_sha256,'frozen asset-expansion request')
    req=read(request);paths=qa.input_paths(req,root,base,membership,request)
    expected={**req['input_sha256'],'frozen_request':a.expected_request_sha256}
    for key,path in paths.items():need(sha(path)==expected[key],'input before '+key)
    helper_hash=sha(helper);old_audit=read(root/'experiments/qlib/gross-profitability-pre2026-audit.json')
    need(helper_hash==old_audit['audit_code_sha256'],'exact previously calibrated signed-order/cash checker')
    outputs=inventory(run);summary=read(run/'summary.json');terminal=read(run/'terminal.json')
    need(len(outputs)==79 and read(run/'input-before.json')==expected and not terminal['pending_profiles']
         and terminal['original_error'] is None and not terminal['persistence_errors'] and terminal['postcheck']['all_inputs_unchanged'],
         'complete79-file six-profile run/terminal')
    quotes=qa.QuoteReader(base/qa.PROVIDER);formed=formations(base,req,run,quotes)
    states={}
    for path in (base/qa.GAPS/'codes').glob('*.json'):
        packet=read(path);states[packet['instrument']]={r['date']:r for r in packet['rows']}
    accounts={}
    for extra in (20,40):
        for name in NAMES:
            label=str(extra)+'/'+name;metrics=read(run/label/'metrics.json')
            need(metrics==summary['results_by_extra_bps_and_family'][label],'published source metrics identity')
            accounts[label]=qa.audit_account(run/label,quotes,extra,metrics,states)
    primary=accounts['40/'+PRIMARY]
    selected=PRIMARY if min(primary['2024_return_pct'],primary['2025_return_pct'])>0 and primary['average_exposure_pct']>=90 and primary['unverified_held_marks']==0 else None
    need(summary['selected_development_lead']==selected,'fixed primary-only40bp gate')
    for flag in ('raw_share_execution_verified','investment_factor_admitted','2026_financial_or_market_values_read','sealed_evidence','objective_achieved'):
        need(summary[flag] is False,'explicit conditional engineering evidence limit')
    for key,path in paths.items():need(sha(path)==expected[key],'input after '+key)
    need(inventory(run)==outputs and sha(helper)==helper_hash,'all output/helper bytes unchanged through QA')
    result={'status':'SEPARATE_EXPANSION_RANKS_AND_SIX_DAILY_ACCOUNT_AUDIT_PASSED_NOT_RAW_CONFIRMATION',
        'audit_code_sha256':sha(Path(__file__)),'prior_separate_daily_account_checker_sha256':helper_hash,
        'request_sha256':a.expected_request_sha256,'input_count':len(paths),'input_binding_digest':digest(expected),
        'all_output_sha256':outputs,'all_inputs_and_outputs_unchanged':True,'formation_audit':formed,'account_audits':accounts,
        'native_unique_scalar_quotes_read':len(quotes.cache),'no_production_imports':True,'shared_prior_separate_account_QA':True,
        'same_researcher_after_source_execution_started':True,'all_original_annual_PDFs_reextracted':False,
        'prior_close_sizing_independently_reimplemented':False,'raw_share_execution_verified':False,
        'selected_development_lead':selected,'objective_achieved':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:qa.json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(qa.json.dumps({'status':result['status'],'selected_development_lead':selected,
        'formation_rows_checked':formed['cohort_formation_rows_checked'],'accounts_checked':len(accounts),
        'holding_rows_checked':sum(v['holding_rows_checked'] for v in accounts.values())}))


if __name__=='__main__':main()
