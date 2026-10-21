"""Score all six conditional ledgers only after independently bound reconstruction."""
import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
from scripts.fundamental_query_journal import file_sha
from scripts.run_low_beta60_horizon_account import fixed_interval_returns, ARTIFACTS
from scripts.run_low_beta60_issuer_schedule_scenario import CAPITAL, END, OUTPUT

PROFILES = {f'{p}/{c}' for p in (100,500,1000) for c in (20,40)}
AUDIT_FLAGS = ('all_six_accounts_reconstructed','original_269_events_unchanged',
    'original_42_financial_prefixes_identical','exact_single_conditional_event_only')


def score(root,audit_path,expected_audit_sha):
    root=Path(root);audit_path=Path(audit_path)
    if file_sha(audit_path) != expected_audit_sha:raise ValueError('independent output audit bytes changed')
    audit=json.loads(audit_path.read_bytes());summary=json.loads((root/'summary.json').read_bytes())
    if (audit['summary_sha256'] != file_sha(root/'summary.json') or audit['plan_sha256'] != summary['plan_sha256']
            or any(audit[k] is not True for k in AUDIT_FLAGS)
            or audit['portfolio_returns_computed'] is not False or audit['critical_or_important_findings'] != 0
            or set(audit['profiles']) != PROFILES or set(summary['results_by_profile']) != PROFILES
            or summary['all_profiles_complete'] is not True or summary['source_events_changed'] is not False
            or summary['statutory_exemption_verified'] is not False or summary['portfolio_returns_computed'] is not False):
        raise ValueError('complete independent six-account reconstruction and unchanged prefix evidence required')
    validated={}
    for label,case in summary['results_by_profile'].items():
        if case['status'] != 'CONDITIONAL_ENGINEERING_ACCOUNT_COMPLETE_UNSCORED':raise ValueError('incomplete account cannot be scored')
        if set(case['artifact_sha256']) != {*ARTIFACTS.values(),'scenario_ledger.json'}:raise ValueError('all eight authenticated financial artifacts required')
        for name,h in case['artifact_sha256'].items():
            if Path(name).name != name or file_sha(root/label/name) != h:raise ValueError('audited financial artifact changed')
        with (root/label/'daily.csv').open() as stream:rows=list(csv.DictReader(stream))
        if len(rows) != 676 or rows[0]['day'] != '2023-12-29' or rows[-1]['day'] != END:raise ValueError('complete fixed source horizon required')
        dates=[r['day'] for r in rows]
        if dates != sorted(set(dates)) or not {'2024-12-31','2025-12-31'} <= set(dates):raise ValueError('complete unique continuous financial dates required')
        if any(not Decimal(r['equity']).is_finite() or Decimal(r['equity']) <= 0 or not Decimal(r['exposure']).is_finite() for r in rows):raise ValueError('finite financial observations required')
        validated[label]=rows
    # No profile ROI is computed until ALL six profiles and ALL artifacts validate.
    results={}
    for label,rows in validated.items():
        values=fixed_interval_returns(rows,CAPITAL);peak=Decimal(CAPITAL);dd=Decimal(0)
        for row in rows[1:]:
            nav=Decimal(row['equity']);peak=max(peak,nav);dd=min(dd,nav/peak-1)
        results[label]={'status':'CONDITIONAL_ENGINEERING_DIAGNOSTIC_AUDITED',**values,
            'max_drawdown_pct':float(dd*100),'average_exposure_pct':float(sum((Decimal(r['exposure']) for r in rows[1:]),Decimal(0))/675*100),
            'statutory_exemption_verified':False,'scenario_classification':summary['scenario_classification']}
    return {'status':'SIX_CONDITIONAL_ACCOUNTS_SCORED_AFTER_INDEPENDENT_RECONSTRUCTION','window':summary['window'],
        'initial_CNY':CAPITAL,'results_by_profile':results,'account_summary_sha256':file_sha(root/'summary.json'),
        'independent_audit_sha256':expected_audit_sha,'plan_sha256':summary['plan_sha256'],
        'all_six_meet_numeric_conditions_at_interim_cutoff':all(r['three_numeric_conditions_met_at_interim_cutoff'] for r in results.values()),
        'source_queries':0,'portfolio_returns_computed':True,'statutory_exemption_verified':False,
        'full_October_complete':False,'sealed_evidence':False,'candidate_promoted':False,'objective_achieved':False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('source-root','audit','expected-audit-sha256','output'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args(argv);root=Path(a.source_root)/OUTPUT;out=Path(a.output)
    if out.exists():raise ValueError('preserve existing score result')
    result=score(root,a.audit,a.expected_audit_sha256)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['results_by_profile'],indent=2))

if __name__=='__main__':main()
