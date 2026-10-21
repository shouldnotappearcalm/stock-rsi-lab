"""Date permission only; authenticate all six development accounts before new features."""
import argparse,ast,hashlib,json
from pathlib import Path
from scripts.fundamental_query_journal import file_sha
from scripts.run_qlib_szse_value_momentum_pre2026 import METHOD_FILES as SCREEN_METHODS
from scripts.run_qlib_low_risk_goal_diagnostic_2026 import full_input_hashes
from scripts.run_qlib_low_risk_pre2026 import parse_memberships
from scripts.prepare_szse_value_frozen_2026_targets import load_extension
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.szse_monthly import load_capture
from stock_rsi.exchange_value_momentum_extended import build_targets

TARGET_END='2026-10-13';ACCOUNT_END='2026-10-20';CANDIDATE='szse_value_momentum_equal'
DEV='szse-value-momentum-intraday-dev-20261021'
FORM='szse-value-momentum-formations-pre2026-20261021'
MONTHLY='szse-monthly-pre2026-20261017';EXTENSION='szse-monthly-2026-extension-20261017'
PROVIDER='qlib-enhanced-2026-diagnostic'
DP='experiments/qlib/szse-value-momentum-intraday-plan.json'
SP='experiments/qlib/szse-value-momentum-pre2026-plan.json'
AUDIT='experiments/qlib/szse-value-momentum-intraday-ledger-audit.json'
REVIEW='experiments/qlib/szse-value-momentum-intraday-output-review.json'
METHOD_FILES=tuple(dict.fromkeys((*SCREEN_METHODS,
 'scripts/prepare_value_momentum_2026_targets.py','src/stock_rsi/exchange_value_momentum_extended.py',
 'scripts/run_qlib_low_risk_goal_diagnostic_2026.py','scripts/prepare_szse_value_frozen_2026_targets.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/fundamental_query_journal.py')))
PUBLIC_FILES=(DP,SP,AUDIT,REVIEW,'experiments/qlib/szse-value-momentum-intraday-results.json',
 'experiments/qlib/szse-value-momentum-intraday-verification.json',
 'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-intraday-audit.py',
 'docs/research/szse-value-momentum-2026-target-plan-2026-10-21.md')
LOCAL_FILES=(DEV+'/summary.json',FORM+'/targets.json',FORM+'/formation_receipts.json',
 MONTHLY+'/manifest.json',EXTENSION+'/manifest.json')

def read(p):return json.loads(Path(p).read_text())
def json_hash(v):return hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest()


def assert_cap_only_change(old,new):
 expected=old.replace('def build_targets(snapshot,memberships,reports,start=START,end=END):',
  'def build_targets(snapshot,memberships,reports,start=START,end=END,*,permitted_end=END):')
 expected=expected.replace("if start<START or start>end or end>END:raise ValueError('value/momentum development capped at2025')",
  "if start<START or start>end or end>permitted_end:raise ValueError('value/momentum exceeds explicit date permission')")
 if ast.dump(ast.parse(expected))!=ast.dump(ast.parse(new)):
  raise ValueError('investment method changed beyond explicit date permission')


