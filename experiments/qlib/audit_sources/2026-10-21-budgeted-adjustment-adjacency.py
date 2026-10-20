"""Classify existing next-session adjustment rows without inventing entitlements."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.run_low_risk_raw_share_validation import validate_source_coverage

p=argparse.ArgumentParser()
for n in ('raw-data-dir','raw-audit','output'):p.add_argument('--'+n,required=True)
a=p.parse_args();root=Path(a.raw_data_dir);repo=Path(__file__).resolve().parents[3]
h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert h(root/'manifest.json')==h(repo/'experiments/qlib/budgeted-residual-raw-source-capture-manifest.json')
assert h(a.raw_audit)==h(repo/'experiments/qlib/budgeted-residual-raw-source-audit.json')
m=json.loads((root/'manifest.json').read_text());audit=json.loads(Path(a.raw_audit).read_text());packets={}
assert m['window']==['2023-12-29','2025-12-31'] and audit['capture_manifest_sha256']==h(root/'manifest.json')
for c,digest in m['per_code_sha256'].items():
 f=root/'codes'/(c+'.json');assert h(f)==digest
 packet=json.loads(f.read_text());assert packet['window']==m['window'] and packet['instrument']==c
 assert all('2023-12-29'<=r['date']<='2025-12-31' for r in packet['bars']);packets[c]=packet
validate_source_coverage(packets)
cases=[]
for c,d in audit['adjustments_without_distribution']:
 packet=packets[c];i=next(i for i,r in enumerate(packet['bars']) if r['date']==d);assert i>0
 prior=packet['bars'][i-1]['date'];div=[r for r in packet['distributions'] if r['dividOperateDate']==prior];assert len(div)==1
 j=next(j for j,r in enumerate(packet['adjustments']) if r['dividOperateDate']==d);assert j>0
 x,y=packet['adjustments'][j-1:j+1]
 assert x['dividOperateDate']==prior and all(x[f]==y[f] for f in ('foreAdjustFactor','backAdjustFactor'))
 assert packet['bars'][i]['preclose']==packet['bars'][i-1]['close']
 cases.append({'instrument':c,'adjustment_day':d,'previous_exchange_session':prior,
  'separately_recorded_distribution':div[0],'previous_adjustment':x,'next_session_adjustment':y,
  'raw_previous_close':packet['bars'][i-1]['close'],'raw_current_preclose':packet['bars'][i]['preclose'],
  'source_packet_sha256':m['per_code_sha256'][c],
  'classification':'NEXT_EXCHANGE_SESSION_ADJUSTMENT_RECORD_BESIDE_EXISTING_DISTRIBUTION',
  'new_entitlement_created':False})
assert len(cases)==9
result={'status':'EXISTING_SOURCE_COVERAGE_GATE_PASSES_ALL210_NINE_ADJACENT_RECORDS_CLASSIFIED',
 'audit_code_sha256':h(__file__),'raw_manifest_sha256':h(root/'manifest.json'),'original_audit_sha256':h(a.raw_audit),
 'existing_coverage_code_file':'scripts/run_low_risk_raw_share_validation.py',
 'existing_coverage_code_sha256':h(repo/'scripts/run_low_risk_raw_share_validation.py'),'cases':cases,
 'source_or_evaluator_modified':False,'additional_cash_or_shares_inferred':False,
 'new_portfolio_returns_computed':False,'2026_values_queried':False,'account_replay_admitted':False,'objective_achieved':False}
out=Path(a.output);assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n')
print('Existing210sourcecoverage and9adjacentdistributionrecords verified; nonewentitlements')
