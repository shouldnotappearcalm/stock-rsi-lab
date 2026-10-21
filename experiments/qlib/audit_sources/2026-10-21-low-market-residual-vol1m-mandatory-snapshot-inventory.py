"""Bounded required-target-snapshot source-state check, without production imports.
No account simulation, price/return calculation, ticker deletion, or source query.
"""
from pathlib import Path
from collections import Counter
import hashlib,json
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
I=Path('/tmp/low-market-residual-vol1m-pre2026-raw-source-inventory-20261021.json')
T=B/'low-market-residual-vol1m-budgeted-pre2026-development-20261021/targets.json'
OUT=Path('/tmp/low-market-residual-vol1m-pre2026-mandatory-snapshot-inventory-20261021.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
initial_inventory_hash=sha(I);assert initial_inventory_hash=='9fbfed7d880974a1e1f49193dae169a7c0416732123202a67ca327c5cae21eb4'
i=read(I);targethash=sha(T);assert targethash==i['target_sha256'];targets=read(T)['low_market_residual_vol_1m'];assert len(targets)==24
assert len(i['selected_reuse'])==301 and len(i['missing_or_incomplete_instruments'])==60
packets={};binding={}
# Only the301 previously selected complete pre2026 packets are opened.
for c,s in i['selected_reuse'].items():
 p=B/s['file'];d=B/s['directory'];assert sha(d/'manifest.json')==s['manifest_sha256'];m=read(d/'manifest.json');assert m['window']==['2023-12-29','2025-12-31'];assert sha(p)==s['packet_sha256']==m['per_code_sha256'][c]
 packet=read(p);assert packet['instrument']==c and packet['window']==m['window'];rows={r['date']:r for r in packet['bars']};assert len(rows)==len(packet['bars'])==486
 assert all('2023-12-29'<=day<='2025-12-31' for day in rows)
 packets[c]=rows;binding[c]={'file':s['file'],'packet_sha256':s['packet_sha256'],'manifest_sha256':s['manifest_sha256']}
covered=[];unknown=[];conflicts=[];halted=[];monthly=[]
for execution,t in targets.items():
 asof=t['as_of'];assert '2023-12-29'<=asof<execution<='2025-12-31'
 month=[]
 for c,w in t['weights'].items():
  assert w>0
  rec={'execution_session':execution,'formation_asof':asof,'instrument':c,'mandatory_reason':'FROZEN_POSITIVE_WEIGHT_TARGET_PRIOR_CLOSE_SNAPSHOT','source_state_can_change_target':False}
  if c not in packets:
   rec.update(status='UNKNOWN_NOT_IN301_COMPLETE_CACHE_SCOPE',source_isST=None,source_tradestatus=None,ordinary_guard_snapshot_pass=None);unknown.append(rec)
  else:
   r=packets[c].get(asof);assert r is not None
   st=r.get('isST');ts=r.get('tradestatus');rec.update(source_isST=st,source_tradestatus=ts,source_binding=binding[c])
   if st not in ('0','1') or type(st) is not str:
    rec.update(status='KNOWN_INVALID_OR_MISSING_ORDINARY_STATE',ordinary_guard_snapshot_pass=False);conflicts.append(rec)
   elif st=='1':
    rec.update(status='KNOWN_MANDATORY_NONORDINARY_CONFLICT',ordinary_guard_snapshot_pass=False);conflicts.append(rec)
   else:rec.update(status='COVERED_ORDINARY_STATE_AT_REQUIRED_SNAPSHOT',ordinary_guard_snapshot_pass=True)
   # Halt is retained separately; ST guard does not equate tradestatus0 with isST1.
   if ts=='0':halted.append(rec)
   elif ts!='1':rec['trade_status_metadata_question']=True
   covered.append(rec)
  month.append(rec)
 monthly.append({'execution_session':execution,'formation_asof':asof,'positive_target_names':len(month),'covered':sum(r['status']!='UNKNOWN_NOT_IN301_COMPLETE_CACHE_SCOPE' for r in month),'unknown':sum(r['status']=='UNKNOWN_NOT_IN301_COMPLETE_CACHE_SCOPE' for r in month),'known_conflicts':sum(r['ordinary_guard_snapshot_pass'] is False for r in month),'target_instruments':list(t['weights'])})
assert len(covered)+len(unknown)==sum(len(t['weights']) for t in targets.values())
for c,b in binding.items():assert sha(B/b['file'])==b['packet_sha256']
assert sha(T)==targethash and sha(I)==initial_inventory_hash
report={'status':'KNOWN_MANDATORY_SNAPSHOT_CONFLICT_FOUND' if conflicts else 'BOUNDED_MANDATORY_SNAPSHOT_INVENTORY_COMPLETE_UNKNOWN_NOT_PASS','candidate':'low_market_residual_vol_1m','target_sha256':targethash,'inventory_file':str(I),'inventory_sha256':initial_inventory_hash,'target_months':24,'target_union_names':361,'complete_packet_scope':301,'unknown_name_scope':60,'mandatory_target_snapshots':len(covered)+len(unknown),'covered_snapshots':len(covered),'unknown_snapshots':len(unknown),'known_conflict_snapshots':len(conflicts),'covered_unique_names':len({r['instrument'] for r in covered}),'unknown_unique_names':len({r['instrument'] for r in unknown}),'known_conflict_unique_names':len({r['instrument'] for r in conflicts}),'known_conflicts':conflicts,'halted_target_snapshot_rows':halted,'covered_snapshots_detail':covered,'unknown_snapshots_detail':unknown,'monthly_coverage':monthly,'source_binding_by_instrument':binding,'ordinary_guard_method':{'file':'src/stock_rsi/ordinary_source_scope.py','sha256':sha(R/'src/stock_rsi/ordinary_source_scope.py'),'semantics':'A required dependency row with isST exactly string1 raises; missing/invalid explicit isST also raises. A positive frozen target requires its as_of close snapshot. tradestatus0 is reported separately and is not itself the isST guard.'},'all_required_snapshots_ordinary_proven':False,'known_snapshot_conflict_blocks_raw_account_without_rule_change':bool(conflicts),'original_inventory_unchanged':True,'targets_or_tickers_or_thresholds_changed':False,'unknown_treated_as_pass':False,'missing60_packets_opened':False,'account_replay_performed':False,'portfolio_returns_computed':False,'source_queries':0,'2026_values_read':False,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'scope_limitations':['Checks only mandatory positive-weight target prior-close snapshots; does not infer actual holdings, future pending entitlements/orders, or account dependency states.','A covered ordinary target snapshot does not certify the entire holding interval, lifecycle, tax, raw-source completeness or execution eligibility.','Unknown60names and their required snapshots remain unknown; no unknown source is promoted to ordinary.','Existing target and source bytes are unchanged. No source or strategy rule is relaxed to avoid a conflict.']}
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(OUT),'sha256':sha(OUT),'audit_code_sha256':report['audit_code_sha256'],'counts':{k:report[k] for k in ('mandatory_target_snapshots','covered_snapshots','unknown_snapshots','known_conflict_snapshots','known_conflict_unique_names')},'conflicts':conflicts,'halted':halted},ensure_ascii=False,indent=2))
