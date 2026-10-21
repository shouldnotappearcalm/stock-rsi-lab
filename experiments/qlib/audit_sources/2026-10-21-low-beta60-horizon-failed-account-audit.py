"""Independent stdlib-only audit of frozen failed account artifacts; no replay."""
import copy
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REPO = Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
OUT = BASE / 'low-beta60-intraday-horizon-20261021'
PLAN = REPO / 'experiments/qlib/low-beta60-horizon-account-plan.json'
REPORT = Path('/tmp/lowbeta-horizon-account-output-review-20261021.json')
PLAN_SHA = '26c820a9b29192e726e97c568118ed38e70c719d77f0d030ffbc9332d89e15cd'
TAX_ID = '9209326edbab25fc20575c17d79d5059ac14cdabb28e3a196617944c3cbff3d7'
PROFILES = {f'{p}/{c}' for p in (100, 500, 1000) for c in (20, 40)}
CENT = Decimal('.01')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def authenticate(root, bindings):
    for name, expected in bindings.items():
        check(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe bound path')
        check(sha(root / name) == expected, 'changed source bytes: ' + str(root / name))


def nonzero(values):
    return {k: v for k, v in values.items() if v}


def normalized_lots(positions):
    return {code: [(lot['quantity'], lot['bought_on'], Decimal(lot['price'])) for lot in lots]
            for code, lots in positions.items() if lots}


def audit_state(state, profile, events, sessions, reference):
    check(state['last_account_clock'] == ['2026-06-16', 1], 'last completed corporate clock')
    check(state['last_intraday_end'] == '2026-06-01T06:55:00+00:00', 'last execution clock')
    check(state['entitlements'][TAX_ID] == 6300, 'positive tax-event registration')
    check(state['owned_shares']['SZ000937'] == 6300, 'positive tax-event ownership')
    ledger, fills = state['corporate_ledger'], state['fills']
    participation_bps = int(profile.split('/')[0])
    for child in state['child_orders']:
        check(type(child['quantity']) is int and 0 < child['quantity'] <= 1000000, 'exchange child quantity')
        check(child['quantity'] <= child['source_volume_lower_shares'] * participation_bps // 10000, 'fixed past-window participation profile')
    for fill in fills:
        check(fill['quantity'] <= fill['current_volume_lower_shares'] * participation_bps // 10000, 'fixed current-window participation profile')
    check(all(r['day'] <= '2026-06-16' for r in ledger), 'no Jun17 corporate mutation')
    check(not any(r['event_id'] == TAX_ID and r['kind'] != 'RECORD_DATE_OWNERSHIP' for r in ledger), 'no unsupported event credit')
    check(not any(c['event_id'] == TAX_ID for c in state['cash_claims'] + state['stock_claims']), 'no unsupported claims')
    check(all(r['execution_at'][:10] <= '2026-06-16' for r in fills), 'no post-stop fills')
    registrations = [r for r in ledger if r['event_id'] == TAX_ID]
    check(len(registrations) == 1 and registrations[0]['quantity'] == 6300 and registrations[0]['day'] == '2026-06-16', 'source-event record quantity')

    cash = Decimal('1000000')
    cash_events = [(r['day'], 0, i, 'credit', r) for i, r in enumerate(ledger) if r['kind'] == 'NET_DIVIDEND_CASH_AVAILABLE']
    cash_events += [(r['execution_at'][:10], 1, i, 'fill', r) for i, r in enumerate(fills)]
    notional = Decimal(0); fees = Decimal(0); credits = Decimal(0)
    extra_bps = Decimal(profile.split('/')[1])
    for _, _, _, kind, row in sorted(cash_events):
        if kind == 'credit':
            delta = Decimal(row['cash_delta']); cash += delta; credits += delta
        else:
            gross = Decimal(row['price']) * row['quantity']
            cost = max(Decimal(5), gross * (Decimal(5) if row['action'] == 'BUY' else Decimal(15)) / 10000).quantize(CENT, rounding=ROUND_HALF_UP)
            cost += (gross * extra_bps / 10000).quantize(CENT, rounding=ROUND_HALF_UP)
            check(cost == Decimal(row['cost']), 'profile-specific fill fees')
            signed = gross if row['action'] == 'BUY' else -gross
            cash -= signed + cost; notional += signed; fees += cost
            check(cash == Decimal(row['cash_after']), 'each fill cash conservation')
    check(cash == Decimal(state['cash']), 'terminal cash conservation')

    share_deltas = defaultdict(lambda: defaultdict(int))
    for row in fills:
        share_deltas[row['execution_at'][:10]][row['security_id']] += row['quantity'] * (1 if row['action'] == 'BUY' else -1)
    for row in ledger:
        if row['kind'] == 'EX_DATE_ENTITLEMENT':
            share_deltas[row['day']][row['instrument']] += row['capital_shares'] + row.get('stock_shares', 0)
    quantities = defaultdict(int); shares_at_close = {}
    for day in sessions:
        if day > '2026-06-16': break
        for code, delta in share_deltas[day].items(): quantities[code] += delta
        check(all(q >= 0 for q in quantities.values()), 'nonnegative reconstructed inventory')
        shares_at_close[day] = nonzero(dict(quantities))
    check(nonzero(dict(quantities)) == state['owned_shares'], 'terminal economic shares conservation')

    lots = defaultdict(list)
    claims_by_kind = {(c['event_id'], c['share_kind']): c for c in state['stock_claims']}
    lot_events = []
    for i, row in enumerate(ledger):
        kind = {'CAPITAL_SHARES_LISTED': 'CAPITAL_TRANSFER', 'STOCK_DIVIDEND_SHARES_LISTED': 'STOCK_DIVIDEND'}.get(row['kind'])
        if kind:
            claim = claims_by_kind[(row['event_id'], kind)]
            check(claim['credited'] is True and claim['quantity'] == row['quantity'], 'listed stock claim')
            lot_events.append((row['day'], 0, i, 'credit', claim))
    lot_events += [(r['execution_at'][:10], 1, i, 'fill', r) for i, r in enumerate(fills)]
    for day, _, _, kind, row in sorted(lot_events):
        if kind == 'credit':
            lots[row['instrument']].append({'quantity': row['quantity'], 'bought_on': row['recorded'], 'price': '0'})
        elif row['action'] == 'BUY':
            lots[row['security_id']].append({'quantity': row['quantity'], 'bought_on': day, 'price': row['price']})
        else:
            left = row['quantity']; code = row['security_id']
            for lot in lots[code]:
                if lot['bought_on'] >= day: continue
                taken = min(left, lot['quantity']); lot['quantity'] -= taken; left -= taken
            check(left == 0, 'independent FIFO/T+1 sell inventory')
            lots[code] = [lot for lot in lots[code] if lot['quantity']]
    check(normalized_lots(lots) == normalized_lots(state['positions']), 'independent terminal lot reconstruction')
    lot_shares = defaultdict(int)
    for code, rows in state['positions'].items(): lot_shares[code] += sum(r['quantity'] for r in rows)
    for claim in state['stock_claims']:
        if not claim['credited']: lot_shares[claim['instrument']] += claim['quantity']
    check(nonzero(dict(lot_shares)) == state['owned_shares'], 'lots plus pending stock claims equal owned shares')

    registered_count = 0; ex_count = 0
    for row in ledger:
        event = events[row['event_id']]
        if row['kind'] == 'RECORD_DATE_OWNERSHIP':
            expected = shares_at_close[event['recorded']].get(event['instrument'], 0)
            check(row['day'] == event['recorded'] and row['quantity'] == expected and state['entitlements'][row['event_id']] == expected, 'record-date share reconstruction')
            registered_count += 1
        elif row['kind'] == 'EX_DATE_ENTITLEMENT':
            q = state['entitlements'][row['event_id']]
            check(row['day'] == event['ex_date'] and row['registered_quantity'] == q, 'ex-date source identity')
            gross = (Decimal(event['cash_per_share']) * q).quantize(CENT, rounding=ROUND_HALF_UP)
            income = (Decimal(event['stock_taxable_income_per_share']) * q).quantize(CENT, rounding=ROUND_HALF_UP)
            reserve = ((gross + income) * Decimal('.2')).quantize(CENT, rounding=ROUND_HALF_UP)
            check(Decimal(row['cash_gross']) == gross and Decimal(row['stress_tax_reserve']) == reserve and Decimal(row['taxable_stock_income']) == income, 'source-derived corporate cash and reserve')
            check(Decimal(row['capital_shares']) == Decimal(event['capital_per_share']) * q and Decimal(row['stock_shares']) == Decimal(event['stock_per_share']) * q, 'source-derived corporate shares')
            if q:
                check(not Decimal(event['capital_per_share']) or event['capital_tax_exempt_verified'] is True, 'earlier capital tax evidence')
                check(not Decimal(event['stock_per_share']) or event['stock_tax_basis_verified'] is True, 'earlier stock tax evidence')
            ex_count += 1
    ex_by_id = {r['event_id']: r for r in ledger if r['kind'] == 'EX_DATE_ENTITLEMENT'}
    for claim in state['cash_claims']:
        row = ex_by_id[claim['event_id']]; event = events[claim['event_id']]
        check(Decimal(claim['gross']) == Decimal(row['cash_gross']) and Decimal(claim['reserve']) == Decimal(row['stress_tax_reserve']), 'cash claim source amounts')
        check(Decimal(claim['net']) == Decimal(claim['gross']) - Decimal(claim['reserve']), 'net claim amount')
        available = next((d for d in sessions if d > event['pay_date']), None)
        check(claim['available_on'] == available, 'source-calendar cash availability')
        paid = [r for r in ledger if r['event_id'] == claim['event_id'] and r['kind'] == 'NET_DIVIDEND_CASH_AVAILABLE']
        check(len(paid) == int(claim['paid']), 'cash claim payment flag')
        if paid: check(paid[0]['day'] == available and Decimal(paid[0]['cash_delta']) == Decimal(claim['net']), 'cash claim payment ledger')
    for claim in state['stock_claims']:
        row = ex_by_id[claim['event_id']]; event = events[claim['event_id']]
        field = 'capital_shares' if claim['share_kind'] == 'CAPITAL_TRANSFER' else 'stock_shares'
        check(claim['quantity'] == row[field] and claim['listed'] == event['listed'] and claim['recorded'] == event['recorded'], 'stock claim source quantities/clocks')
    prefixes = {}
    for key, filename, clock in [('parent_instructions', 'parent_instructions.json', 'eligible_at'), ('child_orders', 'orders.json', 'submitted_at'), ('fills', 'fills.json', 'execution_at'), ('corporate_ledger', 'corporate_ledger.json', 'day')]:
        prefix = [r for r in state[key] if r[clock] < '2026-01-01']
        check(prefix == read(reference / filename), 'pre2026 four-artifact prefix: ' + key)
        prefixes[key] = len(prefix)
    return {'cash_CNY': str(cash), 'signed_fill_notional_CNY': str(notional), 'fill_fees_CNY': str(fees), 'paid_dividend_cash_CNY': str(credits), 'fills_checked': len(fills), 'record_date_quantities_reconstructed': registered_count, 'ex_date_source_rows_checked': ex_count, 'terminal_instruments': len(state['owned_shares']), 'terminal_lots': sum(len(v) for v in state['positions'].values()), 'uncredited_stock_claims': sum(not c['credited'] for c in state['stock_claims']), 'tax_event_registered_and_owned': 6300, 'last_account_clock': state['last_account_clock'], 'four_pre2026_artifact_prefix_counts': prefixes, 'cash_share_lot_claims_and_retained_prefixes_reconciled': True}


def main():
    check(sha(PLAN) == PLAN_SHA, 'frozen plan identity')
    plan = read(PLAN); summary = read(OUT / 'summary.json'); cases = read(OUT / 'case_results.json')
    check(plan['initial_CNY'] == '1000000' and plan['participation_bps'] == [100, 500, 1000] and plan['extra_cost_bps'] == [20, 40], 'six fixed profiles')
    check(summary['plan_sha256'] == PLAN_SHA and summary['initial_CNY'] == '1000000' and summary['window'] == ['2023-12-29', '2026-10-20'], 'summary fixed protocol')
    check(summary['results_by_profile'] == cases and set(cases) == PROFILES, 'same six cases')
    check(summary['method_code_sha256'] == plan['method_code_sha256'], 'summary frozen methods')
    check(summary['portfolio_returns_computed'] is False and summary['all_profiles_complete'] is False and summary['full_October_complete'] is False and summary['objective_achieved'] is False and summary['candidate_promoted'] is False, 'no success or ROI claim')
    for field, root in [('method_code_sha256', REPO), ('local_source_sha256', BASE), ('public_evidence_sha256', REPO)]: authenticate(root, plan[field])
    raw = BASE / 'low-beta60-raw-horizon-20261021'; manifest = read(raw / 'manifest.json')
    authenticate(raw / 'codes', {c + '.json': h for c, h in manifest['per_code_sha256'].items()})
    sessions = read(raw / 'calendar.json')['sessions']; check(len(sessions) == 676, 'source sessions')
    source = BASE / 'low-beta60-account-source-events-horizon-20261021'; event_summary = read(source / 'summary.json')
    authenticate(source, event_summary['artifact_sha256'])
    event_rows = read(source / 'derived_events.json'); events = {r['event_id']: r for r in event_rows}; check(len(events) == 269, 'event count')
    event = events[TAX_ID]
    check(event['instrument'] == 'SZ000937' and event['recorded'] == '2026-06-16' and event['ex_date'] == '2026-06-17' and event['capital_tax_exempt_verified'] is False and Decimal(event['capital_per_share']) == Decimal('.1'), 'retained tax source blocker')
    packet = read(raw / 'codes/SZ000937.json'); vendor = [r for r in packet['distributions'] if r['dividOperateDate'] == '2026-06-17']; check(len(vendor) == 1, 'vendor event unique')
    for source_field, field in [('dividPlanDate','announced'),('dividRegistDate','recorded'),('dividOperateDate','ex_date'),('dividPayDate','pay_date'),('dividStockMarketDate','listed')]: check(vendor[0][source_field] == event[field], 'vendor event clocks')
    for source_field, field in [('dividCashPsBeforeTax','cash_per_share'),('dividReserveToStockPs','capital_per_share'),('dividStocksPs','stock_per_share')]: check(Decimal(vendor[0][source_field]) == Decimal(event[field]), 'vendor event amounts')
    proofs = read(source / 'effective_horizon_proofs.json'); unresolved = proofs['unresolved_tax']['SZ000937|2026-06-17']
    check(unresolved['verified_exempt'] is False and unresolved['strict_tax_admission_resolved'] is False, 'unresolved proof marker')
    proof_dir = BASE / 'low-beta60-corporate-reviewed-horizon-20261021'
    authenticate(proof_dir, {d['file']: d['sha256'] for d in proofs['documents']})
    for key in ('implementation', 'supplement'): authenticate(proof_dir, {unresolved[key]['source_file']: unresolved[key]['source_sha256']})
    minute_count = 0
    for suffix, count in [('dev',1332),('2026',754)]:
        directory = BASE / f'low-beta60-minutes-{suffix}-20261021'; capture = read(directory / 'manifest.json')
        check(len(capture['per_session_sha256']) == count and capture['complete_capture'] is True, 'minute source complete')
        authenticate(directory / 'sessions', capture['per_session_sha256']); minute_count += count
        admission = BASE / ('low-beta60-minute-admission-20261021' if suffix == 'dev' else 'low-beta60-minute-admission-2026-20261021')
        check(sha(admission / 'details.json') == read(admission / 'summary.json')['details_sha256'], 'minute admission details')
    original = BASE / 'low-beta60-intraday-development-20261021'; original_summary = read(original / 'summary.json')
    for profile, result in original_summary['results_by_profile'].items(): authenticate(original / profile, result['artifact_sha256'])
    expected_files = {'summary.json', 'case_results.json'}
    results = {}; accessed_parent_days = set(); raw_bars_cache = {}
    forbidden = {'2024_return_pct','2025_return_pct','2026_through_2026-10-20_return_pct','ending_equity','2026_starting_equity','three_numeric_conditions_met_at_interim_cutoff','development_financial_prefix_identical','artifact_sha256'}
    for profile in sorted(PROFILES):
        result = cases[profile]; folder = OUT / profile
        check(result['status'] == 'INVALID_SOURCE_OR_ACCOUNT' and result['error_type'] == 'ValueError' and result['error'] == 'applicable capital transfer tax treatment is unverified' and result['portfolio_returns_computed'] is False, 'typed tax failure')
        check(not forbidden.intersection(result), 'no success metrics on failed case')
        check(set(result['failure_artifact_sha256']) == {'error.json','failed_account_state.json'}, 'only failure artifacts')
        authenticate(folder, result['failure_artifact_sha256'])
        error = read(folder / 'error.json'); check(error == {k:v for k,v in result.items() if k != 'failure_artifact_sha256'}, 'error artifact semantics')
        expected_files.update(f'{profile}/{f}' for f in result['failure_artifact_sha256'])
        state = read(folder / 'failed_account_state.json')
        results[profile] = audit_state(state, profile, events, sessions, original / profile)
        for parent in state['parent_instructions']:
            code, day = parent['security_id'], parent['eligible_at'][:10]
            if code not in raw_bars_cache:
                raw_bars_cache[code] = {r['date']: r for r in read(raw / 'codes' / (code + '.json'))['bars']}
            if day <= '2026-06-16' and raw_bars_cache[code][day]['tradestatus'] == '1':
                accessed_parent_days.add((code, day))
    check({str(p.relative_to(OUT)) for p in OUT.rglob('*') if p.is_file()} == expected_files, 'no extra successful replay outputs')
    check(summary['source_prefix_pairs'] == minute_count == 2086 and summary['compiled_events'] == 269 and summary['tape_accessed_pairs'] == 945 and summary['source_queries'] == 0, 'summary source metadata')
    check(len(accessed_parent_days) == summary['tape_accessed_pairs'], 'independent nonhalted parent-day access union')
    deviation = read(REPO / 'experiments/qlib/low-beta60-horizon-event-independent-audit.json')['capture_bound_deviation_retained']
    check(deviation == proofs['protocol_deviation'] and deviation['declared_transport_cap_enforced'] is False, 'retained capture deviation')
    negatives = {}
    first_profile = '100/20'; original_state = read(OUT / first_profile / 'failed_account_state.json')
    for name, mutate in [('cash_tamper',lambda s:s.update(cash='0')),('share_tamper',lambda s:s['owned_shares'].update(SZ000937=0)),('entitlement_erasure',lambda s:s['entitlements'].update({TAX_ID:0})),('prefix_fill_tamper',lambda s:s['fills'][0].update(price='0'))]:
        altered = copy.deepcopy(original_state); mutate(altered)
        try: audit_state(altered, first_profile, events, sessions, original / first_profile)
        except AssertionError: negatives[name] = True
        else: raise AssertionError('negative control accepted: ' + name)
    report = {'status':'INDEPENDENT_SIX_FAILED_ACCOUNTS_TAX_GUARD_AND_RETAINED_FINANCIAL_STATE_RECONCILED','frozen_commit':'d23608f7ca5b479a249c18b99f5975a9a5accbac','plan_sha256':PLAN_SHA,'summary_sha256':sha(OUT/'summary.json'),'case_results_sha256':sha(OUT/'case_results.json'),'audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'replayed_account':False,'source_queries_performed':0,'repository_or_source_edits_performed':False,'bound_inputs_unchanged':True,'binding_counts':{k:len(plan[k]) for k in ('method_code_sha256','local_source_sha256','public_evidence_sha256')},'raw_packets_authenticated':len(manifest['per_code_sha256']),'source_minute_files_authenticated':minute_count,'original_account_files_authenticated':42,'failure_artifacts_authenticated':12,'all_six_fixed_profiles_present':True,'tax_event':event,'current_vendor_record_matches_compiled_event':True,'original_unresolved_implementation_and_retrospective_supplement_PDF_hashes_verified':True,'profiles':results,'semantic_negative_controls_rejected':negatives,'capture_bound_deviation_retained':deviation,'critical_findings':[],'important_findings':[],'conclusion':'All six unchanged accounts stopped at the owned SZ000937 Jun17 unverified capital-tax event before credits. Registered and owned quantity is6300 in every profile. Cash, fill fees, economic share totals, FIFO lots, corporate claims and four retained pre2026 financial artifact prefixes reconcile independently. This is an incomplete data/tax-evidence failure, not a negative or complete2026 return result.','all_seven_financial_prefix_parity_claimed':False,'portfolio_returns_computed':False,'full_October_complete':False,'objective_achieved':False,'declined_to_judge':['Full seven-artifact prefix parity for failed accounts: complete daily, intent and ownership histories are not retained. Four available artifact types were compared directly.','True broker FIFO dividend tax treatment or legal exemption: unsupported tax evidence remains an explicit blocker; no policy or exemption inference was substituted.','Actual source-provider request count, transport timing and945 tape accesses cannot be reconstructed from these retained failure states; zero source queries and945 accesses are summary metadata, consistent with the hash-bound offline runner.']}
    report['nonhalted_parent_day_union_independently_reconstructed'] = len(accessed_parent_days)
    report['all_child_and_fill_participation_bounds_checked_for_fixed_profiles'] = True
    report['declined_to_judge'][-1] = 'Actual source-provider query count and transport timing are not independently measurable from these retained states; the offline hash-bound runner makes no source queries. The945 tape-access identities were independently reconstructed as the union of nonhalted eligible parent-days.'
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'audit_code_sha256':report['audit_code_sha256'],'profiles_reconciled':len(results),'critical_findings':0,'important_findings':0,'portfolio_returns_computed':False}))


if __name__ == '__main__':
    main()
