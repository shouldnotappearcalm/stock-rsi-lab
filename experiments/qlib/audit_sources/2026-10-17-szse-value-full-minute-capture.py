"""Capture only frozen full-window value-prefix requests; preserve all reused source bytes."""
import hashlib
import json
import time
from datetime import date,datetime,timezone
from importlib.metadata import version
from pathlib import Path
from eltdx import TdxClient,to_jsonable
from scripts.capture_low_risk_raw_account_data import source_code

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REQUEST=Path('experiments/qlib/szse-value-minute-full-request.json')
CAPTURE_PLAN=Path('experiments/qlib/szse-value-minute-full-capture-plan.json')
OUTPUT=BASE/'szse-value-minutes-full-20261017'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
request=json.loads(REQUEST.read_text());plan=json.loads(CAPTURE_PLAN.read_text())
assert plan['status']=='FROZEN_SZSE_VALUE_FULL_MINUTE_CAPTURE'
assert sha(REQUEST)==plan['request_sha256'] and sha(Path(__file__))==plan['capture_code_sha256']
assert sha(BASE/'szse-value-raw-full-20261017/manifest.json')==plan['raw_manifest_sha256']
assert sha(Path('experiments/qlib/szse-value-frozen-2026-targets.json'))==request['target_sha256']
assert version('eltdx')==plan['package_version']
manifests={};index={}
for name,expected in request['source_manifest_sha256'].items():
    assert Path(name).name==name and sha(BASE/name/'manifest.json')==expected
    manifest=json.loads((BASE/name/'manifest.json').read_text());manifests[name]=manifest
    for filename,h in manifest['per_session_sha256'].items():
        assert Path(filename).name==filename
        if filename in index:assert index[filename]['sha256']==h
        index.setdefault(filename,{'root':name,'sha256':h})
primary=set(manifests['tdx-fixed-order-history-20261017']['per_session_sha256'])
targets=json.loads(Path('experiments/qlib/szse-value-frozen-2026-targets.json').read_text());seen=set();expected_pairs=[]
for day,target in sorted(targets.items()):
    assert '2024-01-02'<=day<='2026-10-16' and target['as_of']<day
    seen.update(target['weights']);expected_pairs.extend([[code,day] for code in sorted(seen)])
assert request['requests']==expected_pairs
pairs=request['supplemental_requests'];assert len(pairs)==len({tuple(p) for p in pairs})
assert pairs==[p for p in request['requests'] if p[0]+'-'+p[1]+'.json' not in primary]
fresh=[p for p in pairs if p[0]+'-'+p[1]+'.json' not in index]
assert fresh==request['fresh_requests'] and all('2024-01-02'<=day<='2026-10-16' for code,day in fresh)
for code,day in pairs:
    source_code(code);assert '2024-01-02'<=day<='2026-10-16' and date.fromisoformat(day).isoformat()==day
if OUTPUT.exists():assert (OUTPUT/'plan.json').read_bytes()==CAPTURE_PLAN.read_bytes()
else:
    (OUTPUT/'sessions').mkdir(parents=True);(OUTPUT/'plan.json').write_bytes(CAPTURE_PLAN.read_bytes())
    (OUTPUT/'progress.json').write_text('{}\n')
progress=json.loads((OUTPUT/'progress.json').read_text())
expected_names={code+'-'+day+'.json' for code,day in pairs}
for name,h in progress.items():assert name in expected_names and sha(OUTPUT/'sessions'/name)==h
origins={};failures=0
with TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
    for number,(code,day) in enumerate(pairs,1):
        name=code+'-'+day+'.json';path=OUTPUT/'sessions'/name
        if name in index:
            origin=index[name];source=BASE/origin['root']/'sessions'/name
            assert sha(source)==origin['sha256']
            if not path.exists():path.write_bytes(source.read_bytes())
            assert sha(path)==origin['sha256'];origins[name]=origin
        elif name not in progress:
            assert not path.exists()
            packet={'instrument':code,'requested_day':day,'request_started_at':datetime.now(timezone.utc).isoformat()}
            try:
                value=client.minutes.history(code.lower(),day,include_raw=True)
                packet.update(status='RESPONSE_CAPTURED',response=to_jsonable(value),observed_at=datetime.now(timezone.utc).isoformat());failures=0
            except Exception as exc:
                packet.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300]);failures+=1
            path.write_text(json.dumps(packet,indent=2)+'\n')
        packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
        progress[name]=sha(path);(OUTPUT/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
        if number%50==0 or number==len(pairs):print(json.dumps({'captured':number,'total':len(pairs),'day':day}),flush=True)
        if failures>=3:break
        time.sleep(.05)
for name,origin in origins.items():
    assert progress.get(name)==origin['sha256']
manifest={'status':'SZSE_VALUE_FULL_SUPPLEMENTAL_MINUTE_CAPTURE_RECORDED','requested':len(pairs),'captured':len(progress),
    'plan_sha256':sha(OUTPUT/'plan.json'),'request_sha256':sha(REQUEST),'per_session_sha256':progress,
    'reused_session_provenance':origins,'all_reused_source_bytes_preserved':True,'new_pre2026_queries':False,'new_2026_queries':True,
    'historical_arrival_verified':False,'2026_strategy_returns_queried':False}
(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('value full minute capture finished',len(progress),flush=True)
