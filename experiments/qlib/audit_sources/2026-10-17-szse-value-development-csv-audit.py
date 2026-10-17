"""Stdlib-only CSV ledger reconstruction; not a raw-share execution audit."""
import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from decimal import Decimal
import struct
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--run-dir', required=True)
parser.add_argument('--provider-uri', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--source-capture-dir', required=True)
args = parser.parse_args()
root = Path(args.run_dir)
summary = json.loads((root/'summary.json').read_text())
plan_path = Path('experiments/qlib/szse-value-pre2026-plan.json')
plan = json.loads(plan_path.read_text())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert summary['plan_sha256'] == sha(plan_path)
assert summary['candidate_budget'] == plan['candidate_budget'] == 1
assert summary['2026_market_values_queried'] is False
assert all(sha(n) == h for n, h in plan['method_code_sha256'].items())
assert sha(root/'targets.json') == plan['initial_targets_sha256'] == summary['targets_sha256']
assert sha(root/'formation_receipts.json') == plan['initial_receipts_sha256'] == summary['formation_receipts_sha256']
calendar_file = Path(args.provider_uri)/'calendars/day.txt'
assert sha(calendar_file) == plan['input_sha256']['calendars/day.txt']
calendar = calendar_file.read_text().splitlines()
provider = Path(args.provider_uri)
for relative, expected in plan['input_sha256'].items():
    if relative != 'price_files': assert sha(provider/relative) == expected
codes = set()
for line in (provider/'instruments/csi500.txt').read_text().splitlines():
    code, first, last = line.split()
    if (code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003'))
            and first <= '2025-12-31' and last >= '2023-12-29'): codes.add(code)
files = [Path('instruments/all.txt')]
for code in sorted(codes):
    files.extend(Path('features')/code.lower()/(f+'.day.bin')
                 for f in ('open', 'high', 'low', 'close', 'volume', 'factor', 'amount', 'adjclose'))
files.append(Path('features/sh000905/adjclose.day.bin'))
prices_digest = hashlib.sha256()
for relative in files:
    prices_digest.update(relative.as_posix().encode()+b'\0')
    prices_digest.update((provider/relative).read_bytes()); prices_digest.update(b'\0')
assert prices_digest.hexdigest() == plan['input_sha256']['price_files']
factor_cache = {}


def execution_factor(code, day):
    if code not in factor_cache:
        raw = (provider/'features'/code.lower()/'factor.day.bin').read_bytes()
        values = struct.unpack('<'+'f'*(len(raw)//4), raw)
        factor_cache[code] = (int(values[0]), values[1:])
    start, values = factor_cache[code]
    value = values[calendar.index(day)-start]
    assert math.isfinite(value) and value > 0
    return value


expected_days = [d for d in calendar if '2024-01-02' <= d <= '2025-12-31']
targets = json.loads((root/'targets.json').read_text())
# Independent point-in-time recipe checks use authenticated original-source views.
source = Path(args.source_capture_dir)
assert sha(source/'manifest.json') == plan['source_capture_manifest_sha256'] == summary['source_capture_manifest_sha256']
source_manifest = json.loads((source/'manifest.json').read_text())
assert source_manifest['status'] == 'PRE2026_SZSE_MONTHLY_ORIGINAL_TABLES_CAPTURED'
assert sha(source/'request.json') == source_manifest['request_sha256'] == plan['source_capture_request_sha256']
for name, h in source_manifest['journal_artifact_sha256'].items(): assert sha(source/name) == h
published = {}
for month, item in source_manifest['months'].items():
    for kind in ('article', 'table', 'normalized'): assert sha(source/item[kind+'_file']) == item[kind+'_sha256']
    published[month] = json.loads((source/item['normalized_file']).read_text())
    for kind in ('article','table'):
        stamp = re.search(r'(?:/t|/W0)(\d{8})',item[kind+'_url'])[1]
        day = stamp[:4]+'-'+stamp[4:6]+'-'+stamp[6:8]
        assert published[month][kind+'_build_day'] == day
membership_rows = [line.split() for line in (provider/'instruments/csi500.txt').read_text().splitlines()]
past_cache = {}
def past_feature(code, field, day):
    assert day <= '2025-12-31'
    key = (code,field)
    if key not in past_cache:
        blob=(provider/'features'/code.lower()/(field+'.day.bin')).read_bytes()
        values=struct.unpack('<'+'f'*(len(blob)//4),blob)
        past_cache[key]=(int(values[0]),values[1:])
    first,values=past_cache[key];offset=calendar.index(day)-first
    if not 0 <= offset < len(values):return None
    value=values[offset];return value if math.isfinite(value) else None
formations = json.loads((root/'formation_receipts.json').read_text())
assert len(formations) == len(targets['szse_monthly_low_pe']) == len(targets['eligible_equal_weight']) == 24
by_formation={row['execution_session']:row for row in formations}
for execution, target in targets['szse_monthly_low_pe'].items():
    asof=calendar[calendar.index(execution)-1]
    assert target['as_of'] == asof and execution[:7] != asof[:7]
    y,m=map(int,execution[:7].split('-'));sy,sm=divmod(y*12+m-1-2,12);month=f'{sy:04d}-{sm+1:02d}'
    source_month=published[month]
    ny,nm=divmod(sy*12+sm+1,12)
    assert asof[:7] == f'{ny:04d}-{nm+1:02d}'
    assert max(source_month['article_build_day'],source_month['table_build_day']) <= asof
    names=sorted({c for c,a,b in membership_rows if c.startswith(('SZ000','SZ001','SZ002','SZ003')) and a<=asof<=b})
    assert len(names)>=100
    available={c:source_month['stocks'][c] for c in names if c in source_month['stocks']}
    assert len(available)>=.95*len(names)
    ranked=[];scores={}
    for code,stock in available.items():
        label=unicodedata.normalize('NFKC',re.sub(r'\s','',stock['name'])).upper()
        if 'ST' in label or '退' in label or stock['pe'] is None:continue
        pe=Decimal(stock['pe']);assert pe.is_finite()
        if pe<=0:continue
        volume=past_feature(code,'volume',asof);factor=past_feature(code,'factor',asof)
        if volume is None or factor is None or min(volume,factor)<=0:continue
        ranked.append((pe,code));scores[code]=1/float(pe)
    assert len(ranked)>=50 and len(ranked)>=.5*len(names)
    selected=[c for pe,c in sorted(ranked)[:len(ranked)//10]]
    assert set(target['weights'])==set(selected)
    assert all(math.isclose(w,.95/len(selected),rel_tol=1e-12) for w in target['weights'].values())
    control=targets['eligible_equal_weight'][execution]
    assert control['as_of']==asof and set(control['weights'])==set(scores)
    assert all(math.isclose(w,.95/len(scores),rel_tol=1e-12) for w in control['weights'].values())
    receipt=by_formation[execution]
    assert receipt['formation_asof']==asof and receipt['source_month']==month
    assert receipt['source_table_sha256']==source_manifest['months'][month]['table_sha256']
    assert receipt['historical_members']==len(names) and receipt['published_member_rows']==len(available)
    assert receipt['eligible']==len(scores) and receipt['selected']==selected and receipt['scores']==scores
assert set(summary['results_by_extra_bps_and_family']) == {
    f'{e}/{n}' for e in (20, 40) for n in ('szse_monthly_low_pe', 'eligible_equal_weight')}


def close(a, b, *, money=False):
    assert math.isfinite(a) and math.isfinite(b)
    assert math.isclose(a, b, rel_tol=1e-9, abs_tol=.01 if money else 1e-6), (a, b)


def read(folder, name):
    with (folder/name).open() as stream:
        return list(csv.DictReader(stream))


audited = {}
for label, stated in summary['results_by_extra_bps_and_family'].items():
    extra, name = label.split('/'); folder = root/label
    for filename, h in stated['artifact_sha256'].items():
        assert sha(folder/filename) == h
    days = read(folder, 'days.csv'); orders = read(folder, 'orders.csv'); holdings = read(folder, 'holdings.csv')
    assert [r['session'] for r in days] == expected_days
    by_order, by_held = defaultdict(list), defaultdict(list)
    for row in orders: by_order[row['session']].append(row)
    for row in holdings: by_held[row['session']].append(row)
    cash = initial = float(plan['capital_CNY']); inventory = defaultdict(float)
    nav = {}; exposures = []; fees = turnover = 0.; peak = initial; dd = 0.
    rounding_excesses = []
    for day in days:
        d = day['session']; cost = gross = 0.
        assert day['signal_date'] == calendar[calendar.index(d)-1]
        assert (day['signal_present'] == 'True') == (d in targets[name])
        for order in by_order[d]:
            assert d in targets[name] and order['signal_date'] == targets[name][d]['as_of'] < d
            raw_q = float(order['filled_normalized_units']); raw_request = float(order['requested_normalized_units'])
            q, requested = abs(raw_q), abs(raw_request)
            amount = float(order['signed_trade_value']); fee = float(order['cost'])
            assert order['side'] in ('BUY', 'SELL')
            # Qlib indicators use signed SELL quantities. Its exchange rounds
            # with (amount*factor+0.1)//100, which can slightly exceed a request.
            assert (raw_q >= 0 and raw_request >= 0) if order['side'] == 'BUY' else (raw_q <= 0 and raw_request <= 0)
            if q > requested + 1e-5:
                excess = (q-requested)*execution_factor(order['instrument'], d)
                assert excess <= .100001, ('beyond Qlib 0.1-share rounding guard', order)
                rounding_excesses.append(excess)
            if q:
                price = float(order['normalized_price']); sign = 1 if order['side'] == 'BUY' else -1
                close(amount, sign*q*price, money=True)
                rate = (.0005 if sign == 1 else .0015) + int(extra)/10000
                close(fee, max(5., abs(amount)*rate), money=True)
                inventory[order['instrument']] += sign*q
                assert inventory[order['instrument']] >= -1e-6
            else:
                close(amount, 0., money=True); close(fee, 0., money=True)
            cash -= amount + fee; cost += fee; gross += abs(amount)
        assert cash >= -.01
        close(cash, float(day['cash']), money=True)
        assert len(by_order[d]) == int(day['orders'])
        close(cost, float(day['cost']), money=True); close(gross, float(day['turnover']), money=True)
        active = {h['instrument']: h for h in by_held[d]}
        assert len(active) == len(by_held[d])
        for code in set(inventory) | set(active):
            close(inventory.get(code, 0.), float(active[code]['normalized_units']) if code in active else 0.)
        market = 0.
        for held in active.values():
            value = float(held['value'])
            close(value, float(held['normalized_units'])*float(held['normalized_price']), money=True)
            market += value
        nav[d] = cash + market
        close(market, float(day['stock_value']), money=True)
        close(nav[d], float(day['account_value']), money=True)
        for held in active.values(): close(float(held['weight']), float(held['value'])/nav[d])
        exposures.append(market/nav[d]); fees += cost; turnover += gross
        peak = max(peak, nav[d]); dd = min(dd, nav[d]/peak - 1)
    returns = {'2024_return_pct': (nav['2024-12-31']/initial-1)*100,
               '2025_return_pct': (nav['2025-12-31']/nav['2024-12-31']-1)*100,
               'net_compound_return_pct': (nav['2025-12-31']/initial-1)*100,
               'average_exposure_pct': sum(exposures)/len(exposures)*100,
               'max_drawdown_pct': dd*100, 'cost_pct_initial': fees/initial*100,
               'turnover_x_initial': turnover/initial}
    for key, value in returns.items(): close(value, stated[key])
    assert len(days) == stated['sessions'] and len(orders) == stated['orders']
    close(sum(r['fill_status'] == 'UNFILLED' for r in orders), stated['unfilled_orders'])
    marks = json.loads((folder/'suspension_mark_audit.json').read_text())
    assert sum(not r['verified'] for r in marks) == stated['unverified_held_marks']
    audited[label] = {'status': 'NORMALIZED_CSV_LEDGER_RECONSTRUCTED', **returns,
        'sessions': len(days), 'orders': len(orders), 'unverified_held_marks_preserved': stated['unverified_held_marks'],
        'cash_inventory_fees_market_value_reconciled': True,
        'qlib_guard_rounding_request_excess_count': len(rounding_excesses),
        'max_qlib_raw_equivalent_request_excess': max(rounding_excesses, default=0.),
        'strict_fill_not_above_requested_quantity_verified': not rounding_excesses}
reference = audited['40/szse_monthly_low_pe']
eligible = (reference['2024_return_pct'] > 0 and reference['2025_return_pct'] > 0
            and reference['average_exposure_pct'] >= 90 and reference['unverified_held_marks_preserved'] == 0)
assert summary['selected_development_lead'] == ('szse_monthly_low_pe' if eligible else None)
output = Path(args.output); assert not output.exists()
output.write_text(json.dumps({'status': 'INDEPENDENT_NORMALIZED_CSV_DEVELOPMENT_AUDIT_COMPLETE',
    'audit_script_sha256': sha(Path(__file__)), 'summary_sha256': sha(root/'summary.json'),
    'results_by_profile': audited, 'development_gate_passes_independently': eligible,
    'imports_project_account_code': False, 'raw_share_execution_verified': False,
    'scope': 'CSV cash, normalized inventory, fill notional, Qlib fees, held market value, NAV, interval metrics and declared gate; quote truth and raw-share executions not certified',
    '2026_outcomes_read': False, 'objective_achieved': False,
    'published_monthly_formations_independently_reconstructed':24,
    'source_capture_manifest_sha256':plan['source_capture_manifest_sha256'],
    'historical_publication_or_arrival_verified':False}, indent=2)+'\n')
print('independent normalized CSV audit', len(audited), 'profiles; passes', eligible)