def authenticate_development(base,repo,p):
 if (p['status']!='FROZEN_COMPOSITE_2026_TARGET_EXTENSION' or p['candidate']!=CANDIDATE
     or p['target_end']!=TARGET_END or p['planned_account_end']!=ACCOUNT_END or p['candidate_budget']!=1
     or set(p['method_code_sha256'])!=set(METHOD_FILES) or set(p['public_evidence_sha256'])!=set(PUBLIC_FILES)
     or set(p['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('one fixed composite, explicit feature permission and immutable development evidence required')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in p[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('fixed target input/method changed: '+n)
 dp=read(repo/DP);sp=read(repo/SP)
 for prior in (dp,sp):
  for n,h in prior['method_code_sha256'].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(repo/n)!=h:raise ValueError('original tested investment or execution code changed')
 dev=base/DEV;s=read(dev/'summary.json');audit=read(repo/AUDIT);review=read(repo/REVIEW)
 if (s['status']!='FIXED_COMPOSITE_PRE2026_INTRADAY_DEVELOPMENT_COMPLETE' or s['candidate']!=CANDIDATE
     or s['window']!=['2023-12-29','2025-12-31'] or s['raw_development_confirmation_passes'] is not True
     or s['plan_sha256']!=file_sha(repo/DP) or s['method_code_sha256']!=dp['method_code_sha256']
     or file_sha(dev/'summary.json')!=file_sha(repo/'experiments/qlib/szse-value-momentum-intraday-results.json')
     or audit['summary_sha256']!=file_sha(dev/'summary.json') or audit['development_confirmation_passes_independently'] is not True
     or audit['imports_project_code'] is not False or audit['all_profile_parent_child_fill_quantities_and_snapshots_reconstructed'] is not True
     or not audit['arithmetic_negative_controls_rejected'] or not all(audit['arithmetic_negative_controls_rejected'].values())
     or audit['audit_code_sha256']!=file_sha(repo/'experiments/qlib/audit_sources/2026-10-21-szse-value-momentum-intraday-audit.py')
     or audit['plan_sha256']!=file_sha(repo/DP) or audit['2026_return_computed'] is not False
     or s['2026_strategy_returns_queried'] is not False
     or review['ready_for_frozen_2026_source_extension'] is not True or review['no2026read'] is not True
     or review['plan_sha256']!=file_sha(repo/DP) or review['summary_sha256']!=file_sha(dev/'summary.json')
     or review['independent_audit_sha256']!=file_sha(repo/AUDIT)):
  raise ValueError('complete independently confirmed composite development required before2026 features')
 profiles={f'{x}/{c}' for x in (100,500,1000) for c in (20,40)}
 if set(s['results_by_profile'])!=profiles or set(audit['results_by_profile'])!=profiles:raise ValueError('all six frozen profiles required')
 for label,r in s['results_by_profile'].items():
  if (r['status']!='NESTED_EXECUTION_ACCOUNT_RECONCILED'
      or set(r['artifact_sha256'])!={'daily.csv','intents.json','parent_instructions.json','orders.json',
       'fills.json','corporate_ledger.json','ownership.json'}):raise ValueError('every complete development account must be valid')
  for n,h in r['artifact_sha256'].items():
   if Path(n).name!=n or file_sha(dev/label/n)!=h:raise ValueError('development financial prefix changed')
 assert_cap_only_change((repo/'src/stock_rsi/exchange_value_momentum.py').read_text(),
  (repo/'src/stock_rsi/exchange_value_momentum_extended.py').read_text())
 return s


def main(argv=None):
 parser=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+n,required=True)
 parser.add_argument('--development-preflight-only',action='store_true');a=parser.parse_args(argv)
 base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve prior target-extension attempt')
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen2026target plan changed')
 p=read(a.plan);authenticate_development(base,repo,p)
 if a.development_preflight_only:print('all six authenticated pre2026 accounts; no new feature/target/ROI/network',flush=True);return 0
 if full_input_hashes(base/PROVIDER)!=p['input_sha256']:raise ValueError('frozen provider changed')
 reports=load_capture(base/MONTHLY,p['development_monthly_manifest_sha256'])
 extra=load_extension(base/EXTENSION,p['extension_monthly_manifest_sha256'])
 if set(reports)&set(extra):raise ValueError('overlapping monthly sources')
 reports.update(extra);snapshot=QlibSnapshot(base/PROVIDER)
 if snapshot.calendar[-1].isoformat()!=TARGET_END:raise ValueError('source calendar permission boundary changed')
 memberships=parse_memberships((base/PROVIDER/'instruments/csi500.txt').read_text())
 targets,receipts=build_targets(snapshot,memberships,reports,end=TARGET_END,permitted_end=TARGET_END)
 before={n:{d:t for d,t in v.items() if d<'2026-01-01'} for n,v in targets.items()}
 prefix=[r for r in receipts if r['execution_session']<'2026-01-01']
 if json_hash(before)!=file_sha(base/FORM/'targets.json') or json_hash(prefix)!=file_sha(base/FORM/'formation_receipts.json'):
  raise ValueError('all original24 family targets and complete formation receipts must reproduce')
 chosen=targets[CANDIDATE]
 if (len(chosen)!=34 or len(receipts)!=34 or sorted(chosen)[-1]!='2026-10-09'
     or any(r['latest_factor_price_read']!=r['formation_asof'] for r in receipts)):
  raise ValueError('all34 causal monthly decisions andOctober target required')
 out.mkdir(parents=True)
 for n,v in (('targets.json',chosen),('family_targets.json',targets),('formation_receipts.json',receipts)):
  (out/n).write_text(json.dumps(v,indent=2)+'\n')
 result={'status':'FIXED_COMPOSITE_2026_TARGETS_PREPARED_NO_RETURNS','candidate':CANDIDATE,'candidate_budget':1,
  'plan_sha256':a.expected_plan_sha256,'months':34,'target_generation_calendar_end':TARGET_END,
  'latest_target_execution_session':max(chosen),'planned_interim_account_end':ACCOUNT_END,
  'requested_full_October_complete':False,'development_targets_and_receipts_prefix_reproduced':True,
  'permission_only_source_change_verified':True,'controls_promoted':False,
  'artifact_sha256':{f.name:file_sha(f) for f in sorted(out.iterdir())},'input_sha256':p['input_sha256'],
  'new_2026_factor_features_read':True,'2026_strategy_returns_queried':False,'account_replay_performed':False,
  'historical_arrival_verified':False,'sealed_evidence':False,'objective_achieved':False}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Composite34targets prepared; complete24-month prefix identical; no account/ROI/network',flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
