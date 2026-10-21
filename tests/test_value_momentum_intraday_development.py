import copy,json,tempfile,unittest
from pathlib import Path
from stock_rsi.calendar import TradingCalendar
from scripts.run_value_momentum_intraday_development import confirmation_passes,run_profiles


class CompositeIntradayTests(unittest.TestCase):
 def test_development_gate_cannot_pick_a_successful_participation_or_cheaper_profile(self):
  good={f'{p}/{c}':{'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED','2024_return_pct':1.,'2025_return_pct':2.,
   'average_exposure_pct':94.,'monthly_decisions':24,'account_sessions':485,'primary_bound_absent_sessions':60,
   'whole_day_volume_violations':0,'noncash_entitlements_supported':True,'all_children_within_1million_shares':True}
   for p in (100,500,1000) for c in (20,40)}
  self.assertTrue(confirmation_passes(good))
  for p in (100,500,1000):
   for value in (0.,-.1,float('nan'),float('inf'),None,True):
    bad=copy.deepcopy(good);bad[f'{p}/40']['2024_return_pct']=value
    self.assertFalse(confirmation_passes(bad))
  bad=copy.deepcopy(good);bad.pop('100/20');self.assertFalse(confirmation_passes(bad))
  for field,value in (('primary_bound_absent_sessions',59),('all_children_within_1million_shares',False),('monthly_decisions',23)):
   bad=copy.deepcopy(good);bad['500/40'][field]=value;self.assertFalse(confirmation_passes(bad))

 def test_physical_account_source_failure_preserves_all_six_attempts_and_pending_parents(self):
  days=['2023-12-29','2024-01-02'];code='SZ000001';calendar=TradingCalendar(days)
  bars={code:{d:{'date':d,'tradestatus':'1','isST':'0','open':'10','close':'10','preclose':'10',
   'high':'10','low':'10','volume':'1000000'} for d in days}}
  targets={days[1]:{'as_of':days[0],'weights':{code:'.95'}}}
  class MissingTape:
   def __call__(self,code,day):raise OSError('fixture source disappeared after authentication')
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'run';results=run_profiles(out,calendar,bars,(),targets,{},MissingTape())
   self.assertEqual(set(results),{f'{p}/{c}' for p in (100,500,1000) for c in (20,40)})
   self.assertEqual(json.loads((out/'case_results.json').read_text()),results)
   for label,r in results.items():
    self.assertEqual(r['status'],'INVALID_SOURCE_OR_ACCOUNT');self.assertEqual(r['error_type'],'OSError')
    self.assertIn('fixture source disappeared',r['error'])
    state=json.loads((out/label/'failed_account_state.json').read_text())
    self.assertEqual(len(state['parent_instructions']),1);self.assertEqual(state['parent_instructions'][0]['action'],'BUY')
    self.assertEqual(state['cash'],'1000000');self.assertEqual(state['fills'],[])
   with self.assertRaises(ValueError):run_profiles(out,calendar,bars,(),targets,{},MissingTape())

if __name__=='__main__':unittest.main()
