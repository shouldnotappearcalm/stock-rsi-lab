"""Extend the tested investment core only through an explicit date permission."""
import argparse,ast,hashlib,json
from pathlib import Path
from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.run_low_risk_intraday_replay import authenticate_development
from scripts.run_qlib_low_risk_goal_diagnostic_2026 import full_input_hashes
from scripts.run_qlib_low_risk_pre2026 import parse_memberships
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.szse_monthly import load_capture,parse_transactions,url_build_day
from stock_rsi.exchange_value_extended import build_targets

TARGET_END='2026-10-13'
METHOD_FILES=('scripts/prepare_szse_value_frozen_2026_targets.py','src/stock_rsi/exchange_value.py',
 'src/stock_rsi/exchange_value_extended.py','src/stock_rsi/szse_monthly.py','src/stock_rsi/return_families.py',
 'src/stock_rsi/low_risk_monthly.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
 'scripts/run_low_risk_intraday_replay.py','scripts/run_qlib_low_risk_goal_diagnostic_2026.py',
 'scripts/run_qlib_low_risk_pre2026.py','scripts/run_cninfo_orj_signal_pre2026.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py')

def json_hash(value):return hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()

def assert_cap_only_change(old,new):
 expected=old.replace('def build_targets(snapshot,memberships,reports,start=START,end=END):',
  'def build_targets(snapshot,memberships,reports,start=START,end=END,*,permitted_end=END):')
 expected=expected.replace("if start<START or start>end or end>END:raise ValueError('published-value development ends in2025')",
  "if start<START or start>end or end>permitted_end:raise ValueError('published-value exceeds explicit date permission')")
 if ast.dump(ast.parse(expected))!=ast.dump(ast.parse(new)):raise ValueError('investment method changed beyond date permission')

def load_extension(directory,expected_sha):
 root=Path(directory)
 if sha256_file(root/'manifest.json')!=expected_sha:raise ValueError('extension source identity changed')
 m=json.loads((root/'manifest.json').read_text())
 if (m['status']!='SZSE_MONTHLY_2026_EXTENSION_ORIGINAL_TABLES_CAPTURED'
     or m['source_reader_sha256']!=sha256_file(Path(__file__).resolve().parents[1]/'src/stock_rsi/szse_monthly.py')
     or sha256_file(root/'request.json')!=m['request_sha256']):raise ValueError('extension source method changed')
 for name,h in m['journal_artifact_sha256'].items():
  if sha256_file(root/name)!=h:raise ValueError('extension source journal changed')
 result={}
 for month,r in m['months'].items():
  for key in ('article','table','normalized'):
   if sha256_file(root/r[key+'_file'])!=r[key+'_sha256']:raise ValueError('extension source artifact changed')
  p=json.loads((root/r['normalized_file']).read_text());parsed=parse_transactions((root/r['table_file']).read_bytes(),month)
  if any(p[k]!=v for k,v in parsed.items()):raise ValueError('extension source parsing changed')
  if p['article_build_day']!=url_build_day(r['article_url']) or p['table_build_day']!=url_build_day(r['table_url']):raise ValueError('extension filename date changed')
  result[month]={**p,'table_sha256':r['table_sha256']}
 return result

