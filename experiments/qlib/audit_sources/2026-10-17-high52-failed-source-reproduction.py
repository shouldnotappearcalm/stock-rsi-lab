"""Exactly two independent reproductions of one pre2026 protocol error."""
import hashlib,json
from datetime import datetime,timezone
from importlib.metadata import version
from pathlib import Path
from eltdx import TdxClient,to_jsonable
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('experiments/qlib/high52-failed-source-reproduction-request.json')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads(R.read_text());assert sha(Path(__file__))==p['capture_code_sha256']
failed=B/'high52-unfilled-source-probe-20261017/sessions/SH603056-2025-06-03.json'
assert sha(failed)==p['original_failure_sha256'] and p['pair']==['SH603056','2025-06-03']
assert p['hosts']==['116.205.183.150:7709','116.205.171.132:7709'] and version('eltdx')==p['package_version']
out=B/'high52-source-error-reproduction-20261017';assert not out.exists();out.mkdir();results=[]
for n,host in enumerate(p['hosts'],1):
 row={'instrument':p['pair'][0],'requested_day':p['pair'][1],'host':host,'started_at':datetime.now(timezone.utc).isoformat()}
 try:
  with TdxClient(host=host,timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
   row.update(status='RESPONSE_CAPTURED',response=to_jsonable(client.minutes.history('sh603056','2025-06-03',include_raw=True)))
 except Exception as exc:row.update(status='REQUEST_FAILED',error_type=type(exc).__name__,error=str(exc)[:300])
 path=out/(str(n)+'.json');path.write_text(json.dumps(row,indent=2)+'\n');results.append({'file':path.name,'sha256':sha(path),'host':host,'status':row['status']})
manifest={'status':'HIGH52_SINGLE_SOURCE_ERROR_REPRODUCTION_COMPLETE','request_sha256':sha(R),'results':results,
 'original_failure_sha256':sha(failed),'old_source_overwritten':False,'2026_market_values_queried':False,'new_portfolio_account_run':False,'objective_achieved':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
