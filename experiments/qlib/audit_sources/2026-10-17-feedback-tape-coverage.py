"""Check every generated feedback-profile order against immutable tape sources."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from scripts.audit_low_risk_execution_tape import audit_case, order_session
from scripts.capture_low_risk_execution_tape import FIELDS, validate_minutes

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
ROOT=BASE/'low-risk-feedback-cost-20261017'
OLD=BASE/'low-risk-execution-tape-20261017'
ADDED=BASE/'low-risk-feedback-tape-additions-20261017'
OUTPUT=Path('experiments/qlib/low-risk-feedback-cost-tape-coverage.json')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert not OUTPUT.exists()
summary=json.loads((ROOT/'summary.json').read_text())
independent=json.loads(Path('experiments/qlib/low-risk-feedback-cost-independent-audit.json').read_text())
assert independent['replay_summary_sha256']==sha(ROOT/'summary.json')
raw=BASE/'low-risk-raw-account-data-20261017'
assert sha(raw/'manifest.json')==summary['data_manifest_sha256']
raw_manifest=json.loads((raw/'manifest.json').read_text());bars={}
for code,expected in raw_manifest['per_code_sha256'].items():
    path=raw/'codes'/(code+'.json');assert sha(path)==expected
    bars[code]={row['date']:row for row in json.loads(path.read_text())['bars']}
assert sha(OLD/'manifest.json')=='13ce6f1b1a68f3207e25d3e66c2bff0b59407ccca78f118399884850129469f8'
added=json.loads((ADDED/'manifest.json').read_text())
assert added['feedback_summary_sha256']==sha(ROOT/'summary.json')
assert sha(ADDED/'plan.json')==added['plan_sha256']
tapes={}
for source in (OLD,ADDED):
    manifest=json.loads((source/'manifest.json').read_text())
    for name,expected in manifest['per_session_sha256'].items():
        path=source/'sessions'/name;assert sha(path)==expected
        packet=json.loads(path.read_text());key=(packet['instrument'],packet['session'])
        assert key not in tapes and name==key[0]+'-'+key[1]+'.json'
        rows,complete=validate_minutes(key[0],key[1],packet['fields'],[[row[f] for f in FIELDS] for row in packet['rows']])
        assert complete and packet['complete_48_slots']
        tapes[key]=rows
all_requests=set();results={};details={}
for bps,cases in summary['results_by_extra_bps_and_initial_CNY'].items():
    for capital,case in cases.items():
        label=bps+'/'+capital
        if 'artifact_sha256' not in case:
            assert case['status']=='INVALID_SINGLE_ORDER_LIMIT'
            results[label]={'status':'INVALID_SINGLE_ORDER_LIMIT','source_claim_made':False}
            continue
        folder=ROOT/bps/capital
        for name in ('orders.json','fills.json'):assert sha(folder/name)==case['artifact_sha256'][name]
        orders=json.loads((folder/'orders.json').read_text());fills=json.loads((folder/'fills.json').read_text())
        requests={key for order in orders if (key:=order_session(order)) is not None}
        assert requests<=set(tapes)
        all_requests.update(requests)
        checked=audit_case(orders,fills,bars,tapes);details[label]=checked
        assert not checked['incomplete_order_session_tape'] and not checked['missing_or_incomplete_traded_tape']
        results[label]={key:checked[key] for key in ('status','orders_over_one_million_shares',
            'filled_orders_over_one_million_shares','fills_checked','first_label_capacity','opening_fill_verified')}
        results[label].update({'requested_code_sessions':len(requests),'all_order_tape_present':True,
            'regular_board_price_violations':len(checked['regular_board_limit_price_violations']),
            'unknown_regular_board_limit_checks':len(checked['unknown_regular_board_limit_checks']),
            'daily_minute_mismatch_fills':len(checked['daily_minute_crosscheck_mismatches'])})
quality=defaultdict(lambda:defaultdict(int))
for code,day in sorted(all_requests):
    daily=bars[code][day];rows=tapes[(code,day)];year=day[:4]
    quality[year]['requested_code_sessions']+=1
    if not daily['volume']:
        quality[year]['daily_volume_unknown']+=1;continue
    total=sum((Decimal(row['volume']) for row in rows),Decimal(0))
    quality[year]['exact_volume_matches']+=total==Decimal(daily['volume'])
    quality[year]['volume_mismatches']+=total!=Decimal(daily['volume'])
    quality[year]['first_open_matches']+=Decimal(rows[0]['open'])==Decimal(daily['open'])
    quality[year]['last_close_matches']+=Decimal(rows[-1]['close'])==Decimal(daily['close'])
detail_file=BASE/'low-risk-feedback-cost-tape-audit-20261017.json'
assert not detail_file.exists();detail_file.write_text(json.dumps(details,indent=2)+'\n')
result={'status':'ALL_NEW_ORDER_SESSIONS_COVERED_OLDER_SOURCE_DISCREPANCIES_UNRESOLVED',
        'summary_sha256':sha(ROOT/'summary.json'),'script_sha256':sha(Path(__file__)),
        'parent_tape_manifest_sha256':sha(OLD/'manifest.json'),'additional_tape_manifest_sha256':sha(ADDED/'manifest.json'),
        'additional_code_sessions':len(added['per_session_sha256']),'all_valid_profile_code_sessions':len(all_requests),
        'uncovered_code_sessions':0,'by_year':dict(quality),'results_by_profile':results,
        'full_local_detail_sha256':sha(detail_file),'auction_volume_verified':False,'objective_achieved':False}
OUTPUT.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='results_by_profile'},indent=2))
