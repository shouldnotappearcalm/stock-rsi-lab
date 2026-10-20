"""Independent continuous interim2026 stdlib audit; no production imports.

Reads frozen pre-2026 sources and completed outputs. Reconstructs signals,
orders, staged funding, fills and accounting independently. No network.
"""
import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal as D, ROUND_HALF_UP
from fractions import Fraction as F
from pathlib import Path
from datetime import date
from html.parser import HTMLParser
import re

CODES = ('SH510300', 'SH510500', 'SZ159915')
REQUEST_SHA = 'e264c5a5e7a87a56f29a5dea8e87118d7f1d94b87d0621769de5377f1dfa5e8f'
END = '2026-10-20'
PARENT_AUDITOR_SHA = '9407af7715e58165797f91100c4fda068bcfbb823aca5f91cc7ca52c8ec0e0aa'
CANDIDATE_REASON = 'fixed three domestic ETF prior2-12 excluding recent month, prior-close 95% target'
LEGACY_REASON = 'fixed three domestic ETF relative12m, prior-close 95% target'
CENT = D('.01')
TICK = D('.001')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def bound(root, name, expected):
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe bound path')
    path = root / relative
    require(sha(path) == expected, 'hash mismatch: ' + str(path))
    return path


def stamp(day, close=False):
    return day + ('T07:05:00+00:00' if close else 'T01:30:00+00:00')


def render(value):
    return str(D(value.numerator) / D(value.denominator))


def independent_formations(days, prices, events, *, prior2_to12=True, expected_count=34):
    """Exact rational returns, independently built from raw closes and ex cash."""
    cash = {(e['ex_date'], e['instrument']): D(e['cash_per_unit']) for e in events}
    require(len(cash) == len(events), 'duplicate ex-date/security')
    indices = {code: F(1) for code in CODES}
    endpoints = []
    formations = {}
    for index, day in enumerate(days):
        for code in CODES:
            close = D(prices[code][day]['close'])
            if index:
                indices[code] *= (F(close) + F(cash.get((day, code), 0))) / F(D(prices[code][days[index-1]]['close']))
        following = days[index+1] if index+1 < len(days) else None
        if following is None or following[:7] != day[:7]:
            endpoints.append((day, dict(indices)))
            if len(endpoints) >= 13 and following and '2024' <= following[:4] <= days[-1][:4]:
                window = endpoints[-13:]
                months = [int(d[:4])*12 + int(d[5:7]) for d, _ in window]
                require(all(b-a == 1 for a, b in zip(months, months[1:])), 'nonconsecutive month ends')
                endpoint = window[-2][1] if prior2_to12 else window[-1][1]
                scores = {c: endpoint[c]/window[0][1][c]-1 for c in CODES}
                formations[day] = {
                    'as_of': day, 'leader': min(CODES, key=lambda c: (-scores[c], c)),
                    'scores': {c: render(scores[c]) for c in CODES},
                    'scores_exact_ratio': {c: [str(scores[c].numerator), str(scores[c].denominator)] for c in CODES},
                    'window_monthends': [d for d, _ in window],
                    'total_return_index_monthends': [{c: render(v[c]) for c in CODES} for _, v in window],
                }
                if prior2_to12:
                    formations[day].update(signal='PRIOR2_TO12_EXCLUDING_LATEST_COMPLETE_MONTH',
                        signal_start_monthend=window[0][0], signal_end_monthend=window[-2][0],
                        excluded_monthend=window[-1][0], return_month_count=11)
    require(len(formations) == expected_count, 'independent formation count')
    return formations


