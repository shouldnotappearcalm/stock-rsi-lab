"""Verify a retained forward data-admission failure; no portfolio simulation."""
from pathlib import Path
import json,hashlib
ROOT=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def main():
 request=ROOT/'experiments/qlib/cash-accrual-horizon-target-request.json';expected='f8dfd4f7551ec31edd95eaf037094b6f2415d4400e6fdd866b23715e1b74477e';assert sha(request)==expected;req=read(request)
 out=BASE/'cash-accrual-targets-through2026-v1-20261028';t=read(out/'terminal.json');caps=tree(out)
 assert t['complete'] is False and t['2026_portfolio_returns_computed'] is False and t['investment_rule_changed'] is False
 assert t['error_type']=='ValueError' and 'fixed100-name guard' in t['error']
 assert t['all_inputs_unchanged'] and t['all_outputs_unchanged'] and caps=={**t['capture_sha256'],'terminal.json':sha(out/'terminal.json')}
 known={**req['input_sha256'],str(request):expected,str(Path(__file__).resolve()):sha(__file__)};assert all(sha(p)==h for p,h in known.items())
 old=read(ROOT/'experiments/qlib/cash-accrual-pre2026-targets.json');forms=[]
 for p in sorted((out/'formations').glob('*.json')):
  item=read(p);r=item['receipt'];assert len(r['cohort_admission'])==394 and len({v['instrument'] for v in r['cohort_admission']})==394
  count=sum(v['reason']=='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED' for v in r['cohort_admission']);assert count==r['eligible']==len(r['ranked_source'])
  assert r['coverage_pass']==(count>=100)
  if r['execution_session']<='2025-12-31':
   for name,targets in old.items():assert item['targets'][name]==targets[r['execution_session']]
  if not r['coverage_pass']:assert all(v is None for v in item['targets'].values()) and not r['selections']
  forms.append({'execution_session':r['execution_session'],'formation_asof':r['formation_asof'],'eligible':count,'coverage_pass':r['coverage_pass'],'admission_counts':r['admission_counts']})
 assert len(forms)==34 and sum(v['execution_session']<='2025-12-31' for v in forms)==24
 future=[v for v in forms if v['execution_session']>='2026-01-01'];failed=[v for v in future if not v['coverage_pass']];assert len(future)==10 and len(failed)==8
 assert not (out/'targets.json').exists() and all(sha(p)==h for p,h in known.items()) and tree(out)==caps
 result={'status':'PASS_RETAINED_FORWARD_DATA_ADMISSION_FAILURE_NO2026ROI','request_sha256':expected,'all_input_sha256':known,'all_output_sha256':caps,
  'all_inputs_outputs_unchanged':True,'old24targets_preserved_identically':True,'forward_months':future,'failed_forward_months':failed,
  '2026_account_return':None,'2026_portfolio_returns_computed':False,'coverage_guard_changed':False,'investment_rule_changed':False,'objective_achieved':False}
 local=BASE/'cash-accrual-forward-failure-audit-v1-20261028';assert not local.exists();local.mkdir();(local/'proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Retained8failed months;all24oldtargets identical;no2026ROI')
if __name__=='__main__':main()
