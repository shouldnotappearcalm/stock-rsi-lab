"""Capture only newly generated fixed-policy order sessions, read-only API."""
import hashlib
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

from scripts.capture_low_risk_execution_tape import FIELDS, validate_minutes
from scripts.capture_low_risk_raw_account_data import query_rows, source_code

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
ROOT=BASE/'low-risk-feedback-cost-20261017'
OLD=BASE/'low-risk-execution-tape-20261017'
OUTPUT=BASE/'low-risk-feedback-tape-additions-20261017'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert not OUTPUT.exists(), 'never overwrite captured source evidence'
summary=json.loads((ROOT/'summary.json').read_text())
audit=json.loads(Path('experiments/qlib/low-risk-feedback-cost-independent-audit.json').read_text())
assert audit['replay_summary_sha256']==sha(ROOT/'summary.json')
assert summary['plan_sha256']=='832e9fa9066303c144cd71e955311f83cfff5c5a66757b1f09de47c7cfc7dad7'
assert sha(OLD/'manifest.json')=='13ce6f1b1a68f3207e25d3e66c2bff0b59407ccca78f118399884850129469f8'
old_manifest=json.loads((OLD/'manifest.json').read_text())
assert sha(OLD/'plan.json')==old_manifest['plan_sha256']
existing={tuple(key) for key in json.loads((OLD/'plan.json').read_text())['requests']}
requested=set()
for bps,cases in summary['results_by_extra_bps_and_initial_CNY'].items():
    for capital,case in cases.items():
        if 'artifact_sha256' not in case:
            assert case['status']=='INVALID_SINGLE_ORDER_LIMIT'
            continue
        path=ROOT/bps/capital/'orders.json'
        assert sha(path)==case['artifact_sha256']['orders.json']
        for order in json.loads(path.read_text()):
            if order['eligible_at']:
                # Eligible times are UTC 01:30; recorded date is Shanghai session.
                assert order['eligible_at'].endswith('T01:30:00+00:00')
                requested.add((order['security_id'],order['eligible_at'][:10]))
missing=sorted(requested-existing)
(OUTPUT/'sessions').mkdir(parents=True)
plan={'status':'FEEDBACK_ORDER_ADDITIONAL_TAPE_CAPTURE','script_sha256':sha(Path(__file__)),
      'feedback_summary_sha256':sha(ROOT/'summary.json'),'parent_tape_manifest_sha256':sha(OLD/'manifest.json'),
      'all_valid_profile_code_sessions':len(requested),'new_requests':missing,'source':'BaoStock raw five-minute API',
      'used_for_decision':False,'historical_arrival_verified':False,'auction_volume_verified':False}
(OUTPUT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
import baostock as bs
socket.setdefaulttimeout(20)
assert bs.login().error_code=='0'
hashes={}
try:
    for code,day in missing:
        fields,raw=query_rows(bs.query_history_k_data_plus(source_code(code),','.join(FIELDS),
                             start_date=day,end_date=day,frequency='5',adjustflag='3'))
        rows,complete=validate_minutes(code,day,fields,raw)
        name=code+'-'+day+'.json';path=OUTPUT/'sessions'/name
        packet={'instrument':code,'session':day,'fields':list(FIELDS),'rows':rows,'complete_48_slots':complete,
                'observed_at':datetime.now(timezone.utc).isoformat(),'used_for_decision':False,
                'historical_arrival_verified':False}
        path.write_text(json.dumps(packet,indent=2)+'\n');hashes[name]=sha(path)
        print(code,day,'rows',len(rows),'complete',complete,flush=True)
finally:
    bs.logout()
manifest={**plan,'status':'ADDITIONAL_EVALUATION_TAPE_CAPTURED','plan_sha256':sha(OUTPUT/'plan.json'),
          'per_session_sha256':hashes,'new_code_sessions':len(hashes)}
(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
