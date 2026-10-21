import copy,json,tempfile,unittest
from pathlib import Path
from stock_rsi.calendar import TradingCalendar
from scripts.run_price_delay_intraday_development import confirmation_passes,run_profiles
from scripts import run_price_delay_intraday_development as runner


class PriceDelayIntradayTests(unittest.TestCase):
 def test_profile_contract_rejects_allocator_change_future_values_or_missing_anchors(self):
  p={'status':'FROZEN_PRICE_DELAY_PRE2026_INTRADAY_DEVELOPMENT','candidate':'price_delay_d1',
   'candidate_budget':1,'participation_bps':[100,500,1000],'extra_cost_bps':[20,40],
   'initial_CNY':'1000000','window':['2023-12-29','2025-12-31'],
   'output_relative':'price-delay-intraday-pre2026-20261021','allocator':'plan_integer_targets',
   'account_guard':'ordinary_source_rows_on','original_strict_2502_admission_remains_failed':True,
   'network_calls_permitted':0,'new_2026_market_values_queried':False,'investment_rule_changed':False,
   'method_code_sha256':dict.fromkeys(runner.METHOD_FILES,'a'*64),
   'public_evidence_sha256':dict.fromkeys(runner.PUBLIC_FILES,'b'*64),
   'local_source_sha256':dict.fromkeys(runner.LOCAL_FILES,'c'*64)}
  runner.validate_profile(p)
  for field,value in [('allocator','plan_budgeted_raw_targets'),('account_guard','none'),
   ('new_2026_market_values_queried',True),('investment_rule_changed',True),
   ('original_strict_2502_admission_remains_failed',False),('network_calls_permitted',1),
   ('candidate_budget',True),('method_code_sha256',{}),('public_evidence_sha256',{}),
   ('local_source_sha256',{}),('output_relative','elsewhere')]:
   changed=copy.deepcopy(p);changed[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):runner.validate_profile(changed)

 def test_development_gate_cannot_pick_a_successful_participation_or_cheaper_profile(self):
  good={f'{p}/{c}':{'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED','2024_return_pct':1.,'2025_return_pct':2.,
   'average_exposure_pct':94.,'monthly_decisions':24,'account_sessions':485,'unused_ST_intervals_verified':241,'ordinary_dependency_guard_passes':True,
   'whole_day_volume_violations':0,'unproved_noncash_record_ownership':[{'quantity':0}],'noncash_entitlements_supported':True,'all_children_within_1million_shares':True}
   for p in (100,500,1000) for c in (20,40)}
  self.assertTrue(confirmation_passes(good))
  for p in (100,500,1000):
   for value in (0.,-.1,float('nan'),float('inf'),None,True):
    bad=copy.deepcopy(good);bad[f'{p}/40']['2024_return_pct']=value
    self.assertFalse(confirmation_passes(bad))
  bad=copy.deepcopy(good);bad.pop('100/20');self.assertFalse(confirmation_passes(bad))
  for field,value in (('unused_ST_intervals_verified',240),('ordinary_dependency_guard_passes',False),('all_children_within_1million_shares',False),('monthly_decisions',23),('unproved_noncash_record_ownership',[{'quantity':100}])):
   bad=copy.deepcopy(good);bad['500/40'][field]=value;self.assertFalse(confirmation_passes(bad))

 def test_physical_account_source_failure_preserves_all_six_attempts_and_pending_parents(self):
  days=['2023-12-29','2024-01-02'];code='SZ000001';calendar=TradingCalendar(days)
  bars={code:{d:{'date':d,'tradestatus':'1','isST':'0','open':'10','close':'10','preclose':'10',
   'high':'10','low':'10','volume':'1000000'} for d in days}}
  targets={days[1]:{'as_of':days[0],'weights':{code:'.95'}}}
  class MissingTape:
   def __call__(self,code,day):raise OSError('fixture source disappeared after authentication')
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'run';results=run_profiles(out,calendar,bars,(),targets,{},MissingTape(),[])
   self.assertEqual(set(results),{f'{p}/{c}' for p in (100,500,1000) for c in (20,40)})
   self.assertEqual(json.loads((out/'case_results.json').read_text()),results)
   for label,r in results.items():
    self.assertEqual(r['status'],'INVALID_SOURCE_OR_ACCOUNT');self.assertEqual(r['error_type'],'OSError')
    self.assertIn('fixture source disappeared',r['error'])
    state=json.loads((out/label/'failed_account_state.json').read_text())
    self.assertEqual(len(state['parent_instructions']),1);self.assertEqual(state['parent_instructions'][0]['action'],'BUY')
    self.assertEqual(state['cash'],'1000000');self.assertEqual(state['fills'],[])
   with self.assertRaises(ValueError):run_profiles(out,calendar,bars,(),targets,{},MissingTape(),[])

if __name__=='__main__':unittest.main()
