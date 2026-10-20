import copy,unittest
from decimal import Decimal as D
from scripts import run_etf_prior2_12_interim2026 as subject
class InterimAccountTests(unittest.TestCase):
 def test_all_development_control_ledgers_must_match_before_continuation(self):
  calls=[]
  def reproduce(extra):
   calls.append(extra)
   return {'cash':'100' if extra==20 else '99'}
  with self.assertRaises(ValueError):subject.require_development_controls(reproduce,lambda extra:{'cash':'100'})
  self.assertEqual(calls,[20,40])
 def test_same_account_year_return_uses_prior_december_equity_and_all_daily_rows(self):
  rows=[{'day':'2025-12-31','equity':D('150'),'exposure':D('.95')},
   {'day':'2026-01-05','equity':D('160'),'exposure':D('.94')},
   {'day':'2026-10-20','equity':D('180'),'exposure':D('.96')}]
  r=subject.summarize_2026(rows,['2026-01-05','2026-10-20'])
  self.assertEqual(r['net_return'],D('.2'));self.assertEqual(r['starting_equity'],D('150'));self.assertEqual(r['average_exposure'],D('.95'))
  with self.assertRaises(ValueError):subject.summarize_2026(rows,['2026-01-05'])
 def test_pre2026_full_ledger_prefix_must_be_unchanged_and_new_year_end_intent_is_allowed(self):
  old={'days':[{'day':'2025-12-31','equity':'150'}],'intents':[{'execution_session':'2025-12-01'}],
   'fills':[{'execution_at':'2025-12-01T01:30:00+00:00'}],'orders':[{'eligible_at':'2025-12-01T01:30:00+00:00'}],
   'funding_intents':[{'confirmation_session':'2025-12-01'}],'corporate_ledger':[{'day':'2025-06-01'}]}
  new=copy.deepcopy(old)
  for key,field in [('days','day'),('intents','execution_session'),('fills','execution_at'),('orders','eligible_at'),('funding_intents','confirmation_session'),('corporate_ledger','day')]:new[key].append({field:'2026-01-05'})
  subject.check_prefix(new,old)
  for key in old:
   bad=copy.deepcopy(new);bad[key][0]['unexplained']='changed'
   with self.subTest(key=key):
    with self.assertRaises(ValueError):subject.check_prefix(bad,old)
if __name__=='__main__':unittest.main()
