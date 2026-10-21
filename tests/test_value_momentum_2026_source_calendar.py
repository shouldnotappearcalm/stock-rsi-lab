import copy,unittest
from datetime import date
from scripts.prepare_value_momentum_2026_targets_v2 import monthly_execution_sessions,verify_monthly_target_identities


class CompositeSourceCalendarTests(unittest.TestCase):
 def test_every_family_and_receipt_uses_source_session_and_previous_explicit_session(self):
  days=[date.fromisoformat(d) for d in ('2026-09-30','2026-10-08','2026-10-09')]
  targets={name:{'2026-10-08':{'as_of':'2026-09-30','weights':{}}} for name in
   ('szse_value_momentum_equal','value_leg_control','momentum_leg_control')}
  receipts=[{'execution_session':'2026-10-08','formation_asof':'2026-09-30'}]
  self.assertEqual(verify_monthly_target_identities(days,targets,receipts,'2026-10-01','2026-10-13'),['2026-10-08'])
  wrong=copy.deepcopy(targets);wrong['value_leg_control']={}
  with self.assertRaises(ValueError):verify_monthly_target_identities(days,wrong,receipts,'2026-10-01','2026-10-13')
  wrong=copy.deepcopy(targets);wrong['momentum_leg_control']['2026-10-08']['as_of']='2026-10-08'
  with self.assertRaises(ValueError):verify_monthly_target_identities(days,wrong,receipts,'2026-10-01','2026-10-13')
  for bad in (receipts+receipts,[{'execution_session':'2026-10-08','formation_asof':'2026-10-08'}]):
   with self.assertRaises(ValueError):verify_monthly_target_identities(days,targets,bad,'2026-10-01','2026-10-13')

 def test_first_session_is_supplied_by_source_including_holiday_and_month_gaps(self):
  days=[date.fromisoformat(d) for d in ('2025-12-31','2026-01-05','2026-01-30',
   '2026-02-02','2026-09-30','2026-10-08','2026-10-09','2026-10-13')]
  expected=['2026-01-05','2026-02-02','2026-09-30','2026-10-08']
  self.assertEqual(monthly_execution_sessions(days,'2026-01-01','2026-10-13'),expected)
  # An alternative explicit calendar is used literally; no weekdays or Oct8/9 assumptions.
  alternative=[d for d in days if d!=date(2026,10,8)]
  self.assertEqual(monthly_execution_sessions(alternative,'2026-10-01','2026-10-13'),['2026-10-09'])
  for bad in ([],days[::-1],days+[days[-1]]):
   with self.assertRaises(ValueError):monthly_execution_sessions(bad,'2026-01-01','2026-10-13')

if __name__=='__main__':unittest.main()
