"""Foreground, bounded raw history capture for every fixed feedback order day."""
import hashlib
import json
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from eltdx import TdxClient, to_jsonable

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
ROOT=BASE/'low-risk-feedback-cost-20261017'
OUTPUT=BASE/'tdx-fixed-order-history-20261017'
EXPECTED_SUMMARY='1c1ebd67e9d87ca4004b2d39b6c74aa8eb8f1ae20fdcfd4c23ece9f2eeb71006'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(ROOT/'summary.json')==EXPECTED_SUMMARY
summary=json.loads((ROOT/'summary.json').read_text());requests=set()
for bps,cases in summary['results_by_extra_bps_and_initial_CNY'].items():
    for capital,case in cases.items():
        if 'artifact_sha256' not in case:
            assert case['status']=='INVALID_SINGLE_ORDER_LIMIT'
            continue
        path=ROOT/bps/capital/'orders.json';assert sha(path)==case['artifact_sha256']['orders.json']
        for order in json.loads(path.read_text()):
            if order['eligible_at']:
                assert order['eligible_at'].endswith('T01:30:00+00:00')
                requests.add((order['security_id'],order['eligible_at'][:10]))
assert len(requests)==1299
plan={'status':'FIXED_ORDER_TDX_HISTORY_CAPTURE','script_sha256':sha(Path(__file__)),
      'feedback_summary_sha256':EXPECTED_SUMMARY,'requests':[list(key) for key in sorted(requests)],
      'host':'116.205.183.150:7709','package':'eltdx','package_version':version('eltdx'),
      'source_commit_inspected':'f6287f69f68354b4b550d132ebec565ee749fa8d',
      'timeout_seconds':3,'opening_match_max_pages':[4,16],'sleep_between_pairs_seconds':.1,
      'heartbeat_interval':None,'probe_hosts':False,'used_for_decision':False,
      'historical_arrival_verified':False,'server_echoed_historical_date_certified':False,
      'volume_unit_per_SDK_documentation':'hands of 100 shares, finite source precision; not exact exchange shares',
      'auction_impact_or_queue_fill_certified':False}
if OUTPUT.exists():
    assert json.loads((OUTPUT/'plan.json').read_text())==plan,'resume identity changed; retain original capture'
else:
    (OUTPUT/'sessions').mkdir(parents=True)
    (OUTPUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
hashes={};statuses={};consecutive_failed_pairs=0
with TdxClient(host=plan['host'],timeout=3,heartbeat_interval=None,probe_hosts=False) as client:
    for number,(code,day) in enumerate(sorted(requests),1):
        name=code+'-'+day+'.json';path=OUTPUT/'sessions'/name
        if path.exists():
            saved=json.loads(path.read_text());assert saved['instrument']==code and saved['requested_day']==day
        else:
            started=datetime.now(timezone.utc).isoformat()
            saved={'instrument':code,'requested_day':day,'request_started_at':started,'methods':{}}
            for method in ('minutes.history','trades.opening_match_history'):
                before=time.monotonic()
                try:
                    if method=='minutes.history':
                        value=client.minutes.history(code.lower(),day,include_raw=True)
                        pages=None
                    else:
                        pages=4;value=client.trades.opening_match_history(code.lower(),day,include_raw=True,max_pages=pages)
                        if value is None:
                            pages=16;value=client.trades.opening_match_history(code.lower(),day,include_raw=True,max_pages=pages)
                    saved['methods'][method]={'status':'RESPONSE_CAPTURED' if value is not None else 'NO_MATCH_WITHIN_BOUNDED_SCAN',
                        'max_pages':pages,'response':to_jsonable(value),
                        'elapsed_seconds':round(time.monotonic()-before,3),
                        'observed_at':datetime.now(timezone.utc).isoformat()}
                except Exception as exc:
                    saved['methods'][method]={'status':'REQUEST_FAILED','error_type':type(exc).__name__,
                        'error':str(exc)[:300],'elapsed_seconds':round(time.monotonic()-before,3)}
            saved['completed_at']=datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(saved,indent=2)+'\n')
        hashes[name]=sha(path);statuses[name]={key:value['status'] for key,value in saved['methods'].items()}
        failed=all(value['status']=='REQUEST_FAILED' for value in saved['methods'].values())
        consecutive_failed_pairs=consecutive_failed_pairs+1 if failed else 0
        if number%25==0 or number==len(requests):print(json.dumps({'captured':number,'total':len(requests),'instrument':code,'day':day}),flush=True)
        if consecutive_failed_pairs>=3:
            print('three consecutive failed pairs; preserve uncaptured remainder',flush=True);break
        time.sleep(.1)
manifest={key:value for key,value in plan.items() if key!='requests'}
manifest.update(status='RAW_TDX_HISTORY_CAPTURE_RECORDED',requested_code_sessions=len(requests),
                captured_code_sessions=len(hashes),plan_sha256=sha(OUTPUT/'plan.json'),
                per_session_sha256=hashes,status_by_session=statuses)
(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({key:value for key,value in manifest.items() if key not in ('per_session_sha256','status_by_session')},indent=2),flush=True)