def main(argv=None):
 parser=argparse.ArgumentParser()
 for name in ('provider-uri','source-dir','extension-dir','development-dir','development-audit','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+name,required=True)
 args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
 if out.exists():raise ValueError('fixed target output exists')
 if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('fixed target plan changed')
 p=json.loads(Path(args.plan).read_text())
 if (p['status']!='FROZEN_BEFORE_SZSE_VALUE_2026_TARGETS' or p['target_end']!=TARGET_END
     or set(p['method_code_sha256'])!=set(METHOD_FILES)
     or any(sha256_file(root/n)!=h for n,h in p['method_code_sha256'].items())):raise ValueError('fixed target method changed')
 for name,key in (('experiments/qlib/szse-value-intraday-development-plan.json','raw_development_plan_sha256'),
                  ('experiments/qlib/szse-value-pre2026-plan.json','original_screen_plan_sha256')):
  if sha256_file(root/name)!=p[key]:raise ValueError('tested development plan changed')
 dp=json.loads((root/'experiments/qlib/szse-value-intraday-development-plan.json').read_text())
 sp=json.loads((root/'experiments/qlib/szse-value-pre2026-plan.json').read_text())
 for prior_plan in (dp,sp):
  if any(sha256_file(root/n)!=h for n,h in prior_plan['method_code_sha256'].items()):raise ValueError('tested development dependency changed')
 assert_cap_only_change((root/'src/stock_rsi/exchange_value.py').read_text(),(root/'src/stock_rsi/exchange_value_extended.py').read_text())
 dev=Path(args.development_dir)
 authenticate_development(dev,{'development_summary_sha256':p['raw_development_summary_sha256'],'method_code_sha256':dp['method_code_sha256']})
 if sha256_file(args.development_audit)!=p['raw_development_audit_sha256']:raise ValueError('development audit changed')
 audit=json.loads(Path(args.development_audit).read_text());prior=json.loads((dev/'summary.json').read_text())
 if (audit['valid_profiles']!=60 or audit['raw_confirmation_passes_independently'] is not True
     or audit['replay_summary_sha256']!=p['raw_development_summary_sha256']
     or prior['plan_sha256']!=p['raw_development_plan_sha256'] or prior['raw_development_confirmation_passes'] is not True):raise ValueError('development confirmation absent')
 if full_input_hashes(args.provider_uri)!=p['input_sha256']:raise ValueError('price snapshot changed')
 reports=load_capture(args.source_dir,p['development_monthly_manifest_sha256'])
 extra=load_extension(args.extension_dir,p['extension_monthly_manifest_sha256'])
 if set(reports)&set(extra):raise ValueError('source month overlap')
 reports.update(extra)
 snapshot=QlibSnapshot(args.provider_uri);memberships=parse_memberships((Path(args.provider_uri)/'instruments/csi500.txt').read_text())
 targets,receipts=build_targets(snapshot,memberships,reports,end=TARGET_END,permitted_end=TARGET_END)
 before={n:{d:t for d,t in v.items() if d<'2026-01-01'} for n,v in targets.items()}
 old_receipts=[r for r in receipts if r['execution_session']<'2026-01-01']
 if json_hash(before)!=p['initial_family_targets_sha256'] or json_hash(old_receipts)!=p['initial_formation_receipts_sha256']:raise ValueError('historical targets or formation receipts changed')
 chosen=targets['szse_monthly_low_pe']
 if len(chosen)!=34 or len(receipts)!=34 or any(r['latest_factor_price_read']!=r['formation_asof'] for r in receipts):raise ValueError('complete causal monthly decisions required')
 out.mkdir(parents=True)
 for name,value in (('targets.json',chosen),('formation_receipts.json',receipts)):(out/name).write_text(json.dumps(value,indent=2)+'\n')
 result={'status':'FROZEN_SZSE_VALUE_2026_TARGETS_PREPARED','strategy':'szse_monthly_low_pe','months':34,
 'target_end':TARGET_END,'planned_account_end':'2026-10-16','development_prefix_reproduced':True,
 'permission_only_source_change_verified':True,'targets_sha256':sha256_file(out/'targets.json'),
 'formation_receipts_sha256':sha256_file(out/'formation_receipts.json'),'input_sha256':p['input_sha256'],
 'plan_sha256':args.expected_plan_sha256,'2026_features_read_within_each_formation_asof':True,
 '2026_strategy_returns_queried':False,'historical_arrival_verified':False,'sealed_evidence':False,'objective_achieved':False}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print('frozen value targets prepared',len(chosen),flush=True)
 return 0
if __name__=='__main__':raise SystemExit(main())