def audit_case(extra, ledger, summary, days, prices, events, formations, *, decision_reason=CANDIDATE_REASON):
    interim = days[-1][:4] == '2026'
    day_rows = ledger['days']
    require([r['day'] for r in day_rows] == [d for d in days if '2024' <= d[:4] <= days[-1][:4]], 'outcome dates')
    rows = {r['day']: r for r in day_rows}
    intents = {r['formation']['as_of']: r for r in ledger['intents']}
    require(len(intents) == len(ledger['intents']) == len(formations) and set(intents) == set(formations), 'monthly intent coverage')
    orders = {o['order_id']: o for o in ledger['orders']}
    require(len(orders) == len(ledger['orders']), 'duplicate order ids')
    reported_fills = ledger['fills']
    funding = {r['confirmation_session']: r for r in ledger['funding_intents']}
    require(len(funding) == len(ledger['funding_intents']), 'duplicate funding confirmation')
    cash, previous_equity = D('1000000'), D('1000000')
    lots, pending, entitlements, claims = defaultdict(list), defaultdict(list), {}, []
    submitted, statuses, expected_fills, expected_corporate = set(), {}, [], []
    verified_funding, deferred, reconstructed = set(), None, []

    def positions():
        return {c: sum(q for q, _ in values) for c, values in lots.items() if values}

    def fee(gross):
        return max(D(5), gross*D('.0005')).quantize(CENT, rounding=ROUND_HALF_UP) + (gross*D(extra)/10000).quantize(CENT, rounding=ROUND_HALF_UP)

    def submit(decisions, snapshot, formed, eligible):
        submitted_now = []
        for decision in decisions:
            decision_id = digest({'decision': decision, 'snapshot': snapshot})
            order_id = digest({'decision_id': decision_id, 'at': stamp(formed, True), 'expires_at': stamp(eligible)})
            require(order_id in orders and order_id not in submitted, 'unmapped/duplicate independent submission')
            o = orders[order_id]
            expected = {'order_id': order_id, 'decision_id': decision_id, 'security_id': decision['security_id'],
                        'action': decision['action'], 'quantity': decision['quantity'], 'submitted_at': stamp(formed, True),
                        'eligible_at': stamp(eligible), 'expires_at': stamp(eligible)}
            require(all(o[k] == v for k, v in expected.items()), 'order differs from fixed intent')
            require(type(o['quantity']) is int and 0 < o['quantity'] <= 1000000 and o['quantity'] % 100 == 0, 'integer unit order')
            pending[eligible].append(o)
            submitted.add(order_id)
            submitted_now.append(order_id)
        return submitted_now

    for index, day in enumerate(days):
        following = days[index+1] if index+1 < len(days) else None
        at_ex = [e for e in events if e['ex_date'] == day]
        for e in at_ex:
            require(e['announced'] < e['recorded'] < day <= e['pay_date'], 'event chronology')
            require(e['event_id'] in entitlements, 'record entitlement absent')
        paid = D(0)
        for claim in claims:
            if not claim['paid'] and claim['available'] == day:
                cash += claim['amount']; paid += claim['amount']; claim['paid'] = True
                expected_corporate.append({'day': day, 'kind': 'NET_DIVIDEND_CASH_AVAILABLE', 'event_id': claim['event_id'], 'cash_delta': str(claim['amount'])})
        for e in at_ex:
            quantity = entitlements[e['event_id']]
            gross = (D(quantity)*D(e['cash_per_unit'])).quantize(CENT, rounding=ROUND_HALF_UP)
            if gross:
                claims.append({'event_id': e['event_id'], 'amount': gross, 'available': next((d for d in days if d > e['pay_date']), None), 'paid': False})
            expected_corporate.append({'day': day, 'kind': 'EX_DATE_ENTITLEMENT', 'event_id': e['event_id'],
                'instrument': e['instrument'], 'registered_quantity': quantity, 'cash_gross': str(gross), 'stress_tax_reserve': '0.00', 'capital_shares': 0})
        todays = pending.pop(day, [])
        require(len({o['action'] for o in todays}) <= 1, 'same-open sell and buy forbidden')
        day_fills, day_fee = [], D(0)
        for o in sorted(todays, key=lambda x: (x['action'] != 'SELL', x['security_id'])):
            code, side = o['security_id'], o['action']
            p = D(prices[code][day]['open'])
            ex_cash = sum((D(e['cash_per_unit']) for e in at_ex if e['instrument'] == code), D(0))
            reference = D(prices[code][days[index-1]]['close']) - ex_cash
            limit = D('.2') if code == 'SZ159915' else D('.1')
            upper = (reference*(1+limit)).quantize(TICK, rounding=ROUND_HALF_UP)
            lower = (reference*(1-limit)).quantize(TICK, rounding=ROUND_HALF_UP)
            require(p > 0 and p == p.quantize(TICK) and lower <= p <= upper and D(prices[code][day]['volume_provider_raw']) > 0, 'opening source/reference band')
            wanted = o['quantity']
            quantity = wanted
            if (side == 'BUY' and p >= upper) or (side == 'SELL' and p <= lower):
                status = 'UNFILLED_MARKET_CONSTRAINT'; quantity = 0
            else:
                if side == 'BUY':
                    # Binary search affordable whole lots, independently of production's decrement loop.
                    low, high = 0, wanted//100
                    while low < high:
                        middle = (low+high+1)//2; gross = p*(middle*100)
                        if gross+fee(gross) <= cash: low = middle
                        else: high = middle-1
                    quantity = low*100
                else:
                    quantity = min(wanted, sum(q for q, bought in lots[code] if bought < day))
                if not quantity: status = 'UNFILLED_CASH_OR_T1'
                elif side == 'SELL' and cash+p*quantity < fee(p*quantity):
                    status = 'UNFILLED_FEES_CASH'; quantity = 0
                else: status = 'FILLED' if quantity == wanted else 'PARTIAL_DAY_EXPIRED'
            statuses[o['order_id']] = status
            require(o['status'] == status, 'order fill-status mismatch')
            if quantity:
                gross, charge = p*quantity, fee(p*quantity)
                day_fee += charge
                if side == 'BUY': cash -= gross+charge; lots[code].append((quantity, day))
                else:
                    cash += gross-charge
                    remaining, replacement = quantity, []
                    for q, bought in lots[code]:
                        removed = min(q, remaining) if bought < day else 0
                        remaining -= removed
                        if q-removed: replacement.append((q-removed, bought))
                    require(remaining == 0, 'T+1 sell inventory')
                    lots[code] = replacement
                f = {'order_id': o['order_id'], 'execution_at': stamp(day), 'security_id': code, 'action': side,
                     'quantity': quantity, 'price': str(p), 'cost': str(charge), 'cash_after': str(cash)}
                require(len(expected_fills) < len(reported_fills) and f == reported_fills[len(expected_fills)], 'fill/fee/cash/timestamp mismatch')
                expected_fills.append(f); day_fills.append(f)
            require(cash >= 0 and cash == cash.quantize(CENT), 'cash nonnegative cents')
        owned = positions()
        for e in events:
            if e['recorded'] == day:
                q = owned.get(e['instrument'], 0); entitlements[e['event_id']] = q
                expected_corporate.append({'day': day, 'kind': 'RECORD_DATE_OWNERSHIP', 'event_id': e['event_id'], 'instrument': e['instrument'], 'quantity': q})
        marks = {c: D(prices[c][day]['close']) for c in CODES}
        receivable = sum((c['amount'] for c in claims if not c['paid']), D(0))
        market = sum((q*marks[c] for c, q in owned.items()), D(0))
        equity = cash+market+receivable
        exposure = market/equity
        if '2024' <= day[:4] <= days[-1][:4]:
            actual = rows[day]
            numeric = {'cash': cash, 'market_value': market, 'cash_receivable': receivable, 'equity': equity,
                'fees': day_fee, 'dividend_cash_available': paid, 'net_return': equity/previous_equity-1, 'exposure': exposure}
            require(all(D(actual[k]) == value for k, value in numeric.items()), 'daily accounting: '+day)
            require(actual['positions'] == owned and {k: D(v) for k, v in actual['marks'].items()} == marks, 'daily shares/marks')
            reconstructed.append({'day': day, **numeric})
        if deferred and deferred['sell_day'] == day:
            require(day in funding, 'missing deferred funding receipt')
            receipt = funding[day]; verified_funding.add(day)
            sell_states = {oid: statuses[oid] for oid in deferred['sell_ids']}
            require(receipt['formation_as_of'] == stamp(deferred['day'], True)
                    and receipt['original_formation_snapshot_sha256'] == deferred['snapshot']
                    and receipt['original_formation_quantity'] == deferred['buys'][0]['quantity']
                    and receipt['sell_order_statuses'] == sell_states
                    and receipt['original_score_record'] == deferred['record'], 'funding original provenance')
            if not all(v == 'FILLED' for v in sell_states.values()):
                require(receipt['status'] == 'CANCELLED_SELL_NOT_FULLY_FILLED' and receipt['decisions'] == [], 'failed sell must cancel')
            elif following is None:
                require(receipt['status'] == 'CANCELLED_CALENDAR_END' and receipt['decisions'] == [], 'calendar end must cancel')
            else:
                confirmation = {'record_id': digest({'day': day, 'sell_states': sell_states, 'fills': day_fills}),
                    'kind': 'observed_sale_confirmation', 'available_at': stamp(day, True), 'payload': {'sell_states': sell_states, 'fills': day_fills}}
                snapshot = digest({'as_of': stamp(day, True), 'records': [deferred['record'], confirmation],
                    'account': {'equity': str(equity), 'cash': str(cash), 'positions': owned}})
                decisions = [{**d, 'evidence_ids': [deferred['record']['record_id'], confirmation['record_id']],
                    'reason': 'release original fixed monthly buy only after observed full sale; next-session execution'} for d in deferred['buys']]
                require(receipt['status'] == 'CONFIRMED_SALE_THEN_NEXT_SESSION_BUY' and receipt['submitted_at'] == stamp(day, True)
                    and receipt['execution_session'] == following and receipt['snapshot_sha256'] == snapshot
                    and receipt['decisions'] == decisions, 'deferred buy must preserve quantity and wait next session')
                submit(decisions, snapshot, day, following)
            deferred = None
        if day in formations:
            expected = formations[day]; intent = intents[day]
            require(intent['formation'] == expected and intent['execution_session'] == following and intent['as_of'] == stamp(day, True), 'ranking/monthend/asof mismatch')
            require(D(intent['equity_at_decision']) == equity and intent['owned_integer_units'] == owned
                and {k: D(v) for k, v in intent['raw_close'].items()} == marks, 'formation account mismatch')
            record = {'record_id': digest(expected), 'kind': 'visible_monthly_ETF_total_returns', 'available_at': stamp(day, True), 'payload': expected}
            snapshot = digest({'as_of': stamp(day, True), 'records': [record], 'account': {'equity': str(equity), 'cash': str(cash),
                'cash_receivable': str(receivable), 'positions': owned, 'raw_close': {c: str(v) for c, v in marks.items()}}})
            require(intent['snapshot_sha256'] == snapshot, 'formation snapshot hash')
            desired = int(F(equity)*F(95, 100)/F(marks[expected['leader']])/100)*100
            actions = []
            for code in sorted(set(owned) | {expected['leader']}):
                held = owned.get(code, 0); target = desired if code == expected['leader'] else 0
                if held > target: actions.append(('SELL', code, held-target))
                elif target > held: actions.append(('BUY', code, ((target-held)//100)*100))
            actions.sort(key=lambda x: (x[0] != 'SELL', x[1]))
            decisions = [{'action': side, 'security_id': code, 'quantity': q, 'evidence_ids': [record['record_id']],
                'reason': decision_reason} for side, code, q in actions if q]
            require(intent['decisions'] == decisions, '95percent prior-close integer sizing')
            sells = [d for d in decisions if d['action'] == 'SELL']; buys = [d for d in decisions if d['action'] == 'BUY']
            ids = submit(sells if sells and buys else decisions, snapshot, day, following)
            if sells and buys:
                require(deferred is None and len(buys) == 1, 'overlapping deferred funding')
                deferred = {'day': day, 'sell_day': following, 'sell_ids': ids, 'buys': buys, 'snapshot': snapshot, 'record': record}
        previous_equity = equity
    require(not pending and deferred is None and submitted == set(orders), 'unconsumed orders')
    require(verified_funding == set(funding) and len(expected_fills) == len(reported_fills), 'extra funding or fills')
    require(expected_corporate == ledger['corporate_ledger'], 'corporate entitlement/payment ledger')
    for flag in ('historical_arrival_certified', 'opening_fill_or_queue_certified', 'official_historical_limit_stream_certified',
                 'primary_action_completeness_certified', 'candidate_promoted', 'objective_achieved'):
        require(ledger[flag] is False, 'unwarranted ledger admission')
    prior, annual = D('1000000'), {}
    for year in (('2024', '2025', '2026') if interim else ('2024', '2025')):
        subset = [r for r in reconstructed if r['day'].startswith(year)]
        peak, drawdown = prior, D(0)
        for row in subset:
            peak = max(peak, row['equity']); drawdown = min(drawdown, row['equity']/peak-1)
        label = '2026_interim' if year == '2026' else year
        annual[label] = {'net_return': subset[-1]['equity']/prior-1, 'ending_equity': subset[-1]['equity'],
            'max_drawdown': drawdown, 'average_exposure': sum((r['exposure'] for r in subset), D(0))/len(subset), 'sessions': len(subset)}
        require(all(D(summary['annual'][label][k]) == v for k, v in annual[label].items()), 'annual aggregation '+year)
        if year == '2026':
            require(D(summary['annual'][label]['starting_equity']) == prior and summary['annual'][label]['end'] == END
                and summary['annual'][label]['full_October'] is False, 'continuous-year starting equity/end/full-month flag')
            annual[label].update(starting_equity=prior, end=END, full_October=False)
        prior = subset[-1]['equity']
    gross_dividends = sum((D(x['cash_gross']) for x in expected_corporate if x['kind'] == 'EX_DATE_ENTITLEMENT'), D(0))
    require(D(summary['fees_CNY']) == sum((D(f['cost']) for f in expected_fills), D(0)) and summary['fills'] == len(expected_fills), 'aggregate fees/fills')
    if not interim:
        require(D(summary['gross_dividends_CNY']) == gross_dividends, 'aggregate dividends')
    if not interim:
        require(D(summary['average_exposure']) == sum((r['exposure'] for r in reconstructed), D(0))/len(reconstructed), 'aggregate exposure')
    if interim:
        screen = annual['2024']['net_return'] > 0 and annual['2025']['net_return'] > 0 and annual['2026_interim']['net_return'] >= D('.10')
        require(summary['conditional_interim_three_period_numeric_screen_passed'] is screen, 'fixed interim numeric screen')
        require(summary['pre2026_full_ledger_prefix_reproduced'] is True and summary['full_October'] is False, 'prefix/partial-month flags')
    else:
        screen = all(x['net_return'] > 0 and x['average_exposure'] >= D('.9') for x in annual.values())
        require(summary['numerical_development_screen_passed'] is screen, 'numeric development screen')
    flags = ('source_or_execution_admission', 'candidate_promoted', 'objective_achieved') + (() if interim else ('new_2026_queries',))
    for flag in flags:
        require(summary[flag] is False, 'unwarranted summary admission')
    return {'sessions_verified': len(reconstructed), 'warmup_and_outcome_sessions_reconstructed': len(days),
        'monthly_rankings_and_integer_targets_verified': len(intents), 'funding_intents_verified': len(funding),
        'orders_verified': len(orders), 'fills_verified': len(expected_fills), 'corporate_rows_verified': len(expected_corporate),
        'all_recorded_entitlements': entitlements, 'gross_dividends_CNY': str(gross_dividends),
        'annual': {y: {k: str(v) if isinstance(v, D) else v for k, v in values.items()} for y, values in annual.items()},
        'numeric_screen_passes': screen}



class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def verify_prefix(ledger, previous):
    for collection, field in [('days', 'day'), ('intents', 'execution_session'), ('fills', 'execution_at'),
                              ('orders', 'eligible_at'), ('funding_intents', 'confirmation_session'), ('corporate_ledger', 'day')]:
        require([r for r in ledger[collection] if r[field] < '2026'] == previous[collection], 'frozen prefix changed: '+collection)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    base, repo, output = Path(args.source_root), Path(args.repo), Path(args.output)
    require(not output.exists(), 'preserve existing audit result')
    request_path = repo/'experiments/qlib/etf-prior2-12-interim2026-replay-request.json'
    require(sha(request_path) == REQUEST_SHA, 'wrong frozen continuation request')
    request = read(request_path)
    require(request['status'] == 'FROZEN_ONE_PRIOR2_12_CONTINUOUS_INTERIM2026_DIAGNOSTIC'
        and request['candidate_id'] == 'three_domestic_broad_ETF_prior2_12' and request['candidate_budget'] == 1
        and request['new_strategy_candidates'] == 0 and request['reset_account_at_2026'] is False
        and request['full_October'] is False and request['end'] == END and request['extra_cost_bps'] == [20, 40]
        and request['reference_extra_cost_bps'] == 40 and request['initial_cash_CNY'] == '1000000', 'fixed scope')
    require(request['user_numeric_conditions'] == {'2024_net_return_gt': '0', '2025_net_return_gt': '0',
        '2026_interim_net_return_gte': '.10'}, 'fixed numeric thresholds')
    checked = 0
    for group, root in [('method_code_sha256', repo), ('local_source_sha256', base), ('public_evidence_sha256', repo)]:
        for name, expected in request[group].items():
            path = bound(root, name, expected); checked += 1
            if path.name in ('manifest.json', 'summary.json'):
                for name2, sha2 in read(path).get('artifact_sha256', {}).items():
                    bound(path.parent, name2, sha2); checked += 1
    olddays = [d.strip() for d in (base/'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines() if '2022-12-01' <= d.strip() <= '2025-12-31']
    newbase = base/request['new_price_directory']; newsummary = read(newbase/'summary.json')
    newdays = read(newbase/'calendar.json')['sessions']
    prefix = [d for d in read(base/'low-risk-raw-account-data-20261017/calendar.json')['sessions'] if d.startswith('2026')]
    require(len(olddays) == 749 and len(prefix) == 188 and prefix[-1] == '2026-10-16'
        and newdays == prefix+['2026-10-19', END], 'actual explicit calendar extension')
    days = olddays+newdays
    require(len(days) == 939 and days == sorted(set(days)) and len(newdays) == 190, 'continuous calendar')
    require(Counter(d[:4] for d in days)['2024'] == 242 and Counter(d[:4] for d in days)['2025'] == 243, 'development counts')
    require(newsummary['all_overlap_raw_OHLC_equal'] is True and newsummary['overlap_sessions_each'] == 243, 'overlap metadata')
    # Independently inspect source date/price rows, never quote/auxiliary nodes or pre-2025 prices.
    originals = base/'etf-tencent-interim2026-originals-20261021'; manifest = read(originals/'manifest.json')
    prices, source_checks = {}, {}
    for code in CODES:
        old = read(base/'etf-relative-eastmoney-development-20261021'/(code+'-raw.json'))
        new = read(newbase/(code+'-raw.json'))
        require(old['instrument'] == new['instrument'] == code and old['mode'] == new['mode'] == 'raw', 'raw identity')
        require([r['date'] for r in old['bars']] == olddays and [r['date'] for r in new['bars']] == newdays, 'raw calendar')
        oldmap = {r['date']: r for r in old['bars']}; newmap = {r['date']: r for r in new['bars']}
        document = manifest['documents'][code]; wire = (originals/document['file']).read_text()
        require(wire.startswith('kline_day2025='), 'JSONP identity')
        response = json.loads(wire.removeprefix('kline_day2025='))
        require(response['code'] == 0 and set(response['data']) == {code.lower()}, 'wire security identity')
        raw = response['data'][code.lower()]['day']; rawdates = [r[0] for r in raw]
        require(rawdates == sorted(set(rawdates)) and all(date.fromisoformat(d).isoformat() == d and d <= END for d in rawdates), 'wire dates')
        admitted = [r for r in raw if r[0] >= '2025-01-01']
        require([r[0] for r in admitted if r[0] < '2026'] == [d for d in olddays if d.startswith('2025')]
            and [r[0] for r in admitted if r[0] >= '2026'] == newdays, 'source overlap/new dates')
        for rawrow in admitted:
            day = rawrow[0]; expected = oldmap[day] if day < '2026' else newmap[day]
            values = [D(v) for v in rawrow[1:5]]
            require(all(D(expected[k]) == v and v.is_finite() and v > 0 and v == v.quantize(TICK)
                        for k, v in zip(('open', 'close', 'high', 'low'), values)), 'source raw OHLC equality/tick')
            op, close, high, low = values
            require(low <= min(op, close) <= max(op, close) <= high and D(rawrow[5]).is_finite() and D(rawrow[5]) > 0, 'source OHLC/volume')
            if day >= '2026':
                require(expected['original_fields'] == rawrow and expected['volume_provider_raw'] == rawrow[5], 'normalized original row provenance')
        prices[code] = {**oldmap, **newmap}
        source_checks[code] = {'overlap_OHLC_sessions': 243, 'new_sessions': 190, 'pre2025_rows_quarantined': len(raw)-len(admitted)}
    # Exact official month/day closure ranges, read through stdlib HTML parsing only.
    closurebase = base/'etf-interim2026-originals-20261021'; closuremanifest = read(closurebase/'manifest.json')
    page = closuremanifest['documents']['sse2026closures']
    require(page['url'] == 'https://www.sse.com.cn/disclosure/dealinstruc/closed/', 'closure origin')
    parser_html = TextOnly(); parser_html.feed((closurebase/page['file']).read_text())
    plain = re.sub(r'\s+', '', ''.join(parser_html.parts))
    require('2026年休市安排' in plain, 'closure year')
    ranges = [('01-01','01-03','元旦'),('02-15','02-23','春节'),('04-04','04-06','清明节'),
              ('05-01','05-05','劳动节'),('06-19','06-21','端午节'),('09-25','09-27','中秋节'),('10-01','10-07','国庆节')]
    for start, end, label in ranges:
        pattern = label+r'[:：]?(\d{1,2})月(\d{1,2})日(?:（[^）]*）)?至(\d{1,2})月(\d{1,2})日(?:（[^）]*）)?休市'
        found = re.findall(pattern, plain)
        require(len(found) == 1, 'unique complete closure clause '+label)
        m1,d1,m2,d2 = map(int, found[0])
        require((f'{m1:02}-{d1:02}', f'{m2:02}-{d2:02}') == (start,end), 'closure endpoint '+label)
        require(not any('2026-'+start <= d <= '2026-'+end for d in newdays), 'observed closure contradiction')
    require(all(date.fromisoformat(d).weekday() < 5 for d in newdays), 'observed weekend')
    events = []
    for filename, directory, count in [('etf-five-cashflows-primary-review.json','etf-five-distribution-notices-20261021',5),
                                        ('etf-three-2026-cashflows-review.json','etf-2026-cash-notices-rules-20261021',3)]:
        review = read(repo/'experiments/qlib'/filename); require(len(review['events']) == count, 'cash review count')
        for event in review['events']:
            bound(base/directory, event['file'], event['pdf_sha256']); checked += 1
            require(event['instrument'] in CODES and '2022-12-01' <= event['ex_date'] <= END
                and event['unit_denominator'] == 10 and event['personal_income_tax_rate_assumption'] == '0', 'cash event scope/units')
        events.extend(review['events'])
    require(len(events) == len({e['event_id'] for e in events}) == 8, 'unique eight cash events')
    provider = read(base/'etf-interim2026-actions-derived-20261021/summary.json')['funds']
    for code in CODES:
        require(provider[code]['share_changes'] == [], 'unmodeled share change')
        selected = [e for e in events if e['instrument'] == code and e['ex_date'].startswith('2026')]
        keys = ('recorded','ex_date','pay_date','cash_per_unit')
        require(sorted(tuple(e[k] for k in keys) for e in selected) == sorted(tuple(e[k] for k in keys) for e in provider[code]['dividends']), 'provider/review cash correspondence')
    run = base/'etf-prior2-12-continuous-interim2026-20261021'; summary = read(run/'summary.json')
    require(summary['request_sha256'] == REQUEST_SHA and summary['candidate_id'] == request['candidate_id']
        and summary['reference_extra_cost_bps'] == 40, 'output identity/reference')
    for name, expected in summary['artifact_sha256'].items(): bound(run, name, expected); checked += 1
    for flag in ('account_reset_at_2026','full_October','historical_arrival_certified','primary_action_completeness_certified',
                 'opening_execution_certified','candidate_promoted','objective_achieved'):
        require(summary[flag] is False, 'unwarranted continuation admission')
    formations = independent_formations(days, prices, events)
    development_formations = independent_formations(olddays, prices, events, expected_count=24)
    previous_run = base/'etf-prior2-12-physical-development-20261021'; previous_summary = read(previous_run/'summary.json')
    results, ledgers, prefix_receipts = {}, {}, {}
    for extra in (20,40):
        oldledger = read(previous_run/('extra'+str(extra)+'-ledger.json'))
        audit_case(extra, oldledger, previous_summary['summaries'][str(extra)], olddays, prices, events, development_formations)
        ledger = read(run/('extra'+str(extra)+'-ledger.json')); ledgers[extra] = ledger
        verify_prefix(ledger, oldledger)
        prefix_receipts[str(extra)] = {'status':'ALL_SIX_FROZEN_COLLECTIONS_IDENTICAL', 'old_ledger_sha256':sha(previous_run/('extra'+str(extra)+'-ledger.json'))}
        results[str(extra)] = audit_case(extra, ledger, summary['summaries'][str(extra)], days, prices, events, formations)
    rejected = []
    for label, mutate in [
        ('daily_cash', lambda x:x['days'][0].update(cash='1')),
        ('fill_fee', lambda x:x['fills'][0].update(cost='0')),
        ('ranking', lambda x:x['intents'][0]['formation'].update(leader='SH510300')),
        ('fixed_quantity', lambda x:x['intents'][0]['decisions'][0].update(quantity=100)),
        ('funding_timestamp', lambda x:x['funding_intents'][0].update(execution_session='1900-01-01')),
        ('lag_endpoint', lambda x:x['intents'][0]['formation'].update(signal_end_monthend=x['intents'][0]['formation']['excluded_monthend'])),
        ('lag_month_count', lambda x:x['intents'][0]['formation'].update(return_month_count=12)),
        ('new_year_receivable', lambda x:next(r for r in x['days'] if r['day'].startswith('2026')).update(cash_receivable='0.01')),
    ]:
        altered = copy.deepcopy(ledgers[40]); mutate(altered)
        try:audit_case(40, altered, summary['summaries']['40'], days, prices, events, formations)
        except AssertionError:rejected.append(label)
        else:raise AssertionError('negative control not caught: '+label)
    altered_summary = copy.deepcopy(summary['summaries']['40']); altered_summary['annual']['2026_interim']['starting_equity']='1000000'
    try:audit_case(40, ledgers[40], altered_summary, days, prices, events, formations)
    except AssertionError:rejected.append('year_reset_denominator')
    else:raise AssertionError('year reset was not caught')
    disposition = ('CONDITIONAL_INTERIM_NUMERIC_SCREEN_PASSED_FULL_HORIZON_AND_ADMISSION_PENDING' if results['40']['numeric_screen_passes']
                   else 'CONDITIONAL_INTERIM_NUMERIC_SCREEN_FAILED')
    result = {'status':'INDEPENDENT_STDLIB_CONTINUOUS_INTERIM2026_AUDIT_PASSED','script_sha256':sha(__file__),
        'parent_auditor_sha256':PARENT_AUDITOR_SHA,'request_sha256':REQUEST_SHA,'output_summary_sha256':sha(run/'summary.json'),
        'binding_group_counts':{k:len(request[k]) for k in ('method_code_sha256','local_source_sha256','public_evidence_sha256')},
        'verified_file_bindings':checked,'source_overlap_and_calendar_checks':source_checks,
        'official_closure_ranges_independently_checked':7,'all_six_development_prefix_collections':prefix_receipts,
        'production_modules_imported':False,'new_network_queries':0,'new_2026_queries':0,'new_strategy_variants':0,
        'profiles':results,'in_memory_negative_controls_rejected':rejected,'discrepancies':[],
        'reference_disposition':disposition,'full_October':False,'candidate_promoted':False,'objective_achieved':False,
        'limits':['Current-vintage source data do not establish historical arrival or absence of missing corporate actions.',
            'July2026 510500 notice is a distributor-hosted manager PDF; issuer-host byte identity remains unverified.',
            'Opening fills, queue/capacity and complete official historical limit streams remain uncertified.',
            'This is adaptive-development continuation through October20, not full October or a sealed holdout.',
            'No strategy change or investment admission follows from this audit.']}
    with output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'status':result['status'],'verified_file_bindings':checked,'profiles':results,
        'reference_disposition':disposition,'negative_controls':rejected,'discrepancies':[]},ensure_ascii=False))


if __name__ == '__main__':
    main()
