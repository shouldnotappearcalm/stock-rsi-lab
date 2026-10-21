"""Read-only fixed-source inventory; no account, performance report or network."""
import hashlib,json
from collections import Counter
from decimal import Decimal
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
ROOTS=('szse-value-momentum-raw-full-v2-20261021','low-beta60-raw-horizon-20261021','reversal-raw-full-20261017','szse-value-raw-full-20261017')
START,OLD_END,END='2023-12-29','2025-12-31','2026-10-20'
TARGET=B/'price-delay-horizon-formations-20261021/candidate_targets.json'
OUT=Path('/tmp/price-delay-horizon-raw-inventory-20261021.json')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def core(rows):return [[r['date'],r['code'],*[str(Decimal(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']] for r in rows]
def main():
 assert not OUT.exists(),'preserve prior inventory'
 assert sha(TARGET)=='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923'
 targets=read(TARGET);codes=sorted({c for t in targets.values() for c in t['weights']});assert len(codes)==203 and len(targets)==34
 manifests={n:read(B/n/'manifest.json') for n in ROOTS}
 cal=B/ROOTS[1]/'calendar.json';sessions=read(cal)['sessions'];assert len(sessions)==676 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END]
 oldraw=B/'price-delay-raw-dev-20261021';oldmanifest=read(oldraw/'manifest.json');oldcal=read(oldraw/'calendar.json')['sessions'];assert sessions[:486]==oldcal and sha(oldraw/'calendar.json')==oldmanifest['calendar_sha256']
 items={};references=0;prefix_conflicts=[];cross_conflicts=[]
 for code in codes:
  old=None
  if code in oldmanifest['per_code_sha256']:
   f=oldraw/'codes'/(code+'.json');assert sha(f)==oldmanifest['per_code_sha256'][code];old=read(f)
  choices=[];common=[]
  for root in ROOTS:
   m=manifests[root]
   if code not in m['per_code_sha256']:continue
   f=B/root/'codes'/(code+'.json');h=sha(f);assert h==m['per_code_sha256'][code];p=read(f);assert p['instrument']==code and p['window'][0]<=p['window'][1]<=END
   rows=[r for r in p['bars'] if START<=r['date']<=END];dates=[r['date'] for r in rows];assert dates==sorted(set(dates)) and all(r['code']==code[:2].lower()+'.'+code[2:] for r in rows)
   oldrows=[r for r in rows if r['date']<=OLD_END]
   overlap={}
   if old:
    overlap={'raw_core_matches_original':core(oldrows)==core(old['bars']),
     'distributions_match_original':[r for r in p['distributions'] if START<=r['dividOperateDate']<=OLD_END]==old['distributions'],
     'adjustments_match_original':[r for r in p['adjustments'] if START<=r['dividOperateDate']<=OLD_END]==old['adjustments']}
    if not all(overlap.values()):prefix_conflicts.append({'instrument':code,'root':root,'facts':overlap})
   choices.append({'root':root,'packet_sha256':h,'window':p['window'],'source_sessions':len(rows),
    'first_source_session':dates[0] if dates else None,'last_source_session':dates[-1] if dates else None,
    'complete_676_session_coverage':dates==sessions,'missing_sessions':[d for d in sessions if d not in set(dates)],
    'original_pre2026_overlap':overlap,'full_raw_core_sha256':digest(core(rows)),
    'accepted_distribution_rows_through_cutoff':sum(START<=r['dividOperateDate']<=END for r in p['distributions']),
    'accepted_adjustment_rows_through_cutoff':sum(START<=r['dividOperateDate']<=END for r in p['adjustments']),
    'quarantine_rows_not_admitted':len(p.get('quarantine',[]))})
   common.append((root,{r['date']:r for r in rows}));references+=1
  conflicts=[]
  for i,(a,left) in enumerate(common):
   for b,right in common[i+1:]:
    days=sorted(left.keys()&right.keys())
    if core([left[d] for d in days])!=core([right[d] for d in days]):conflicts.append([a,b])
  if conflicts:cross_conflicts.append({'instrument':code,'conflicting_roots':conflicts})
  complete=[x for x in choices if x['complete_676_session_coverage']]
  status='FULL_CACHE_AVAILABLE_NOT_ADMITTED' if complete else 'PARTIAL_CACHE_ONLY' if choices else 'NO_RAW_CACHE'
  items[code]={'status':status,'has_original_pre2026_baseline':old is not None,
   'fixed_priority_full_route':complete[0]['root'] if complete else None,'choices':choices,'common_date_core_conflicts':conflicts}
 result={'status':'UNCHANGED_PRICE_DELAY_HORIZON_RAW_COVERAGE_INVENTORY_NOT_ADMISSION','candidate':'price_delay_d1',
 'target_sha256':sha(TARGET),'window':[START,END],'names':203,'original_names':151,'additional_names':52,
 'source_priority_fixed_before_inventory':list(ROOTS),'source_manifest_sha256':{n:sha(B/n/'manifest.json') for n in ROOTS},
 'calendar_sha256':sha(cal),'calendar_sessions':676,'original_486_calendar_prefix_identical':True,
 'original_raw_manifest_sha256':sha(oldraw/'manifest.json'),'matching_cache_references':references,
 'status_counts':dict(Counter(v['status'] for v in items.values())),
 'original_prefix_differences':prefix_conflicts,'common_date_core_conflicts':cross_conflicts,'items':items,
 'inventory_code_sha256':sha(Path(__file__)),'protocol_sha256':sha(R/'docs/research/price-delay-horizon-raw-inventory-plan-2026-10-21.md'),
 'network_calls':0,'source_admitted_for_replay':False,'strategy_or_targets_changed':False,
 'portfolio_returns_computed':False,'prior_2026_strategy_performance_reports_read':False,'objective_achieved':False}
 OUT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['names','matching_cache_references','status_counts']}));print('prefix differences',len(prefix_conflicts),'common-date conflicts',len(cross_conflicts),'no source admission/account/ROI')
if __name__=='__main__':main()
