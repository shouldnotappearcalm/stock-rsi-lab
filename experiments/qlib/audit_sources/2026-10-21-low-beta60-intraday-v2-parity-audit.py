"""Local stdlib byte-parity validation, no account engine imports or runs."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser()
for n in ('original-dir','guarded-dir','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();old,new=Path(a.original_dir),Path(a.guarded_dir);repo=Path(__file__).resolve().parents[3]
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
read=lambda f:json.loads(Path(f).read_text())
o,n=read(old/'summary.json'),read(new/'summary.json')
pf=repo/'experiments/qlib/low-beta60-intraday-development-v2-parity-plan.json';plan=read(pf)
assert sha(pf)=='f51a73fe0b4c5203a08d0d6955ea29d278c59cee5ee072f4fbf015d303fc5281'
assert n['plan_sha256']==sha(pf) and n['method_code_sha256']==plan['method_code_sha256']
assert sha(old/'summary.json')==plan['original_run_summary_sha256']==n['original_run_summary_sha256']
assert o['plan_sha256']==plan['original_plan_sha256']==n['original_plan_sha256']=='fff4f3f26f0dd5e99f99d63cd0c77f899e8397e098a9e59a4b298f3e234fc8c0'
for f,h in plan['method_code_sha256'].items():assert sha(repo/f)==h
assert set(o['results_by_profile'])==set(n['results_by_profile'])=={f'{p}/{e}' for p in (100,500,1000) for e in (20,40)}
expected={'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}
checks={}
for profile,r in o['results_by_profile'].items():
 assert set(r['artifact_sha256'])==expected and r==n['results_by_profile'][profile]
 for f,h in r['artifact_sha256'].items():
  assert sha(old/profile/f)==sha(new/profile/f)==h==n['results_by_profile'][profile]['artifact_sha256'][f]
  checks[profile+'/'+f]=h
assert len(checks)==42
for f in ('derived_events.json','event_source_receipts.json','case_results.json'):assert sha(old/f)==sha(new/f)
assert n['all_42_accounting_files_byte_identical_to_original'] is True and all(n['parity_by_profile'].values())
assert o['raw_development_confirmation_passes']==n['raw_development_confirmation_passes']==True
assert not n['2026_strategy_returns_queried'] and not n['candidate_promoted'] and not n['objective_achieved']
v={'status':'INDEPENDENT_V2_SOURCE_IO_RETENTION_CONTROL_ALL42_LEDGER_FILES_BYTE_IDENTICAL',
 'audit_code_sha256':sha(__file__),'v2_plan_sha256':sha(pf),'original_summary_sha256':sha(old/'summary.json'),
 'guarded_summary_sha256':sha(new/'summary.json'),'accounting_files_checked':42,'all_profile_metadata_identical':True,
 'source_events_receipts_and_case_results_byte_identical':True,'imports_project_code':False,'replayed_account':False,
 'v2_does_not_change_original_account_economics':True,'account_file_sha256':checks,
 '2026_returns_computed':False,'new_source_calls':0,'candidate_promoted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(v,indent=2)+'\n')
print('Independent42ledgerfiles and all6profile metadata byte parity passed; no source/account calls')
