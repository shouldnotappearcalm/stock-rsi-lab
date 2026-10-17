"""Immutable supplemental development minutes; no 2026 request is permitted."""
import hashlib
import json
import time
from datetime import date,datetime,timezone
from importlib.metadata import version
from pathlib import Path
from eltdx import TdxClient,to_jsonable
from scripts.capture_low_risk_raw_account_data import source_code

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REQUEST=Path('experiments/qlib/return-families-minute-development-request.json')
OUTPUT=BASE/'return-family-minutes-dev-20261017'
EXTRA=BASE/'intraday-prefix-tape-20261017'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
request=json.loads(REQUEST.read_text())
assert request['window_end']=='2025-12-31' and request['new_2026_market_queries_allowed'] is False
assert request['target_sha256']==sha(Path('experiments/qlib/return-families-selected-dev-targets.json'))
assert sha(BASE/'tdx-fixed-order-history-20261017/manifest.json')==request['parent_tape_manifest_sha256']
assert sha(EXTRA/'manifest.json')==request['reusable_extra_manifest_sha256']
pairs=request['missing_requests'];assert len(pairs)==len({tuple(p) for p in pairs})
for code,day in pairs:
    source_code(code);assert '2024-01-02'<=day<='2025-12-31' and date.fromisoformat(day).isoformat()==day
extra=json.loads((EXTRA/'manifest.json').read_text())['per_session_sha256']
plan={'status':'FIXED_PRE2026_PREFIX_MINUTE_CAPTURE','request_sha256':sha(REQUEST),
      'script_sha256':sha(Path(__file__)),'requests':pairs,'host':'116.205.183.150:7709',
      'package_version':version('eltdx'),'heartbeat_interval':None,'historical_arrival_verified':False,
      'used_for_policy_selection':False,'new_2026_market_queries_allowed':False}
if OUTPUT.exists():assert json.loads((OUTPUT/'plan.json').read_text())==plan
else:
    (OUTPUT/'sessions').mkdir(parents=True);(OUTPUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
hashes={};origins={};failures=0
with TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
    for index,(code,day) in enumerate(pairs,1):
        name=code+'-'+day+'.json';path=OUTPUT/'sessions'/name
        if name in extra:
            source=EXTRA/'sessions'/name;assert sha(source)==extra[name]
            if not path.exists():path.write_bytes(source.read_bytes())
            assert sha(path)==extra[name];origins[name]={'route':'IMMUTABLE_PRIOR_CAPTURE','source_sha256':extra[name]}
        elif not path.exists():
            packet={'instrument':code,'requested_day':day,'request_started_at':datetime.now(timezone.utc).isoformat()}
            try:
                value=client.minutes.history(code.lower(),day,include_raw=True)
                packet.update(status='RESPONSE_CAPTURED',response=to_jsonable(value),observed_at=datetime.now(timezone.utc).isoformat());failures=0
            except Exception as exc:
                packet.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300]);failures+=1
            path.write_text(json.dumps(packet,indent=2)+'\n')
        packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
        hashes[name]=sha(path)
        if index%25==0 or index==len(pairs):print(json.dumps({'captured':index,'total':len(pairs),'instrument':code,'day':day}),flush=True)
        if failures>=3:break
        time.sleep(.05)
manifest={k:v for k,v in plan.items() if k!='requests'}
manifest.update(status='PRE2026_SUPPLEMENTAL_MINUTE_CAPTURE_RECORDED',plan_sha256=sha(OUTPUT/'plan.json'),
    requested=len(pairs),captured=len(hashes),per_session_sha256=hashes,reused_session_provenance=origins)
(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('development minute capture finished',len(hashes),flush=True)
