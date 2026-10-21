import json
from pathlib import Path
from scripts.inventory_low_beta60_sources import core_fingerprint
from scripts.capture_frozen_target_development_data import clipped_packet
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
base=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');target=base/'szse-value-momentum-formations-pre2026-20261021/targets.json';targets=json.loads(target.read_bytes())['szse_value_momentum_equal'];codes=sorted({c for t in targets.values() for c in t['weights']})
priority=('low-beta60-raw-dev-20261021','budgeted-residual-raw-dev-20261021','illiquidity-raw-source-continuation-20261020','return-families-raw-dev-20261017','szse-value-raw-dev-20261017')
manifests={n:json.loads((base/n/'manifest.json').read_bytes()) for n in priority};sessions=json.loads((base/'low-beta60-raw-dev-20261021/calendar.json').read_bytes())['sessions'];assert len(sessions)==486
items={};missing=[];conflicts=[]
for c in codes:
 choices=[]
 for n,m in manifests.items():
  if c not in m['per_code_sha256']:continue
  src=base/n/'codes'/(c+'.json');assert sha256_file(src)==m['per_code_sha256'][c];packet=json.loads(src.read_bytes());assert packet['instrument']==c
  if packet['window']!=['2023-12-29','2025-12-31']:continue
  p=clipped_packet(packet);choices.append({'source_directory':n,'source_sha256':sha256_file(src),'raw_core_sha256':core_fingerprint(p),'full486_calendar':[r['date'] for r in p['bars']]==sessions,'distributions':len(p['distributions']),'adjustments':len(p['adjustments'])})
 if not choices:missing.append(c)
 elif len({x['raw_core_sha256'] for x in choices})>1:conflicts.append(c)
 items[c]={'priority_route':choices[0]['source_directory'] if choices else None,'choices':choices}
v={'status':'FIXED_VALUE_MOMENTUM_PRE2026_SOURCE_INVENTORY_ONLY_NOT_ADMISSION','target_sha256':sha256_file(target),'names':len(codes),'source_priority':list(priority),'source_manifest_sha256':{n:sha256_file(base/n/'manifest.json') for n in priority},'existing_names':len(codes)-len(missing),'missing_codes':missing,'conflicting_codes':conflicts,'items':items,'source_queries':0,'portfolio_returns_computed':False,'date_indexed_2026_market_values_used':False,'raw_quarantine_or_provenance_may_reference_later_dates':True,'source_admitted_for_replay':False}
out=Path('/tmp/szse-value-momentum-raw-source-inventory-20261021.json');out.write_text(json.dumps(v,indent=2)+'\n');print('sourceinventory',v['existing_names'],'/',len(codes),'missing',missing,'conflicts',conflicts,'completechoices',sum(x['full486_calendar'] for v in items.values() for x in v['choices']))
