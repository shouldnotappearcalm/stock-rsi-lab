import ast,copy,importlib.util,json,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from scripts import inventory_price_delay_horizon_minutes as draft
R=Path(__file__).resolve().parents[1]
class SourceOnlyDraftTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  prefix,tape,cls.adapter=draft.load_adapters(R);cls.prefix=staticmethod(prefix);cls.inspect=staticmethod(tape)
 def fixtures(self):
  targets={'2025-12-31':{'as_of':'2025-12-30','weights':{'SH600001':'0.95'}},'2026-01-05':{'as_of':'2025-12-31','weights':{'SZ000001':'0.95'}},'2026-02-02':{'as_of':'2026-01-05','weights':{'SH600001':'0.95'}}}
  bars={c:{d:{'date':d,'tradestatus':'1','isST':'0'} for d in targets} for c in ('SH600001','SZ000001')};return targets,bars
 def test_date_cap_adapter_keeps_old_prefix_exact_and_original_unchanged(self):
  from scripts.illiquidity_minute_sources import prefix_minute_requirements as old
  t,b=self.fixtures();pre={k:v for k,v in t.items() if k<='2025-12-31'}
  self.assertEqual(self.prefix(pre,b,{}),old(pre,b,{}))
  with self.assertRaises(ValueError):old(t,b,{})
  self.assertEqual(self.adapter['date_cap_literals_changed'],1);self.assertTrue(self.adapter['inspect_function_AST_unchanged'])
 def test_cumulative_seen_algorithm_does_not_drop_past_names_or_use_ownership(self):
  t,b=self.fixtures();active,skipped=self.prefix(t,b,{})
  self.assertEqual(active,[['SH600001','2025-12-31'],['SH600001','2026-01-05'],['SZ000001','2026-01-05'],['SH600001','2026-02-02'],['SZ000001','2026-02-02']]);self.assertEqual(skipped,[])
 def test_ST_and_unknown_flags_remain_active_required_pairs(self):
  t,b=self.fixtures();b['SH600001']['2026-01-05']['isST']='1';b['SZ000001']['2026-01-05']['isST']='?';active,_=self.prefix(t,b,{})
  self.assertIn(['SH600001','2026-01-05'],active);self.assertIn(['SZ000001','2026-01-05'],active)
  self.assertEqual(draft.source_state(b['SH600001']['2026-01-05']),'NONORDINARY_FLAG_ONE');self.assertEqual(draft.source_state(b['SZ000001']['2026-01-05']),'ORDINARY_FLAG_UNKNOWN')
 def test_halt_is_retained_skipped_without_zero_inventory_claim(self):
  t,b=self.fixtures();b['SH600001']['2026-01-05']['tradestatus']='0';a,s=self.prefix(t,b,{})
  self.assertNotIn(['SH600001','2026-01-05'],a);self.assertEqual(s,[{'instrument':'SH600001','day':'2026-01-05','reason':'SOURCE_HALT','actual_inventory_proven_zero':False,'synthetic_price_created':False}])
 def test_unexplained_gap_and_future_date_fail(self):
  t,b=self.fixtures();del b['SH600001']['2026-01-05']
  with self.assertRaises(ValueError):self.prefix(t,b,{})
  for d in ('2026-10-21','2027-01-01','2026-1-05'):
   with self.subTest(d=d),self.assertRaises(ValueError):draft.valid_pair('SH600001',d)
 def test_prefix_calendar_target_and_priorclose_contract(self):
  sessions=['2025-12-30','2025-12-31','2026-01-05'];targets={'2025-12-31':{'as_of':'2025-12-30','weights':{'SH600001':'0.95'}},'2026-01-05':{'as_of':'2025-12-31','weights':{'SH600001':'0.95'}}};old={'2025-12-31':copy.deepcopy(targets['2025-12-31'])}
  draft.validate_prefix(sessions,sessions[:2],targets,old,full=False)
  changed=copy.deepcopy(targets);changed['2025-12-31']['weights']['SH600001']='0.94'
  with self.assertRaises(ValueError):draft.validate_prefix(sessions,sessions[:2],changed,old,full=False)
  changed=copy.deepcopy(targets);changed['2026-01-05']['as_of']='2025-12-30'
  with self.assertRaises(ValueError):draft.validate_prefix(sessions,sessions[:2],changed,old,full=False)
 def test_conflicts_are_not_selected_by_quality_or_counted_as_fresh(self):
  origins=[{'root':'A','sha256':'a'*64},{'root':'B','sha256':'b'*64}];packet=lambda o:{'instrument':'SH600001','requested_day':'2026-01-05','status':'RESPONSE_CAPTURED','response':{'fixture':o['root']}}
  result=draft.cache_pair('SH600001','2026-01-05',{'isST':'0'},origins,packet,lambda *a:None)
  self.assertEqual(result['status'],'CONFLICTING_CACHED_RESPONSES');self.assertIsNone(result['selected_origin'])
 def test_unknown_ST_metadata_kept_without_ordinary_admission(self):
  origin={'root':'A','sha256':'a'*64};packet={'instrument':'SH600001','requested_day':'2026-01-05','status':'RESPONSE_CAPTURED','response':{'fixture':True}}
  def forbidden(*a):raise AssertionError('ordinary acceptance must not be inferred for ST')
  result=draft.cache_pair('SH600001','2026-01-05',{'isST':'1'},[origin],lambda _:packet,forbidden)
  self.assertEqual(result['selected_origin'],origin);self.assertFalse(result['ordinary_source_quality_checked']);self.assertFalse(result['source_or_account_admitted'])
 def test_budget_is_missing_only_not_rejected_retries_and_inputs_not_mutated(self):
  active=[['SH600001','2026-01-05'],['SH600002','2026-01-05'],['SH600003','2026-01-05']];bars={c:{d:{'isST':'0'}} for c,d in active};index={'SH600001-2026-01-05.json':[{'root':'A','sha256':'a'*64}],'SH600002-2026-01-05.json':[{'root':'B','sha256':'b'*64}]};before=copy.deepcopy((active,bars,index))
  def load(o,name):return {'instrument':name.split('-')[0],'requested_day':'2026-01-05','status':'RESPONSE_CAPTURED' if o['root']=='A' else 'REQUEST_FAILED','response':{'fixture':True}}
  r=draft.inventory_new_pairs(active,bars,index,load,lambda *a:None)
  self.assertEqual(r['uncached_requests'],[['SH600003','2026-01-05']]);self.assertEqual(r['invalid_cached_requests'],[['SH600002','2026-01-05']]);self.assertEqual(r['proposed_maximum_new_logical_queries'],1);self.assertEqual((active,bars,index),before)
 def test_unchanged_ordinary_inspection_accepts_synthetic_newdate_and_rejects_ST(self):
  from scripts.tdx_history_checks import minute_labels
  day='2026-01-05';points=[{'index':i,'time_label':t,'time':day+'T'+t+':00+08:00','price_milli':10000,'price':10.0,'volume':1} for i,t in enumerate(minute_labels())]
  packet={'instrument':'SH600001','requested_day':day,'status':'RESPONSE_CAPTURED','response':{'exchange':'sh','market_id':1,'code':'600001','trading_date':day,'points':points}}
  daily={'date':day,'tradestatus':'1','isST':'0','close':'10','low':'9','high':'11','volume':'24000'}
  result=self.inspect('SH600001',day,packet,daily);self.assertEqual(result['windows'],48);self.assertEqual(result['status'],'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE')
  with self.assertRaises(ValueError):self.inspect('SH600001',day,packet,{**daily,'isST':'1'})
 def test_wrong_plan_checksum_fails_before_sources_or_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'plan.json';p.write_text('{}');out=root/'no-output'
   with self.assertRaisesRegex(ValueError,'external frozen plan SHA'):
    draft.main(['--source-root',str(root/'absent'),'--repo-root',str(root/'absent'),'--plan',str(p),'--expected-plan-sha256','0'*64,'--output-dir',str(out),'--execute-frozen-inventory','--frozen-commit','0000000'])
   self.assertFalse(out.exists())
 def test_real_financial_bytes_checked_even_when_all_summary_maps_unchanged(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp)/'base';repo=Path(tmp)/'repo';base.mkdir();(repo/'experiments/qlib').mkdir(parents=True)
   bindings={}
   for i in range(48):
    f=base/(str(i)+'.json');f.write_text('original');bindings[f.name]=draft.sha(f)
   (repo/'experiments/qlib/price-delay-horizon-raw-source-request.json').write_text(json.dumps({'immutable_financial_sha256':bindings}))
   with patch('scripts.prepare_price_delay_horizon_formations.immutable_financial_hashes',return_value=bindings):
    draft.verify_financial_prefix({'immutable_financial_sha256':bindings},base,repo)
    (base/'17.json').write_text('changed bytes with all maps unchanged')
    with self.assertRaises(ValueError):draft.verify_financial_prefix({'immutable_financial_sha256':bindings},base,repo)
if __name__=='__main__':unittest.main()
