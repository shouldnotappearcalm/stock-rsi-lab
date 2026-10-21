"""Read-only fixed127name source inventory; never computes account returns or queries."""
import argparse,copy,hashlib,json
from decimal import Decimal
from pathlib import Path

SOURCES=('low-beta60-raw-horizon-20261021','low-risk-raw-account-data-20261017','szse-value-raw-full-20261017','reversal-raw-full-20261017')
START,PRE_END,END='2023-12-29','2025-12-31','2026-10-20'
FORM='szse-value-momentum-formations-full-v2-20261021';OLD='szse-value-momentum-raw-dev-20261021';SOURCE='szse-value-momentum-account-sources-20261021'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())

def financial_core(row):
 return (row['date'],row['code'],*(str(Decimal(row[k]).normalize()) if row[k] else '' for k in ('open','high','low','close','preclose','volume','amount')),row['tradestatus'],row['isST'])

def overlapping_conflict(left,right):
 a={r['date']:financial_core(r) for r in left};b={r['date']:financial_core(r) for r in right}
 assert len(a)==len(left) and len(b)==len(right)
 return any(a[d]!=b[d] for d in set(a)&set(b))

def main():
 p=argparse.ArgumentParser()
 for n in ('source-root','repo-root','output'):p.add_argument('--'+n,required=True)
 a=p.parse_args();base=Path(a.source_root);repo=Path(a.repo_root);out=Path(a.output);assert not out.exists()
 target=base/FORM/'targets.json';receipt=read(base/FORM/'receipt.json');auditfile=repo/'experiments/qlib/szse-value-momentum-2026-target-v2-independent-audit.json';audit=read(auditfile)
 assert sha(target)==receipt['artifact_sha256']['targets.json'] and audit['receipt_sha256']==sha(base/FORM/'receipt.json')
 assert audit['all_three_families_34_targets_reconstructed'] is True and audit['original24_complete_receipts_and_family_targets_byte_exact'] is True
 assert audit['imports_project_code'] is False and all(audit['semantic_negative_controls_rejected'].values())
 targets=read(target);codes=sorted({c for t in targets.values() for c in t['weights']});assert len(targets)==34 and len(codes)==127
 old=read(base/OLD/'manifest.json');assert old['names']==103 and set(old['per_code_sha256'])<=set(codes)
 originals={}
 for c,h in old['per_code_sha256'].items():
  f=base/OLD/'codes'/(c+'.json');assert sha(f)==h;originals[c]=read(f)
 ss=read(base/SOURCE/'summary.json');life=read(base/SOURCE/'lifecycles.json');assert sha(base/SOURCE/'lifecycles.json')==ss['artifact_sha256']['lifecycles.json']
 manifests={n:read(base/n/'manifest.json') for n in SOURCES}
 reference=base/SOURCES[0]/'calendar.json';assert sha(reference)==manifests[SOURCES[0]]['calendar_sha256']
 sessions=[d for d in read(reference)['sessions'] if START<=d<=END];assert sessions==sorted(set(sessions)) and sessions[0]==START and sessions[-1]==END
 assert [d for d in sessions if d<=PRE_END]==read(base/OLD/'calendar.json')['sessions']
 for n,m in manifests.items():
  f=base/n/'calendar.json';assert sha(f)==m['calendar_sha256']
  cal=[d for d in read(f)['sessions'] if START<=d<=min(m['window'][-1],END)]
  assert cal==[d for d in sessions if d<=min(m['window'][-1],END)]
 items={};no_cache=[];partial=[];complete=[];conflicts=[];prefix_conflicts=[]
 for c in codes:
  expected=[d for d in sessions if c not in life or d>=life[c]['effective_date']]
  choices=[];payloads=[];preconflict=False
  for n in SOURCES:
   m=manifests[n]
   if c not in m['per_code_sha256']:continue
   f=base/n/'codes'/(c+'.json');assert sha(f)==m['per_code_sha256'][c];v=read(f);assert v['instrument']==c
   rows=[r for r in v['bars'] if START<=r['date']<=END];dates=[r['date'] for r in rows]
   assert dates==sorted(set(dates)) and set(dates)<=set(sessions) and all(r['code']==c[:2].lower()+'.'+c[2:] for r in rows)
   for row in rows:
    assert row['tradestatus'] in ('0','1') and row['isST'] in ('0','1','')
    financial_core(row)
   missing=[d for d in expected if d not in set(dates)]
   prefixok=None
   if c in originals:
    oldrows=originals[c]['bars'];newrows=[r for r in rows if r['date']<=PRE_END]
    prefixok=([r['date'] for r in newrows]==[r['date'] for r in oldrows] and not overlapping_conflict(newrows,oldrows))
    for key in ('distributions','adjustments'):
     prefixok=prefixok and [r for r in v[key] if r['dividOperateDate']<=PRE_END]==originals[c][key]
    preconflict=preconflict or not prefixok
   choices.append({'source_directory':n,'source_packet_sha256':m['per_code_sha256'][c],'window':v['window'],
    'bars_in_required_window':len(rows),'missing_source_sessions':missing,'complete_through_Oct20':not missing,'original_pre2026_core_and_events_match':prefixok})
   payloads.append(rows)
  disagree=any(overlapping_conflict(x,y) for i,x in enumerate(payloads) for y in payloads[i+1:])
  if disagree:conflicts.append(c)
  if preconflict:prefix_conflicts.append(c)
  route=choices[0]['source_directory'] if choices and not disagree and not preconflict else None
  if not choices:no_cache.append(c)
  elif not choices[0]['missing_source_sessions']:complete.append(c)
  else:partial.append(c)
  items[c]={'priority_route':route,'choices':choices,'cross_cache_core_conflict':disagree,'original_prefix_conflict':preconflict,
   'original_pre2026_packet_present':c in originals,'expected_sessions':len(expected),'primary_bound_absent_sessions':len(sessions)-len(expected)}
 fixture={'date':'2026-01-05','code':'sz.000001','open':'10','high':'11','low':'9','close':'10','preclose':'10','volume':'1000','amount':'10000','tradestatus':'1','isST':'0'}
 changed=copy.deepcopy(fixture);changed['close']='10.01';assert overlapping_conflict([fixture],[changed])
 alternative=copy.deepcopy(fixture);alternative['close']='10.000';alternative['turn']='changed nonfinancial metadata';assert not overlapping_conflict([fixture],[alternative])
 tail=copy.deepcopy(fixture);tail['date']='2026-01-06';assert not overlapping_conflict([fixture],[fixture,tail])
 negatives={'changed_common_close_rejected':True,'numeric_string_format_not_false_conflict':True,'different_tail_coverage_not_false_conflict':True}
 result={'status':'FIXED127_COMPOSITE_RAW_CACHE_INVENTORY_ONLY_NOT_ADMISSION','candidate':'szse_value_momentum_equal','window':[START,END],
  'inventory_code_sha256':sha(__file__),'target_sha256':sha(target),'target_receipt_sha256':sha(base/FORM/'receipt.json'),'target_independent_audit_sha256':sha(auditfile),
  'original_pre2026_manifest_sha256':sha(base/OLD/'manifest.json'),'source_projection_summary_sha256':sha(base/SOURCE/'summary.json'),'lifecycle_sha256':sha(base/SOURCE/'lifecycles.json'),
  'source_priority_fixed_before_inventory':list(SOURCES),'source_manifest_sha256':{n:sha(base/n/'manifest.json') for n in SOURCES},
  'source_calendar_sha256':{n:sha(base/n/'calendar.json') for n in SOURCES},'explicit_full_source_sessions':len(sessions),
  'names':127,'original_pre2026_names':103,'complete_cached_names':complete,'partial_cached_names':partial,'uncached_names':no_cache,
  'cross_cache_raw_core_conflict_codes':conflicts,'original_pre2026_prefix_conflict_codes':prefix_conflicts,'items':items,
  'semantic_negative_controls_passed':negatives,'new_network_queries':0,'source_admitted_for_account':False,'corporate_action_completeness_verified':False,
  'cached_2026_raw_values_inspected':True,'portfolio_returns_computed':False,'investment_rules_changed':False,'objective_achieved':False}
 with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print('127names cacheinventory: full20',len(complete),'partial',len(partial),'uncached',len(no_cache),'conflicts',len(conflicts),'originalprefixconflicts',len(prefix_conflicts),'no queries/returns')
if __name__=='__main__':main()
