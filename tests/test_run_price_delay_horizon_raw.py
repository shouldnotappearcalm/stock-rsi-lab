"""All market records below are fabricated; no local market/result inputs opened."""
import copy,importlib.util,json,sys,tempfile,unittest
from datetime import date,timedelta
from decimal import Decimal as D
from functools import partial
from pathlib import Path
R=Path(__file__).resolve().parents[1]
from scripts import run_price_delay_horizon_raw as api
from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistributionAccount,StockDistribution
from stock_rsi.execution_cost import ExecutionCostBroker
from scripts.replay_stock_distribution_targets import simulate_fixed_targets as old_sim

def calendar_fixture():
 def days(a,b):
  out=[];d=date.fromisoformat(a)
  while d<=date.fromisoformat(b):
   if d.weekday()<5 and d.isoformat() not in ('2024-01-01','2025-01-01','2026-01-01','2026-01-02'):out.append(d.isoformat())
   d+=timedelta(days=1)
  return out
 def cap(ds,count):
  first={}
  for d in ds:first.setdefault(d[:7],d)
  keep=set(first.values())|{'2023-12-29','2024-01-03','2024-01-04','2024-12-31','2025-12-31','2026-10-20'}
  remove=len(ds)-count
  for d in list(ds):
   if remove and d not in keep:ds.remove(d);remove-=1
  assert len(ds)==count
  return ds
 return cap(days('2023-12-29','2025-12-31'),486)+cap(days('2026-01-01','2026-10-20'),190)
def fixture():
 sessions=calendar_fixture();first={}
 for d in sessions:
  if d>='2024-01-02':first.setdefault(d[:7],d)
 targets={d:{'as_of':sessions[sessions.index(d)-1],'weights':{'SH600001' if d<=api.PRE else 'SZ000001':'0.95'}} for d in first.values()}
 packets={c:{'instrument':c,'bars':[{'date':d,'code':c[:2].lower()+'.'+c[2:],'open':'10.00','high':'10.00','low':'10.00','close':'10.00','preclose':'10.00','volume':'100000000','amount':'1000000000','adjustflag':'3','tradestatus':'1','isST':'0'} for d in sessions]} for c in ('SH600001','SZ000001')}
 bars,boundary=api.project_account_bars(packets,{'SH600001'},targets);refs={}
 for cost in api.COSTS:
  factory=partial(StockDistributionAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=cost))
  case=old_sim(TradingCalendar(sessions[:486]),{'SH600001':bars['SH600001']},(),{d:t for d,t in targets.items() if d<=api.PRE},api.CAPITAL,lifecycles={},account_factory=factory,policy_id=api.POLICY)
  refs[cost]={k:api.clean(case[k]) for k in ('orders','fills','corporate_ledger','intents','ownership')};refs[cost]['days']=[{k:str(v) for k,v in r.items()} for r in case['days']];refs[cost]['artifact_sha256']=api.prefix_artifact_hashes(case,{k:api.clean(case[k]) for k in ('orders','fills','corporate_ledger')})
 return {'calendar':TradingCalendar(sessions),'sessions':sessions,'packets':packets,'raw_bars':{c:{r['date']:r for r in p['bars']} for c,p in packets.items()},'bars':bars,'old_codes':{'SH600001'},'boundary_codes':boundary,'events':(),'targets':targets,'references':refs,'old_scope':[],'receipts':[]}

class ContinuousDraftTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.inputs=fixture()
 def test_projection_is_immutable_and_only_exact_boundary_close_state_is_exposed(self):
  v=copy.deepcopy(self.inputs);before=copy.deepcopy(v['packets']);bars,boundary=api.project_account_bars(v['packets'],v['old_codes'],v['targets'])
  self.assertEqual(boundary,{'SZ000001'});self.assertEqual(v['packets'],before)
  self.assertEqual([d for d in bars['SZ000001'] if d<=api.PRE],[api.PRE]);self.assertEqual(set(bars['SZ000001'][api.PRE]),{'date','code','close','tradestatus','isST'})
  self.assertEqual(len(bars['SH600001']),676)
 def test_simulator_keeps_original_code_and_allocator_and_guards_required_ST(self):
  simulation,audit=api.make_simulator(self.inputs['old_codes'],self.inputs['boundary_codes']);self.assertIs(simulation.__code__,old_sim.__code__);self.assertIs(simulation.__globals__['plan_integer_targets'],old_sim.__globals__['plan_integer_targets'])
  guard=simulation.__globals__['source_rows_on'];d=date(2026,1,5);b=copy.deepcopy(self.inputs['bars']);b['SH600001'][d.isoformat()]['isST']='1'
  with self.assertRaisesRegex(ValueError,'required nonordinary'):guard(b,d,{'SH600001'}, {})
  rows,extra=guard(b,d,set(),{});self.assertNotIn('SH600001',rows);self.assertEqual(extra[0]['required_by_account'],False)
 def test_future_only_prewindow_dependency_fails_even_with_existing_full_original_bytes(self):
  sim,_=api.make_simulator(self.inputs['old_codes'],self.inputs['boundary_codes']);guard=sim.__globals__['source_rows_on']
  with self.assertRaisesRegex(ValueError,'future-only'):guard(self.inputs['bars'],date(2025,12,30),{'SZ000001'}, {})
 def test_all676_sessions_34intents_both_profiles_keep_prefix_before_stub_scoring(self):
  calls=[]
  def scorer(case):calls.append(len(case['days']));return {'synthetic_stub_only':True}
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'run';results,post,scored=api.run_profiles(out,self.inputs,postcheck=lambda:None,scorer=scorer)
   self.assertTrue(post and scored);self.assertEqual(calls,[676,676]);self.assertEqual(set(results),{'20','40'})
   for cost in api.COSTS:
    self.assertEqual(results[str(cost)]['status'],'CONTINUOUS_DAILY_PROXY_RECONCILED');intents=api.read(out/str(cost)/'intents.json')
    cross=[r for r in intents if r['execution_session']>api.PRE and r['as_of'][:10]==api.PRE];self.assertEqual(len(cross),1);self.assertEqual(cross[0]['execution_session'],'2026-01-05')
    self.assertFalse(any('return_pct' in k for k in results[str(cost)]))
 def test_gate_rejects_late_profile_failure_or_postcheck_without_any_scorer_calls(self):
  calls=[];fn=lambda c:calls.append(c)
  for results,cases,post in [({'20':{'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED'},'40':{'status':'INVALID_SOURCE_OR_ACCOUNT'}},{20:{},40:{}},True),({'20':{'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED'},'40':{'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED'}},{20:{},40:{}},False),({'20':{'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED'},'40':{'status':'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED'}},{20:{}},True)]:self.assertFalse(api.finalize_returns(results,cases,post,fn))
  self.assertEqual(calls,[])
 def test_unknown_tax_and_fractional_fail_before_credit_retain_both_profiles_and_entitlements(self):
  # January2024 fixture only; no actual2026 holdings/returns are read.
  for verified,capital,reason in [(False,'1','tax treatment'),(True,'0.4019063','fractional')]:
   x=copy.deepcopy(self.inputs);e=StockDistribution('f'*64,'SH600001',date(2023,12,29),date(2024,1,3),date(2024,1,4),date(2024,1,4),date(2024,1,4),D('0.41'),D(capital),verified)
   x['events']=(e,);calls=[]
   with tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp)/'failed';results,post,scored=api.run_profiles(out,x,postcheck=lambda:None,scorer=lambda _:calls.append('bad'))
    self.assertFalse(scored);self.assertEqual(calls,[]);self.assertEqual(set(results),{'20','40'})
    for c in api.COSTS:
     r=results[str(c)];self.assertIn(reason,r['error']);state=api.read(out/str(c)/'failed_account_state.json');self.assertGreater(state['entitlements'][e.event_id],0)
     self.assertFalse(any(row['kind']=='EX_DATE_ENTITLEMENT' for row in state['corporate_ledger']));self.assertEqual(state['cash_claims'],[]);self.assertEqual(state['stock_claims'],[])
     self.assertTrue(api.read(out/str(c)/'partial_case.json')['rows']);self.assertFalse(r['portfolio_returns_computed'])
 def test_boundary_prefix_uses_execution_session_and_checkpoint_status_not_later_mutation(self):
  original={'orders':[{'eligible_at':'2025-12-01T09:30:00+08:00','status':'FILLED'}],'fills':[],'corporate_ledger':[],'intents':[{'execution_session':'2025-12-01'}],'ownership':{},'days':[{'day':'2025-12-31','cash':'1000000'}]};checkpoint={k:copy.deepcopy(original[k]) for k in ('orders','fills','corporate_ledger')};case={**copy.deepcopy(original),'intents':original['intents']+[{'execution_session':'2026-01-05','as_of':'2025-12-31T15:05:00+08:00'}],'days':[{'day':'2025-12-31','cash':D('1000000')}],'lifecycle_source_audit':[]};original['artifact_sha256']=api.prefix_artifact_hashes(case,checkpoint)
  case['orders'][0]['status']='LATER_MUTATED';api.verify_prefix(case,checkpoint,original,[])
  case['intents'][0]['execution_session']='2026-01-05'
  with self.assertRaises(ValueError):api.verify_prefix(case,checkpoint,original,[])
 def test_old_physical_fee_or_cash_tamper_is_rejected_by_conservation(self):
  inputs=self.inputs;sim,_=api.make_simulator(inputs['old_codes'],inputs['boundary_codes']);factory=partial(StockDistributionAccount,broker_factory=partial(ExecutionCostBroker,extra_cost_bps=20));case=sim(inputs['calendar'],inputs['bars'],(),inputs['targets'],api.CAPITAL,lifecycles={},account_factory=factory,policy_id=api.POLICY)
  self.assertTrue(api.reconcile_case(case,(),inputs['bars'],inputs['sessions'],20));bad=copy.deepcopy(case);bad['fills'][0]['cost']=str(D(bad['fills'][0]['cost'])+1)
  with self.assertRaisesRegex(ValueError,'feeformula'):api.reconcile_case(bad,(),inputs['bars'],inputs['sessions'],20)
 def test_late_profile_prefix_failure_prevents_all_annual_scoring_and_retains_full_evidence(self):
  x=copy.deepcopy(self.inputs);x['references'][40]['days'][0]['cash']='999999';calls=[]
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'run';r,post,scored=api.run_profiles(out,x,postcheck=lambda:None,scorer=lambda _:calls.append('forbidden'))
   self.assertFalse(scored);self.assertEqual(calls,[]);self.assertEqual(r['20']['status'],'CONTINUOUS_DAILY_PROXY_RECONCILED_UNSCORED');self.assertEqual(r['40']['status'],'INVALID_SOURCE_OR_ACCOUNT')
   self.assertTrue((out/'40/unvalidated_completed_case.json').exists());self.assertEqual(len(api.read(out/'40/unvalidated_completed_case.json')['days']),676)
 def test_physical60_file_hashes_are_checked_not_only_summary_maps(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for folder,key,labels,names in [(api.OLDDAY,'results_by_extra_bps',['20','40'],set(api.ARTIFACTS)),(api.OLDINTRA,'results_by_profile',[f'{p}/{c}' for p in (100,500,1000) for c in (20,40)],set(api.ARTIFACTS)|{'parent_instructions.json','source_scope_audit.json'})]:
    records={}
    for label in labels:
     here=root/folder/label;here.mkdir(parents=True);hashes={}
     for name in names:(here/name).write_bytes(b'fixed synthetic artifact');hashes[name]=api.sha(here/name)
     records[label]={'artifact_sha256':hashes}
    api.write_json(root/folder/'summary.json',{key:records})
   self.assertEqual(len(api.immutable_financials(root)),60)
   (root/api.OLDINTRA/'100/40/daily.csv').write_bytes(b'tampered physical bytes')
   with self.assertRaisesRegex(ValueError,'oldfinancial changed'):api.immutable_financials(root)
 def test_corporate_prerequisite_failure_does_not_credit_other_due_cash_claim(self):
  cal=TradingCalendar(['2024-01-02','2024-01-03','2024-01-04'])
  for verified,capital in [(False,'1'),(True,'0.4019063')]:
   e=StockDistribution('a'*64,'SH600001',date(2024,1,1),date(2024,1,2),date(2024,1,3),date(2024,1,3),date(2024,1,3),D('0.41'),D(capital),verified)
   a=StockDistributionAccount(cal,api.CAPITAL,(e,));a.broker.positions={'SH600001':[{'quantity':100,'price':D('10'),'bought_on':date(2024,1,2)}]};a.entitlements[e.event_id]=100;a.cash_claims=[{'event_id':'other','net':D('7'),'available_on':date(2024,1,3),'paid':False}]
   before=copy.deepcopy((a.broker.cash,a.broker.positions,a.entitlements,a.cash_claims,a.stock_claims,a.corporate_ledger,a._last_clock))
   with self.assertRaises(ValueError):a.start_day(date(2024,1,3))
   self.assertEqual((a.broker.cash,a.broker.positions,a.entitlements,a.cash_claims,a.stock_claims,a.corporate_ledger,a._last_clock),before)
 def test_wrong_external_sha_and_existing_output_fail_without_source_access(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'plan';p.write_text('{}');out=root/'out'
   args=['--source-root',str(root/'absent'),'--repo-root',str(root/'absent'),'--plan',str(p),'--expected-plan-sha256','0'*64,'--output-dir',str(out),'--source-preflight-only']
   with self.assertRaisesRegex(ValueError,'external frozen'):api.main(args)
   self.assertFalse(out.exists());out.mkdir()
   with self.assertRaisesRegex(ValueError,'preserve existing'):api.main(args)
if __name__=='__main__':unittest.main()
