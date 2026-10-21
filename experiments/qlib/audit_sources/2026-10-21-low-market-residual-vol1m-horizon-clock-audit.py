"""Stdlib-only audit of frozen clock denial; no quote decoding or replay."""
import argparse
import copy
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

EXPECTED_PLAN='c5cdfdb602d7d233a374a08eefeebdefa3cec6b6a0890b27a57b22e63ff84301'
OLD_FACTOR='de2d29831b81d0e7078e482bdf429ea3388e47d7a2bc264bfec0841c20a602dd'
OUT='low-market-residual-vol1m-horizon-formations-20261021'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(value,reason):
 if not value:raise ValueError(reason)
def prior_month(key):
 y,m=key;return (y,m-1) if m>1 else (y-1,12)
def independent_clock(days):
 require(days==sorted(set(days)),'calendar not unique/ordered')
 groups=defaultdict(list)
 for d in days:groups[(d.year,d.month)].append(d)
 result=[]
 for key,execution_days in sorted(groups.items()):
  execution=execution_days[0]
  if not date(2024,1,2)<=execution<=date(2026,10,20):continue
  previous=prior_month(key);samples=groups.get(previous,[])
  require(samples and groups.get(prior_month(previous)),'missing full month or baseline')
  require(samples[-1]==max(d for d in days if d<execution),'month adjacency mismatch')
  n=len(samples);admitted=n>=15
  result.append({'execution_session':execution.isoformat(),'formation_asof':samples[-1].isoformat(),
   'return_month':'%04d-%02d'%previous,'sample_dates':[d.isoformat() for d in samples],
   'n':n,'minimum_return_observations':15,'admitted':admitted,
   'reason':None if admitted else 'complete_source_month_fewer_than_frozen_15_observations'})
 return result

