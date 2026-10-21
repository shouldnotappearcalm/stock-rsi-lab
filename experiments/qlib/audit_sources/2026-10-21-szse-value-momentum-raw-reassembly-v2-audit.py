from pathlib import Path
import json,hashlib
b=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');repo=Path.cwd();raw=b/'szse-value-momentum-raw-full-v2-20261021';v1=b/'szse-value-momentum-raw-full-20261021';old=b/'szse-value-momentum-raw-dev-20261021';r=lambda p:json.loads(Path(p).read_bytes());h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();m=r(raw/'manifest.json');prior=r(v1/'manifest.json');om=r(old/'manifest.json');request=r(repo/'experiments/qlib/szse-value-momentum-raw-reassembly-v2-request.json');sessions=r(raw/'calendar.json')['sessions']
assert len(m['per_code_sha256'])==127 and len(sessions)==676 and h(raw/'calendar.json')==m['calendar_sha256']
for c,s in m['per_code_sha256'].items():
 f=raw/'codes'/(c+'.json');assert h(f)==s;p=r(f);assert p['instrument']==c and [row['date'] for row in p['bars']]==[d for d in sessions if c!='SZ001389' or d>='2024-04-02']
 if c in prior['per_code_sha256']:assert f.read_bytes()==(v1/'codes'/(c+'.json')).read_bytes()
 if c in om['per_code_sha256']:
  o=r(old/'codes'/(c+'.json'));assert h(old/'codes'/(c+'.json'))==om['per_code_sha256'][c]
  for k,day in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:assert [row for row in p[k] if row[day]<='2025-12-31']==o[k]
for name,s in request['v1_artifact_sha256'].items():assert h(v1/name)==s
for name,s in request['financial_artifact_sha256'].items():assert h(b/name)==s
checks=r(raw/'coordinate_checks.json');assert h(raw/'coordinate_checks.json')==m['coordinate_checks_sha256'];assert sorted(checks)==['SZ000563','SZ000783','SZ002608','SZ002756']
result={'raw_manifest_sha256':h(raw/'manifest.json'),'all127_packets_authenticated':True,'all123_accepted_packets_byte_exact':True,'all_original103_prefixes_identical':True,'all54_original_financial_files_unchanged':True,'all_v1_source_bytes_and_four_errors_unchanged':True,'coordinate_revisions':sorted(checks),'source_queries':0,'portfolio_returns_computed':False,'account_admission':False}
p=b/'szse-value-momentum-raw-reassembly-v2-audit-20261021.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
