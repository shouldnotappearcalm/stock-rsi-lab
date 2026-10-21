"""Minimal independent stdlib failure evidence audit. No account/scorer imports."""
import ast,copy,csv,hashlib,io,json,subprocess
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');O=B/'price-delay-raw-daily-horizon-20261021';OUT=Path('/tmp/price-delay-horizon-raw-account-failure-review-20261021.json')
REQ='b28c9d0e1d7def9b8aedeee29714a1f7de490b03c47667458445dc70dc2206de';CODE='SH600079';DAY='2026-03-31';NEXT='2026-04-01';PRE='2025-12-31'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def digest_bytes(data):return hashlib.sha256(data).hexdigest()
def serialized_hash(v):return digest_bytes((json.dumps(v,indent=2)+'\n').encode())
def no_annual(value):
 if isinstance(value,list):
  for v in value:no_annual(v)
 elif isinstance(value,dict):
  for k,v in value.items():
   assert not ('return_pct' in k or k in ('ending_equity','2026_starting_equity','three_numeric_conditions_met_at_interim_cutoff'))
   no_annual(v)
def dependency(state,part,rawrow,target,events,sessions):
 assert rawrow['code']=='sh.600079' and rawrow['date']==DAY and rawrow['tradestatus']=='1' and rawrow['isST']=='1'
 assert sessions[sessions.index(DAY)+1]==NEXT and target['as_of']==DAY and CODE in target['weights']
 physical=sum(l['quantity'] for l in state['positions'].get(CODE,[]))
 pending_shares=sum(x['quantity'] for x in state['stock_claims'] if x['instrument']==CODE and not x['credited'])
 pending_orders=[x for x in state['orders'] if x['security_id']==CODE and x['status']=='PENDING']
 exevents=[x for x in events if x['instrument']==CODE and x['ex_date']==DAY and state['entitlements'].get(x['event_id'],0)>0]
 assert physical==pending_shares==state['owned_shares'].get(CODE,0)==0 and not pending_orders and not exevents
 assert state['last_account_clock']==['2026-03-30',1] and part['rows'][-1]['day']=='2026-03-30'
 assert state['cash']==part['rows'][-1]['cash']
 listed={c:sum(l['quantity'] for l in ls) for c,ls in state['positions'].items()};assert listed==part['ownership']['2026-03-30']
 assert all(f['execution_at'][:10]<DAY for f in state['fills']) and all(x['day']<DAY for x in state['corporate_ledger'])
 assert all(x['as_of'][:10]<DAY and x['execution_session']<NEXT for x in part['intents'])
 assert not any(x['security_id']==CODE for x in state['orders']) and not any(x['security_id']==CODE for x in state['fills'])
 return {'physical_owned_quantity':physical,'pending_stock_quantity':pending_shares,'pending_order_count':0,'positive_ex_entitlement_count':0,'next_frozen_target_dependency':True,'next_execution_session':NEXT,'target_as_of':DAY,'target_weight_literal':target['weights'][CODE],'dependence_class':'NEXT_TARGET_PRIOR_CLOSE_REQUIRED','no_prior_SH600079_order_or_fill':True}
def negative(fn):
 try:fn()
 except (AssertionError,KeyError,ValueError):return True
 raise AssertionError('negative unexpectedly accepted')
