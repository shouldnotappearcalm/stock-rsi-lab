"""Independent initial-equal-entry stdlib audit; no production imports.

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

CODES = ('SH510300', 'SH510500', 'SZ159915')
REQUEST_SHA = 'c5b02ff02bede888289f103647cdbd866d33ca24f35ea9dafd84eb0cf15acc46'
PARENT_AUDITOR_SHA = '9407af7715e58165797f91100c4fda068bcfbb823aca5f91cc7ca52c8ec0e0aa'
CANDIDATE_REASON = 'fixed initial equal-weight buy and hold'
LEGACY_REASON = 'fixed three domestic ETF prior2-12 excluding recent month, prior-close 95% target'
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


def independent_formations(days, prices, events, *, prior2_to12=True):
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
            if len(endpoints) >= 13 and following and '2024' <= following[:4] <= '2025':
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
    require(len(formations) == 24, '24 independent formations required')
    return formations


def audit_case(extra, ledger, summary, days, prices, events, formations, *, decision_reason=CANDIDATE_REASON, equal_entry=False):
    day_rows = ledger['days']
    require([r['day'] for r in day_rows] == [d for d in days if '2024' <= d[:4] <= '2025'], 'outcome dates')
    rows = {r['day']: r for r in day_rows}
    intents = {r['formation']['as_of']: r for r in ledger['intents']}
    require(len(intents) == len(ledger['intents']) == len(formations) and set(intents) == set(formations), 'monthly intent coverage')
    orders = {o['order_id']: o for o in ledger['orders']}
    require(len(orders) == len(ledger['orders']), 'duplicate order ids')
    reported_fills = ledger['fills']
    if equal_entry:
        require(set(intents) == {'2023-12-29'} and len(orders) == 3 and len(reported_fills) <= 3
            and all(o['action'] == 'BUY' and o['submitted_at'] == stamp('2023-12-29', True)
                    and o['eligible_at'] == stamp('2024-01-02') for o in orders.values())
            and ledger['funding_intents'] == [], 'one initial three-asset purchase; no subsequent trades or funding')
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
        if '2024' <= day[:4] <= '2025':
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
            record = {'record_id': digest(expected), 'kind': ('visible_initial_equal_weight_ETF_allocation' if equal_entry else 'visible_monthly_ETF_total_returns'), 'available_at': stamp(day, True), 'payload': expected}
            snapshot = digest({'as_of': stamp(day, True), 'records': [record], 'account': {'equity': str(equity), 'cash': str(cash),
                'cash_receivable': str(receivable), 'positions': owned, 'raw_close': {c: str(v) for c, v in marks.items()}}})
            require(intent['snapshot_sha256'] == snapshot, 'formation snapshot hash')
            if equal_entry:
                require(owned == {} and equity == D('1000000'), 'initial equal-entry account before orders')
                targets = {c: int(F(equity)*F(19,60)/F(marks[c])/100)*100 for c in CODES}
            else:
                targets = {expected['leader']: int(F(equity)*F(95,100)/F(marks[expected['leader']])/100)*100}
            actions = []
            for code in sorted(set(owned) | set(targets)):
                held = owned.get(code, 0); target = targets.get(code, 0)
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
    for year in ('2024', '2025'):
        subset = [r for r in reconstructed if r['day'].startswith(year)]
        peak, drawdown = prior, D(0)
        for row in subset:
            peak = max(peak, row['equity']); drawdown = min(drawdown, row['equity']/peak-1)
        annual[year] = {'net_return': subset[-1]['equity']/prior-1, 'ending_equity': subset[-1]['equity'],
            'max_drawdown': drawdown, 'average_exposure': sum((r['exposure'] for r in subset), D(0))/len(subset), 'sessions': len(subset)}
        require(all(D(summary['annual'][year][k]) == v for k, v in annual[year].items()), 'annual aggregation '+year)
        prior = subset[-1]['equity']
    gross_dividends = sum((D(x['cash_gross']) for x in expected_corporate if x['kind'] == 'EX_DATE_ENTITLEMENT'), D(0))
    require(D(summary['fees_CNY']) == sum((D(f['cost']) for f in expected_fills), D(0)) and summary['fills'] == len(expected_fills), 'aggregate fees/fills')
    require(D(summary['gross_dividends_CNY']) == gross_dividends, 'aggregate dividends')
    require(D(summary['average_exposure']) == sum((r['exposure'] for r in reconstructed), D(0))/len(reconstructed), 'aggregate exposure')
    screen = all(x['net_return'] > 0 and x['average_exposure'] >= D('.9') for x in annual.values())
    require(summary['numerical_development_screen_passed'] is screen, 'numeric screen')
    for flag in ('source_or_execution_admission', 'candidate_promoted', 'new_2026_queries', 'objective_achieved'):
        require(summary[flag] is False, 'unwarranted summary admission')
    return {'sessions_verified': len(reconstructed), 'warmup_and_outcome_sessions_reconstructed': len(days),
        'formation_intents_and_integer_targets_verified': len(intents), 'funding_intents_verified': len(funding),
        'orders_verified': len(orders), 'fills_verified': len(expected_fills), 'corporate_rows_verified': len(expected_corporate),
        'all_five_recorded_entitlements': entitlements, 'gross_dividends_CNY': str(gross_dividends),
        'positive_record_entitlements': sum(q > 0 for q in entitlements.values()),
        'cash_payments_verified': [r for r in expected_corporate if r['kind'] == 'NET_DIVIDEND_CASH_AVAILABLE'],
        'annual': {y: {k: str(v) if isinstance(v, D) else v for k, v in values.items()} for y, values in annual.items()},
        'numeric_screen_passes': screen}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    base, repo, output = Path(args.source_root), Path(args.repo), Path(args.output)
    require(not output.exists(), 'preserve existing audit result')
    request_path = repo/'experiments/qlib/etf-equal-entry-pre2026-replay-request.json'
    require(sha(request_path) == REQUEST_SHA, 'wrong frozen replay request')
    request = read(request_path)
    require(request['candidate_id'] == 'three_domestic_broad_ETF_initial_equal_entry_hold' and request['candidate_budget'] == 1
        and request['total_ETF_family_candidate_budget_so_far'] == 3 and request['reference_extra_cost_bps'] == 40
        and request['extra_cost_bps'] == [20, 40] and request['unchanged_engine_controls'] == [20, 40], 'fixed candidate scope/budget')
    require(request['target_weight_ratios'] == {c:['19','60'] for c in CODES}
        and request['entry_formation'] == '2023-12-29T15:05:00+08:00'
        and request['entry_execution'] == '2024-01-02T09:30:00+08:00'
        and request['dividend_reinvestment'] is False and request['annual_cash_reset'] is False, 'fixed entry/weights/cash rules')
    checked = 0
    for group, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
        for name, expected in request[group].items():
            path = bound(root, name, expected); checked += 1
            if path.name == 'manifest.json':
                for artifact, value in read(path).get('artifact_sha256', {}).items():
                    bound(path.parent, artifact, value); checked += 1
    days = [d.strip() for d in (base/'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines() if '2022-12-01' <= d.strip() <= '2025-12-31']
    require(len(days) == 749 and days == sorted(set(days)), 'source sessions')
    require(Counter(d[:4] for d in days)['2024'] == 242 and Counter(d[:4] for d in days)['2025'] == 243, 'outcome calendar years')
    prices = {}
    for code in CODES:
        packet = read(base/'etf-relative-eastmoney-development-20261021'/(code+'-raw.json'))
        require(packet['instrument'] == code and packet['mode'] == 'raw' and [r['date'] for r in packet['bars']] == days, 'raw source identity')
        prices[code] = {r['date']: r for r in packet['bars']}
    review = read(repo/'experiments/qlib/etf-five-cashflows-primary-review.json'); events = review['events']
    require(review['status'] == 'FIVE_CASH_EVENTS_MATCH_PRIMARY_NOTICES' and len(events) == 5, 'primary event review')
    for e in events:
        bound(base/'etf-five-distribution-notices-20261021', e['file'], e['pdf_sha256']); checked += 1
        require(e['instrument'] in CODES and '2022-12-01' <= e['ex_date'] <= '2025-12-31', 'pre2026 cash event')
        require(e['personal_income_tax_rate_assumption'] == '0' and e['unit_denominator'] == 10, 'cash event assumptions')
    run = base/'etf-equal-entry-pre2026-development-20261021'; summary = read(run/'summary.json')
    require(summary['request_sha256'] == REQUEST_SHA, 'output request binding')
    for name, expected in summary['artifact_sha256'].items(): bound(run, name, expected); checked += 1
    require(summary['candidate_id'] == request['candidate_id'] and summary['candidate_budget'] == 1, 'output candidate identity')
    for flag in ('new_2026_queries', 'historical_arrival_certified', 'primary_action_completeness_certified',
                 'opening_execution_certified', 'candidate_promoted', 'objective_achieved'):
        require(summary[flag] is False, 'unwarranted top-level admission')
    controls = read(run/'legacy-control-reproduction.json')
    require(controls == summary['legacy_controls_reproduced'] and set(controls) == {'20', '40'}, 'legacy reproduction receipts')
    legacy_run = base/'etf-prior2-12-physical-development-20261021'
    legacy_summary = read(legacy_run/'summary.json')
    legacy_formations = independent_formations(days, prices, events, prior2_to12=True)
    legacy_checks = {}
    for extra in (20, 40):
        path = legacy_run/('extra'+str(extra)+'-ledger.json')
        expected = {'status': 'FULL_LEGACY_CONTROL_LEDGER_REPRODUCED_WITHOUT_DIFFERENCE',
                    'source_ledger_sha256': sha(path), 'sessions': 485, 'monthly_intents': 24, 'investments_changed': False}
        require(controls[str(extra)] == expected, 'legacy control identity/scope')
        require(sha(path) == request['local_source_sha256'][str(path.relative_to(base))], 'legacy ledger frozen hash')
        verified = audit_case(extra, read(path), legacy_summary['summaries'][str(extra)], days, prices, events,
                              legacy_formations, decision_reason=LEGACY_REASON)
        legacy_checks[str(extra)] = {'status': 'BOUND_RECEIPT_AND_FULL_LEGACY_LEDGER_INDEPENDENTLY_RECONCILED',
            'source_ledger_sha256': sha(path), 'sessions_verified': verified['sessions_verified'],
            'monthly_rankings_verified': verified['formation_intents_and_integer_targets_verified']}
    require(days[days.index('2023-12-29')+1] == '2024-01-02', 'fixed entry sessions')
    formations = {'2023-12-29': {'as_of':'2023-12-29', 'signal':'INITIAL_EQUAL_WEIGHT_BUY_HOLD',
        'target_weight_ratios':{c:['19','60'] for c in CODES},
        'allocation_basis':'equal initial capital; total19/20; no subsequent orders or reinvestment'}}
    results, ledgers = {}, {}
    for extra in (20, 40):
        ledgers[extra] = read(run/('extra'+str(extra)+'-ledger.json'))
        results[str(extra)] = audit_case(extra, ledgers[extra], summary['summaries'][str(extra)], days, prices, events, formations, equal_entry=True)
    # In-memory mutation tests exercise the independent verifier without touching sources.
    mutation_names = []
    for label, mutate in (
        ('daily_cash', lambda x: x['days'][0].update(cash='1')),
        ('fill_fee', lambda x: x['fills'][0].update(cost='0')),
        ('unexpected_ranking', lambda x: x['intents'][0]['formation'].update(leader='SH510300')),
        ('formation_quantity', lambda x: x['intents'][0]['decisions'][0].update(quantity=100)),
        ('later_rebalance', lambda x: x['intents'].append(copy.deepcopy(x['intents'][0]))),
        ('initial_weight', lambda x: x['intents'][0]['formation']['target_weight_ratios'].update(SH510300=['19','59'])),
        ('entry_timestamp', lambda x: x['intents'][0].update(as_of=stamp('2024-01-02', True))),
        ('unearned_receivable', lambda x: x['days'][0].update(cash_receivable='0.01')),
    ):
        altered = copy.deepcopy(ledgers[40]); mutate(altered)
        try: audit_case(40, altered, summary['summaries']['40'], days, prices, events, formations, equal_entry=True)
        except AssertionError: mutation_names.append(label)
        else: raise AssertionError('auditor failed mutation: '+label)
    # The preregistered annual-positive/exposure gate is computed above, never selected from outcomes.
    disposition = ('NUMERICAL_DEVELOPMENT_SCREEN_PASSED_ADMISSION_STILL_PENDING' if results['40']['numeric_screen_passes']
                   else 'REJECT_NUMERICAL_DEVELOPMENT_SCREEN')
    result = {'status': 'INDEPENDENT_STDLIB_LEDGER_SIGNAL_AND_FUNDING_AUDIT_PASSED', 'script_sha256': sha(__file__),
        'request_sha256': REQUEST_SHA, 'parent_auditor_sha256': PARENT_AUDITOR_SHA,
        'output_summary_sha256': sha(run/'summary.json'), 'verified_file_bindings': checked,
        'binding_group_counts': {k: len(request[k]) for k in ('method_code_sha256', 'local_source_sha256', 'public_evidence_sha256')},
        'legacy_control_receipts_and_independent_reconstruction': legacy_checks,
        'production_modules_imported': False, 'new_network_queries': 0, 'new_2026_queries': 0,
        'profiles': results, 'in_memory_negative_controls_rejected': mutation_names, 'discrepancies': [],
        'fixed_40bp_reference_disposition': disposition,
        'candidate_id': request['candidate_id'], 'candidate_budget': 1, 'total_ETF_family_candidate_budget_so_far': 3,
        'candidate_promoted': False, 'objective_achieved': False,
        'limits': ['Current-vintage source truth and historical arrival not certified.',
            'No independent proof of absent corporate actions or complete historical event coverage.',
            'Reference price bands and opening fills remain engineering assumptions; no queue or volume capacity proof.',
            'Positive-entitlement coverage is limited to actual reconstructed entitlement quantities reported per profile; zero ownership does not test a payment path.',
            'Candidate 3 belongs to an adaptive campaign with previously consumed 2026 diagnostics; it is not a sealed holdout.',
            'This outcome audit is not investment or 2026 admission.']}
    with output.open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'status': result['status'], 'verified_file_bindings': checked, 'profiles': results,
                      'negative_controls': mutation_names, 'discrepancies': []}, ensure_ascii=False))


if __name__ == '__main__':
    main()