def validate_semantics(clock,summary,failure,expected):
 require(clock==expected,'clock values differ from calendar mathematics')
 denied=[x for x in expected if not x['admitted']]
 require(len(expected)==34 and len(denied)==1 and denied[0]['execution_session']=='2026-03-02' and denied[0]['n']==14,'fixed denial expectation')
 require(summary['status']==failure['status']=='UNCHANGED_IVOL_CLOCK_ADMISSION_FAILED','wrong status')
 require(summary['actual_exit_code']==2 and summary['clock_months_checked']==34,'wrong termination')
 require(summary['denied_months']==failure['denied_months']==denied,'denial mismatched')
 for obj in (summary,failure):
  for k in ('new_2026_quote_values_decoded','targets_generated','portfolio_returns_computed','investment_rule_changed','objective_achieved'):
   require(obj[k] is False,'forbidden success flag '+k)
  require(not any(k in obj for k in ('annual_returns','annual_metrics','returns_2026','portfolio_returns','results_by_extra_bps')),'unexpected return payload')
 require(failure['full_provider_snapshot_constructed'] is False and failure['fallback_added'] is False,'snapshot/fallback claimed')

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo-root',required=True);p.add_argument('--source-root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 repo=Path(a.repo_root).resolve();base=Path(a.source_root).resolve();folder=base/OUT
 files={'summary.json','failure.json','clock_admission.json','input-before.json','input-postcheck.json'}
 require({x.name for x in folder.iterdir()}==files and all(x.is_file() and not x.is_symlink() for x in folder.iterdir()),'unexpected/missing outputs')
 summary=read(folder/'summary.json');failure=read(folder/'failure.json');clock=read(folder/'clock_admission.json');known=read(folder/'input-before.json');post=read(folder/'input-postcheck.json')
 request=repo/'experiments/qlib/low-market-residual-vol1m-horizon-formation-request.json';require(sha(request)==summary['plan_sha256']==EXPECTED_PLAN,'request hash');plan=read(request)
 require(known[str(request)]==EXPECTED_PLAN and len(known)==summary['bound_input_count']==5356,'input binding count')
 for name,h in known.items():
  path=Path(name).resolve();require(path.is_relative_to(base) or path.is_relative_to(repo),'input path outside roots');require(sha(path)==h,'changed input '+name)
 for field,root in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)]:
  for name,h in plan[field].items():require(known[str((root/name).resolve())]==h,'request map omitted')
 factor=repo/'src/stock_rsi/low_market_residual_vol.py';require(sha(factor)==OLD_FACTOR,'old factor changed')
 require(plan['minimum_return_observations']==15 and plan['on_inadmissible_month']=='FAIL_NO_SKIP_NO_CARRY_NO_PARAMETER_CHANGE','rule changed')
 cal=base/'qlib-enhanced-dev/calendars/day.txt';require(sha(cal)==plan['source_input_sha256']['calendars/day.txt'],'calendar checksum');days=[date.fromisoformat(s) for s in cal.read_text().splitlines()]
 require(days[-1]==date(2026,10,13),'calendar end');expected=independent_clock(days);validate_semantics(clock,summary,failure,expected)
 require(post=={'all_bound_inputs_unchanged':True,'full_provider_identity_and_pre2026_prefix_rechecked':True,'errors':[],'completed':True},'postcheck failed')
 require(summary['all_original_financial_evidence_preserved'] is True and summary['all_bound_inputs_unchanged'] is True,'preservation flags')
 require(set(summary['artifact_sha256'])==files-{'summary.json'},'artifact map')
 for n,h in summary['artifact_sha256'].items():require(sha(folder/n)==h,'changed output '+n)
 audit=read(repo/'experiments/qlib/low-market-residual-vol1m-regime-independent-account-audit.json')
 maps=[('completed26',audit['all_output_file_sha256'],base/'low-market-residual-vol1m-regime-raw-development-pre2026-20261021',26),('failed13',audit['old_failure_output_artifact_sha256'],base/'low-market-residual-vol1m-raw-development-pre2026-20261021',13),('old42',audit['old42_financial_sha256'],base/'low-market-residual-vol1m-budgeted-pre2026-development-20261021',42)]
 for label,mapping,root,count in maps:
  require(len(mapping)==count,'map count '+label)
  for n,h in mapping.items():
   path=(root/n).resolve();require(known[str(path)]==h and sha(path)==h,'preserved evidence '+label+':'+n)
 negative={}
 for name in ('n14_to_15','denial_marked_admitted','fake_2026_ROI'):
  c,s,f=copy.deepcopy(clock),copy.deepcopy(summary),copy.deepcopy(failure)
  if name=='n14_to_15':next(x for x in c if x['n']==14)['n']=15
  elif name=='denial_marked_admitted':next(x for x in c if x['n']==14)['admitted']=True
  else:s['portfolio_returns_computed']=True;s['annual_returns']={'2026':0.1}
  try:validate_semantics(c,s,f,expected)
  except ValueError:negative[name]=True
  else:raise ValueError('negative accepted '+name)
 report={'status':'PASS_INDEPENDENT_UNCHANGED_IVOL_CLOCK_DENIAL_AUDIT','script_sha256':sha(__file__),'request_sha256':EXPECTED_PLAN,'output_sha256':{n:sha(folder/n) for n in sorted(files)},'all5356_bound_inputs_actual_hash_verified':True,'completed26_failed13_old42_actual_bytes_preserved':True,'old_factor_sha256':OLD_FACTOR,'independently_reconstructed_clock_months':len(expected),'old_months':sum(x['execution_session']<'2026' for x in expected),'denied_months':[x for x in expected if not x['admitted']],'semantic_negative_controls_rejected':negative,'critical_or_important_findings':[],'production_imported':False,'QlibSnapshot_constructed':False,'2026_quote_values_decoded_by_audit':False,'production_replay_or_formation_run':False,'portfolio_returns_computed':False,'network_used':False,'source_or_repository_modified':False,'evidence_boundary':'Runtime zero-quote claim is supported by the reviewed denial branch and saved failure records, not independent OS access tracing or an OS future-data isolation certificate. Full provider and inputs are read as opaque bytes only for hashes. No successful horizon formation, portfolio test, PIT, arrival or objective approval.'}
 Path(a.output).write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n');print(json.dumps({'output':a.output,'sha256':sha(a.output),'status':report['status']}))
if __name__=='__main__':main()
