"""Read-only source admission for all registered development prefix code-sessions."""
import hashlib,json
from collections import Counter
from datetime import date
from pathlib import Path
from scripts.run_low_risk_intraday_replay import TapeBank
from scripts.tdx_history_checks import inspect_minutes
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('experiments/qlib/szse-value-minute-development-request.json')
RAW=B/'szse-value-raw-dev-20261017';OLD=B/'tdx-fixed-order-history-20261017';EXTRA=B/'szse-value-minutes-dev-20261017'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
request=json.loads(R.read_text());raw=json.loads((RAW/'manifest.json').read_text())
plan=json.loads((EXTRA/'plan.json').read_text());manifest=json.loads((EXTRA/'manifest.json').read_text())
assert sha(R)==plan['request_sha256'] and sha(RAW/'manifest.json')==plan['raw_manifest_sha256']
assert manifest['captured']==manifest['requested']==len(request['supplemental_requests'])
assert sha(EXTRA/'plan.json')==manifest['plan_sha256']
assert sha(OLD/'manifest.json')==request['source_manifest_sha256'][OLD.name]
packets={}
for code,h in raw['per_code_sha256'].items():
 p=RAW/'codes'/(code+'.json');assert sha(p)==h;packets[code]=json.loads(p.read_text())
bars={c:{r['date']:r for r in p['bars']} for c,p in packets.items()}
bank=TapeBank(OLD,EXTRA,bars,'2025-12-31');rows=[]
for code,day in request['requests']:
 row={'instrument':code,'day':day};source=bars[code][day];path,h=bank.index[(code,day)]
 assert sha(path)==h
 packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
 record=packet.get('methods',{}).get('minutes.history',packet)
 row.update(source_sha256=h,raw_tradestatus=source['tradestatus'],captured_status=record['status'])
 try:
  if source['tradestatus']=='0':
   if record['status']=='RESPONSE_CAPTURED':
    assert not any(p['volume'] for p in record['response']['points']), 'positive minute volume on original halt'
   row['status']='RAW_HALT_NO_EXECUTABLE_TAPE_REQUIRED'
  else:
   windows=bank(code,date.fromisoformat(day))
   row.update(status='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE',windows=len(windows),
       facts=inspect_minutes(code,day,record['response'],source))
 except (ValueError,KeyError,AssertionError) as exc:
  row.update(status='SOURCE_REJECTED',error=str(exc))
 rows.append(row)
counts=dict(Counter(r['status'] for r in rows));assert len(rows)==len(request['requests'])
result={'status':'SZSE_VALUE_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE','audit_code_sha256':sha(Path(__file__)),
 'request_sha256':sha(R),'raw_manifest_sha256':sha(RAW/'manifest.json'),
 'old_tape_manifest_sha256':sha(OLD/'manifest.json'),'extra_tape_manifest_sha256':sha(EXTRA/'manifest.json'),
 'required_sessions':len(rows),'status_counts':counts,
 'admitted_for_reconstructed_execution':counts.get('SOURCE_REJECTED',0)==0,
 'full_series_labels_prices_ranges_and_stressed_volume_checked':True,
 'source_volume_unit':'hands; whole-day stressed lower shares cap only; exact share precision not certified',
 'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,
 'queue_and_impact_calibrated':False,'2026_strategy_returns_queried':False,'objective_achieved':False,
 'exceptions':[r for r in rows if r['status']!='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE']}
full=B/'szse-value-minute-admission-20261017.json';assert not full.exists()
full.write_text(json.dumps({'summary':result,'sessions':rows},indent=2)+'\n')
result['local_detail_sha256']=sha(full)
out=Path('experiments/qlib/szse-value-development-minute-admission.json');assert not out.exists()
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
