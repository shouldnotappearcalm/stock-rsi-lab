"""Read-only inventory of151 fixed price-delay names; pre2026 packets only."""
import argparse,json,hashlib
from pathlib import Path
from decimal import Decimal
from scripts.capture_frozen_target_development_data import target_codes,clipped_packet
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,validate_bars
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
SOURCES=('budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020',
 'low-beta60-raw-dev-20261021','szse-value-momentum-raw-dev-20261021',
 'return-families-raw-dev-20261017','szse-value-raw-dev-20261017')
TARGET_SHA='03acf78c10c10376b5764b0d1399d1631af08a608aa865575aa1bd56203fad0c'

def core_fingerprint(packet):
 rows=[]
 for r in packet['bars']:
  rows.append([r['date'],r['code'],*[str(Decimal(r[k]).normalize()) if r[k] else '' for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']])
 return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--output',required=True);a=p.parse_args();base=Path(a.source_root);out=Path(a.output)
 if out.exists():raise ValueError('preserve prior inventory')
 target=base/'price-delay-pre2026-formations-20261021/targets.json'
 if sha256_file(target)!=TARGET_SHA:raise ValueError('frozen target changed')
 codes=target_codes(json.loads(target.read_text())['price_delay_d1']);calendar_path=base/'qlib-price-delay-pre2026-clock-v2-20261021/calendars/day.txt';calendar=[d for d in calendar_path.read_text().splitlines() if '2023-12-29'<=d<='2025-12-31']
 if len(codes)!=151 or len(calendar)!=486:raise ValueError('frozen151names/486source sessions required')
 manifests={n:json.loads((base/n/'manifest.json').read_text()) for n in SOURCES};items={};missing=[];conflicts=[]
 for n,m in manifests.items():
  if m.get('window')!=['2023-12-29','2025-12-31']:raise ValueError('only physically pre2026 packet sources permitted')
 for c in codes:
  choices=[]
  for n in SOURCES:
   m=manifests[n]
   if c not in m['per_code_sha256']:continue
   src=base/n/'codes'/(c+'.json');expected=m['per_code_sha256'][c]
   if sha256_file(src)!=expected:raise ValueError('original cache hash changed')
   packet=json.loads(src.read_text())
   if packet['instrument']!=c or packet['window']!=['2023-12-29','2025-12-31']:raise ValueError('source identity or pre2026 packet window changed')
   clipped=clipped_packet(packet);validate_bars(c,BAR_FIELDS,[[r[k] for k in BAR_FIELDS] for r in clipped['bars']])
   choices.append({'source_directory':n,'original_packet_sha256':expected,'original_window':packet['window'],
    'full_486_source_calendar': [r['date'] for r in clipped['bars']]==calendar,
    'missing_sessions':[d for d in calendar if d not in {r['date'] for r in clipped['bars']}],
    'pre2026_raw_core_sha256':core_fingerprint(clipped),'distributions_in_window':len(clipped['distributions']),
    'adjustments_in_window':len(clipped['adjustments'])})
  if not choices:missing.append(c);items[c]={'status':'NO_EXISTING_RAW_PACKET','choices':[]};continue
  disagree=len({x['pre2026_raw_core_sha256'] for x in choices})>1
  if disagree:conflicts.append(c)
  items[c]={'status':'RAW_CORE_CONTRADICTION_REQUIRES_REVIEW' if disagree else 'EXISTING_ORIGINALS_AUTHENTICATED_NOT_ADMITTED',
   'priority_route':choices[0]['source_directory'],'choices':choices}
 result={'status':'PRICE_DELAY_PRE2026_ONLY_RAW_CACHE_INVENTORY_ONLY','target_sha256':TARGET_SHA,'candidate':'price_delay_d1','names':len(codes),'window':['2023-12-29','2025-12-31'],
  'method_sha256':sha256_file(__file__),'helper_sha256':sha256_file(Path(__file__).with_name('capture_frozen_target_development_data.py')),
  'validation_sha256':sha256_file(Path(__file__).with_name('capture_low_risk_raw_account_data.py')),
  'source_manifests_sha256':{n:sha256_file(base/n/'manifest.json') for n in SOURCES},'reference_calendar_sha256':sha256_file(calendar_path),
  'source_priority_fixed_before_inventory':list(SOURCES),'existing_names':len(codes)-len(missing),'fresh_codes':missing,'raw_core_conflict_codes':conflicts,
  'new_network_queries':0,'source_admitted_for_replay':False,'corporate_action_completeness_verified':False,
  'historical_arrival_verified':False,'original_cache_may_include_later_bytes':False,'date_indexed_2026_values_used':False,
  'strategy_or_targets_changed':False,'portfolio_returns_computed':False,'objective_achieved':False,'items':items}
 with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
 print('rawcache',result['existing_names'],'/',len(codes),'fresh',len(missing),'core conflicts',len(conflicts),'no network/ROI')
if __name__=='__main__':main()
