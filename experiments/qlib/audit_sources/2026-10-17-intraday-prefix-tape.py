"""Read-only supplementary minutes for a predeclared prefix holding universe."""
import hashlib
import json
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from eltdx import TdxClient, to_jsonable

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REQUEST=Path('experiments/qlib/intraday-prefix-tape-requests.json')
OUTPUT=BASE/'intraday-prefix-tape-20261017'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
request=json.loads(REQUEST.read_text())
assert request['target_sha256']=='2900729ad58c851764216093b26ca777eed9d4c6d1e75f528ae9bb26b9eecafb'
assert sha(BASE/'tdx-fixed-order-history-20261017/manifest.json')==request['parent_tape_manifest_sha256']
plan={'status':'FIXED_PREFIX_MINUTE_TAPE_CAPTURE','request_sha256':sha(REQUEST),'script_sha256':sha(Path(__file__)),
      'requests':request['missing_requests'],'host':'116.205.183.150:7709','package_version':version('eltdx'),
      'heartbeat_interval':None,'historical_arrival_verified':False,'used_for_policy_selection':False}
if OUTPUT.exists():assert json.loads((OUTPUT/'plan.json').read_text())==plan
else:
    (OUTPUT/'sessions').mkdir(parents=True);(OUTPUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
hashes={};failures=0
with TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
    for index,(code,day) in enumerate(plan['requests'],1):
        name=code+'-'+day+'.json';path=OUTPUT/'sessions'/name
        if path.exists():
            packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
        else:
            packet={'instrument':code,'requested_day':day,'request_started_at':datetime.now(timezone.utc).isoformat()}
            try:
                value=client.minutes.history(code.lower(),day,include_raw=True)
                packet.update(status='RESPONSE_CAPTURED',response=to_jsonable(value),observed_at=datetime.now(timezone.utc).isoformat());failures=0
            except Exception as exc:
                packet.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300]);failures+=1
            path.write_text(json.dumps(packet,indent=2)+'\n')
        hashes[name]=sha(path)
        if index%25==0 or index==len(plan['requests']):print(json.dumps({'captured':index,'total':len(plan['requests']),'instrument':code,'day':day}),flush=True)
        if failures>=3:break
        time.sleep(.05)
manifest={k:v for k,v in plan.items() if k!='requests'}
manifest.update(status='PREFIX_MINUTE_TAPE_CAPTURE_RECORDED',plan_sha256=sha(OUTPUT/'plan.json'),
                requested=len(plan['requests']),captured=len(hashes),per_session_sha256=hashes)
(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('prefix capture finished',len(hashes),flush=True)