def main():
 rp=R/'experiments/qlib/price-delay-horizon-raw-daily-request.json';assert sha(rp)==REQ
 assert digest_bytes(subprocess.check_output(['git','show','25c6d03:experiments/qlib/price-delay-horizon-raw-daily-request.json'],cwd=R))==REQ
 plan=read(rp)
 for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('immutable_financial_sha256',B)]:
  for n,h in plan[field].items():assert sha(root/n)==h
 assert len(plan['immutable_financial_sha256'])==60
 summary=read(O/'summary.json');cases=read(O/'case_results.json');assert cases==summary['results_by_extra_bps'] and set(cases)=={'20','40'}
 assert summary['plan_sha256']==REQ and summary['all60_oldfinancial_unchanged_postcheck'] is True and summary['annual_returns_computed_after_both_complete_gates'] is False
 assert summary['execution_model']=='DAILY_PROXY_ONLY' and summary['original_strict_minute_admission_stays_failed'] is True and summary['objective_achieved'] is False
 no_annual(summary);no_annual(cases)
 rawroot=B/'price-delay-raw-horizon-v2-20261021';rm=read(rawroot/'manifest.json');assert sha(rawroot/'manifest.json')==summary['raw_manifest_sha256'];calendar=read(rawroot/'calendar.json')['sessions'];assert sha(rawroot/'calendar.json')==rm['calendar_sha256']
 for code,h in rm['per_code_sha256'].items():assert sha(rawroot/'codes'/(code+'.json'))==h
 p=read(rawroot/'codes/SH600079.json');rawrow=next(x for x in p['bars'] if x['date']==DAY)
 targetpath=B/'price-delay-horizon-formations-20261021/candidate_targets.json';assert sha(targetpath)==summary['target_sha256'];target=read(targetpath)[NEXT]
 es=B/'price-delay-account-horizon-events-20261021';em=read(es/'summary.json');assert sha(es/'summary.json')==summary['event_summary_sha256']
 for n,h in em['artifact_sha256'].items():assert sha(es/n)==h
 events=read(es/'derived_events.json');assert len(events)==613
 # Static authenticated code order plus saved clock establish pre-start-day refusal.
 code=ast.parse((R/'scripts/replay_stock_distribution_targets.py').read_text());fn=next(x for x in code.body if isinstance(x,ast.FunctionDef) and x.name=='simulate_fixed_targets')
 loop=next(x for x in fn.body if isinstance(x,ast.For));guard=next(x.lineno for x in loop.body if isinstance(x,ast.Assign) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Name) and x.value.func.id=='source_rows_on');start=next(x.lineno for x in loop.body if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='start_day');assert guard<start
 oldscope=read(B/'price-delay-ordinary-source-scope-20261021/scope.json')['nonordinary_source_intervals'];expected_scope=[{'instrument':x['instrument'],'session':x['day'],'reason':'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT','original_row_present':True,'source_isST':'1','required_by_account':False,'synthetic_price_created':False} for x in oldscope];assert len(expected_scope)==241
 oldsummary=read(B/'price-delay-raw-daily-pre2026-20261021/summary.json');profiles={};negatives={};first=None
 for cost in ['20','40']:
  folder=O/cost;r=cases[cost];assert r['status']=='INVALID_SOURCE_OR_ACCOUNT' and r['error_type']=='ValueError' and r['error']=='required nonordinary source state: SH600079 2026-03-31' and r['portfolio_returns_computed'] is False
  assert set(r['failure_artifact_sha256'])=={'failed_account_state.json','partial_case.json','source_scope_audit.json','error.json'} and {p.name for p in folder.iterdir()}==set(r['failure_artifact_sha256'])
  for n,h in r['failure_artifact_sha256'].items():assert sha(folder/n)==h
  error=read(folder/'error.json');assert error=={k:r[k] for k in ['status','error_type','error','portfolio_returns_computed']}
  state=read(folder/'failed_account_state.json');part=read(folder/'partial_case.json');scope=read(folder/'source_scope_audit.json');dep=dependency(state,part,rawrow,target,events,calendar)
  assert [x['day'] for x in part['rows']]==calendar[:calendar.index(DAY)] and list(part['ownership'])==calendar[:calendar.index(DAY)]
  assert len(part['rows'])==541 and len(part['intents'])==27 and len(scope)==len(part['lifecycle_audit'])==296 and scope==part['lifecycle_audit']
  assert [x for x in scope if x['session']<=PRE]==expected_scope and all(x['session']<DAY for x in scope)
  checkpoint=state['pre2026_checkpoint'];oldfolder=B/'price-delay-raw-daily-pre2026-20261021'/cost;oldhash=oldsummary['results_by_extra_bps'][cost]['artifact_sha256']
  olddays=[x for x in part['rows'] if x['day']<=PRE];assert len(olddays)==486
  stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(olddays[0]));writer.writeheader();writer.writerows(olddays);reproduced={'daily.csv':digest_bytes(stream.getvalue().encode())}
  objects={k:checkpoint[k] for k in ['orders','fills','corporate_ledger']};objects['intents']=[x for x in part['intents'] if x['execution_session']<=PRE];objects['ownership']={d:v for d,v in part['ownership'].items() if d<=PRE};assert len(objects['intents'])==24
  for k,v in objects.items():assert read(oldfolder/(k+'.json'))==v;reproduced[k+'.json']=serialized_hash(v)
  assert reproduced==oldhash
  with (oldfolder/'daily.csv').open() as f:assert list(csv.DictReader(f))==olddays
  no_annual(error);profiles[cost]={'failure_artifact_sha256':r['failure_artifact_sha256'],'source_dependency':dep,'last_account_clock':state['last_account_clock'],'completed_partial_days':541,'completed_intents':27,'old486days_24intents_6financial_prefixes_byte_exact':True,'reproduced_old6_prefix_sha256':reproduced,'old241_source_scope_prefix_identical':True,'source_scope_records_before_failure':296,'failure_day_no_account_clock_cash_position_fill_or_corporate_mutation_evidence':True,'annual_returns_computed':False}
  if first is None:first=(state,part)
 state,part=first
 changed=copy.deepcopy(rawrow);changed['isST']='0';negatives['ordinary_row_cannot_explain_failure']=negative(lambda:dependency(state,part,changed,target,events,calendar))
 changed=copy.deepcopy(target);del changed['weights'][CODE];negatives['missing_target_dependency_rejected']=negative(lambda:dependency(state,part,rawrow,changed,events,calendar))
 changed=copy.deepcopy(state);changed['last_account_clock']=[DAY,0];negatives['mutated_failureday_clock_rejected']=negative(lambda:dependency(changed,part,rawrow,target,events,calendar))
 assert {x.name for x in O.iterdir()}=={'20','40','case_results.json','summary.json'}
 report={'status':'INDEPENDENT_BOUNDED_RAW_ACCOUNT_FAILURE_EVIDENCE_CONFIRMED_NO_ANNUAL_ROI','audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'production_account_or_annual_scorer_called':False,'plan_sha256':REQ,'summary_sha256':sha(O/'summary.json'),'case_results_sha256':sha(O/'case_results.json'),'frozen_commit_request_bytes_verified':'25c6d03','failure_instrument':CODE,'failure_day':DAY,'raw_source_packet_sha256':sha(rawroot/'codes/SH600079.json'),'source_state':{k:rawrow[k] for k in ['date','code','tradestatus','isST']},'both_profiles_failed_same_next_target_dependency':True,'profiles':profiles,'all8_failure_artifact_hashes_verified':True,'all60_original_financial_file_bytes_unchanged':True,'all_request_method_public_local_bindings_unchanged':True,'all203_raw_packet_hashes_and5_compiled_artifact_hashes_unchanged':True,'source_guard_precedes_account_start_day_in_authenticated_code':True,'guard_source_line':guard,'start_day_source_line':start,'no_2026_annual_return_fields_in_results':True,'annual_returns_computed_after_both_complete_gates':False,'semantic_negative_controls_rejected':negatives,'critical_or_important_findings':[],'limitations':['Failure is caused by next frozen target prior-close dependency, not actual SH600079 ownership, pending order, pending stock or positive ex entitlement. No free exit or target deletion is justified.','Observed state and authenticated code show refusal before account.start_day onMar31; there is no valid March31/full676day continuation or annual2026 result.','Both original2024/25 six-artifact prefixes were independently recovered byte-exact from partial rows/intents/ownership plus the Dec31 checkpoint. This is not an independent reconstruction of every2026partial-day trade or account economics.','The presence of earlier partial daily net_return/equity records is retained failure evidence; no annual scorer was called by this audit and no2026annual ROI is calculated or reported.','No account rerun, target/rule/guard edit, source mutation, network or new source query.'],'account_replay_admitted':False,'portfolio_returns_computed':False,'objective_achieved':False}
 OUT.write_text(json.dumps(report,indent=2)+'\n');print(OUT);print(sha(OUT));print('both partial prefixes exact;3semantic negatives;no annual scorer/account')
if __name__=='__main__':main()
