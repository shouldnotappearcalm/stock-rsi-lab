"""One frozen GP candidate and two descriptive controls; pre2026 quotes only."""
import argparse
import json
import math
import sys
from importlib import metadata
from datetime import date
from pathlib import Path

from scripts.build_profitability_availability import resolve
from scripts.immutable_http_capture import file_sha as sha, need, write_once
from scripts.run_qlib_low_risk_pre2026 import (
    OPEN_LIMITS, load_state_capture, parse_memberships,
)
from stock_rsi.data import digest
from stock_rsi.gross_profitability_monthly import PRIMARY, LOW_CONTROL, NAMES, START, END, build_targets
from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.suspension_evidence import verify_suspension_mark

OUTPUT = 'gross-profitability-conditional-development-v1-20261022'
PROVIDER = 'qlib-price-delay-pre2026-clock-v2-20261021'
SOURCE = 'gross-profitability-monthly-availability-v1-20261022'
PARENT_REQUEST = 'experiments/qlib/profitability-monthly-availability-request.json'
PARENT_SHA = 'a753412c63a3b33d73ab1292bf423ea2b1ea3f3a749535e17a9a7e981e73ba7c'
PARENT_AUDIT = 'experiments/qlib/profitability-monthly-availability-audit.json'
GAP_STATES = 'low-risk-gap-states-pre2026-20261017'
STATUS = 'FROZEN_BEFORE_ONE_CONDITIONAL_GROSS_PROFITABILITY_DEVELOPMENT_SCREEN'
CAPITAL, EXTRA_BPS = 1000000, (20, 40)
METHODS = ('scripts/run_qlib_profitability_pre2026.py', 'src/stock_rsi/gross_profitability_monthly.py',
    'scripts/build_profitability_availability.py', 'src/stock_rsi/profitability_availability.py',
    'src/stock_rsi/annual_profitability.py', 'src/stock_rsi/industry_catalog.py', 'src/stock_rsi/data.py',
    'scripts/immutable_http_capture.py', 'scripts/run_qlib_low_risk_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py', 'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/capture_baostock_gap_states_pre2026.py', 'src/stock_rsi/low_risk_monthly.py',
    'src/stock_rsi/prior_close_orders.py', 'src/stock_rsi/qlib_prior_close.py',
    'src/stock_rsi/qlib_daily_evidence.py', 'src/stock_rsi/qlib_snapshot.py', 'src/stock_rsi/suspension_evidence.py')


def read(path):
    return json.loads(Path(path).read_text())


def inventory(folder):
    need(not any(p.is_symlink() for p in folder.rglob('*')), 'no symlinks in authenticated local inputs')
    return {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def verify(base, root, membership, request_file, expected_sha):
    need(sha(request_file) == expected_sha, 'frozen GP development request changed')
    req = read(request_file)
    need(req['status'] == STATUS and req['output_subdir'] == OUTPUT and req['provider_relative'] == PROVIDER
         and req['candidate'] == PRIMARY and req['controls'] == ['eligible_equal_weight', LOW_CONTROL]
         and req['candidate_budget'] == 1 and req['capital_CNY'] == CAPITAL and req['extra_bps'] == list(EXTRA_BPS)
         and req['account_window'] == [START, END] and req['target_exposure'] == .95
         and req['ranking_fraction'] == '1/10' and req['minimum_eligible'] == 100
         and req['minimum_active_cohort_fraction'] == .5
         and req['annual_freshness_rule'] == 'YEAR_MINUS2_THROUGH_JUNE_YEAR_MINUS1_FROM_JULY'
         and req['conditional_engineering_assumptions_explicit'] is True
         and req['network_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False
         and set(req['method_sha256']) == set(METHODS), 'complete single-candidate GP development contract')
    runtime = {'python': sys.version.split()[0], **{name: metadata.version(name) for name in ('pyqlib', 'numpy', 'pandas')}}
    need(req['runtime'] == runtime, 'registered installed numerical research runtime')
    paths = {key: resolve(key, root, base, membership) for key in req['input_sha256']}
    for key, path in paths.items():
        need(sha(path) == req['input_sha256'][key], 'bound GP input: ' + key)
    for name, value in req['method_sha256'].items():
        need(value == req['input_sha256']['repo/' + name], 'complete GP method binding')
    need(sha(root / PARENT_REQUEST) == PARENT_SHA, 'original full-cohort source request')
    parent, audit = read(root / PARENT_REQUEST), read(root / PARENT_AUDIT)
    need(audit['request_sha256'] == PARENT_SHA and audit['input_binding_digest'] ==
         digest({**parent['input_sha256'], 'frozen_source_request': PARENT_SHA})
         and audit['all_inputs_and_outputs_unchanged'] is True
         and audit['queries_checked'] == 48 and audit['cohort_query_rows_checked'] == 18912,
         'complete audited monthly source join')
    need(req['cohort'] == parent['cohort'] and req['formations'] == parent['formations'], 'same full cohort and formation clocks')
    for key, value in parent['input_sha256'].items():
        need(req['input_sha256'][key] == value, 'parent original-source binding retained')
    need(inventory(base / SOURCE) == audit['all_output_sha256'], 'all52 source outputs unchanged')
    for name, value in audit['all_output_sha256'].items():
        need(req['input_sha256']['source/' + SOURCE + '/' + name] == value, 'source output closure')
    provider = base / PROVIDER
    need(inventory(provider) == req['provider_inventory_sha256'], 'complete physically capped provider inventory')
    manifest = read(provider / 'manifest.json')
    need(manifest['status'] == 'PHYSICAL_PRE2026_QUOTES_WITH_ACTUAL_NEXT_SESSION_CLOCK_BOUNDARY'
         and manifest['output_calendar_end'] == manifest['all_output_values_at_or_before'] == END
         and manifest['clock_boundary']['additional_quote_values'] == 0
         and manifest['clock_boundary']['additional_simulated_sessions'] == 0, 'no2026 quote values or simulated sessions')
    days = (provider / 'calendars/day.txt').read_text().splitlines()
    need(days == sorted(set(days)) and days[-1] == END, 'actual simulation calendar physically capped')
    expected_files = set(manifest['per_feature']) | {'manifest.json', 'calendars/day.txt', 'calendars/day_future.txt',
                                                        'instruments/all.txt', 'instruments/csi500.txt'}
    need(set(req['provider_inventory_sha256']) == expected_files, 'no extra quote-source files')
    for name, meta in manifest['per_feature'].items():
        need(meta['sha256'] == req['provider_inventory_sha256'][name] and meta['last_date'] <= END
             and meta['last_index'] < len(days) and (provider / name).stat().st_size == 4 * (meta['copied_values'] + 1),
             'registered source prefix has no future quote tail')
    for name, value in req['provider_inventory_sha256'].items():
        need(req['input_sha256']['source/' + PROVIDER + '/' + name] == value, 'provider input closure')
    need(sha(base / GAP_STATES / 'manifest.json') == req['gap_state_manifest_sha256'], 'existing independent gap-source manifest')
    return req, paths


def form_targets(base, req, out):
    provider = base / PROVIDER
    snapshot = QlibSnapshot(provider)
    need(snapshot.calendar[-1].isoformat() == END, 'target reader has no2026 quote calendar')
    memberships = parse_memberships((provider / 'instruments/csi500.txt').read_text())
    views = {q['execution_session']: read(base / SOURCE / (q['execution_session'] + '-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
             for q in req['formations']}
    folder = out / 'formations'; folder.mkdir()
    def save(day, targets, receipt):
        write_once(folder / (day + '.json'), {'targets': targets, 'receipt': receipt})
    return build_targets(snapshot, memberships, req['cohort'], views, on_formation=save)


def summarize_report(report, initial_cash):
    import pandas as pd
    net = report['return'] - report['cost']
    expected = float(initial_cash) * (1 + net).cumprod()
    need(all(math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=.01)
             for a, b in zip(expected, report['account'])), 'net-return/account conservation failed')
    nav = pd.concat([pd.Series([float(initial_cash)]), report['account'].reset_index(drop=True)], ignore_index=True)
    return {'sessions': len(report), 'net_compound_return_pct': float(((1 + net).prod() - 1) * 100),
        '2024_return_pct': float(((1 + net.loc['2024']).prod() - 1) * 100),
        '2025_return_pct': float(((1 + net.loc['2025']).prod() - 1) * 100),
        'average_exposure_pct': float((report['value'] / report['account']).mean() * 100),
        'max_drawdown_pct': float((nav / nav.cummax() - 1).min() * 100),
        'cost_pct_initial': float(report['total_cost'].iloc[-1] / initial_cash * 100),
        'turnover_x_initial': float(report['total_turnover'].iloc[-1] / initial_cash),
        'final_account_CNY': float(report['account'].iloc[-1])}


def simulate(provider, targets, *, name, extra_bps, out, base, req):
    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN
    from stock_rsi.qlib_prior_close import MonthlyPriorCloseStrategy
    snapshot = QlibSnapshot(provider)
    need(snapshot.calendar[-1].isoformat() == END, 'simulation reader capped at2025')
    states = load_state_capture(base / GAP_STATES, req['gap_state_manifest_sha256'])
    qlib.init(provider_uri=str(provider), region=REG_CN, kernels=1, logging_level=30)
    strategy = MonthlyPriorCloseStrategy(targets=targets, snapshot=snapshot)
    codes = sorted({c for target in targets.values() for c in target['weights']})
    portfolio, indicators = backtest(start_time=START, end_time=END, strategy=strategy,
        executor={'class': 'SimulatorExecutor', 'module_path': 'qlib.backtest.executor',
                  'kwargs': {'time_per_step': 'day', 'generate_portfolio_metrics': True}},
        benchmark='SH000905', account=CAPITAL,
        exchange_kwargs={'freq': 'day', 'codes': codes, 'start_time': '2023-12-29', 'end_time': END,
            'limit_threshold': OPEN_LIMITS, 'deal_price': 'open', 'open_cost': .0005 + extra_bps/10000,
            'close_cost': .0015 + extra_bps/10000, 'min_cost': 5})
    report, positions = portfolio['1day']
    expected = pd.DatetimeIndex([d for d in snapshot.calendar if START <= d.isoformat() <= END])
    need(report.index.equals(expected) and len(strategy.intents) == len(req['formations'])
         and strategy.decision_days == [d.strftime('%Y-%m-%d') for d in expected], 'complete continuous daily/monthly account coverage')
    for intention in strategy.intents:
        previous = intention['as_of_close_convention'][:10]
        equity = float(report.loc[pd.Timestamp(previous), 'account']) if previous >= START else CAPITAL
        held = positions[pd.Timestamp(previous)].get_stock_amount_dict() if previous >= START else {}
        actual = intention['holdings_at_decision']
        need(math.isclose(intention['equity_at_decision'], equity, rel_tol=1e-10, abs_tol=.01)
             and set(actual) == set(held) and all(math.isclose(actual[c], float(q), rel_tol=1e-10, abs_tol=1e-8) for c, q in held.items()),
             'prior-close order sizing crossed account clock')
    evidence = reconcile_daily_evidence(report, positions, indicators['1day'][1].order_indicator_his,
        snapshot.calendar, initial_cash=CAPITAL,
        signal_days={date.fromisoformat(t['as_of']) for t in targets.values()})
    marks = []
    for row in evidence['holdings']:
        quote = snapshot.value(row['instrument'], 'close', row['session'])
        if quote is None or quote <= 0:
            marks.append(verify_suspension_mark(snapshot, row['instrument'], row['session'],
                row['normalized_price'], states.get(row['instrument'], {})))
    report.to_pickle(out / 'report.pkl'); pd.to_pickle(positions, out / 'positions.pkl')
    for key in ('days', 'orders', 'holdings'):
        pd.DataFrame(evidence[key]).to_csv(out / (key + '.csv'), index=False)
    write_once(out / 'decision_intents.json', strategy.intents)
    write_once(out / 'suspension_mark_audit.json', marks)
    return {'status': 'DAILY_PROXY_DEVELOPMENT_RECONCILED', **summarize_report(report, CAPITAL),
            'unverified_held_marks': sum(not row['verified'] for row in marks), 'orders': len(evidence['orders']),
            'unfilled_orders': sum(row['fill_status'] == 'UNFILLED' for row in evidence['orders']),
            'artifact_sha256': inventory(out)}


def run(base, root, membership, request_file, expected_sha, *, form_targets=form_targets, simulation=simulate):
    out = base / OUTPUT
    need(not out.exists(), 'fresh GP output only; no resume or overwrite')
    req, paths = verify(base, root, membership, request_file, expected_sha)
    paths = {**paths, 'frozen_request': request_file}
    expected = {**req['input_sha256'], 'frozen_request': expected_sha}
    for key, path in paths.items():
        need(sha(path) == expected[key], 'GP input before: ' + key)
    out.mkdir(parents=True)
    labels = [str(extra) + '/' + name for extra in EXTRA_BPS for name in NAMES]
    results, primary, mismatches, persistence = {}, None, [], []
    try:
        write_once(out / 'input-before.json', expected)
        targets, receipts = form_targets(base, req, out)
        need(len(receipts) == len(req['formations']) and all(r['formation_asof'] == r['latest_factor_price_read'] for r in receipts),
             'complete exact prior-close formation evidence')
        write_once(out / 'targets.json', targets); write_once(out / 'formation_receipts.json', receipts)
        for extra in EXTRA_BPS:
            for name in NAMES:
                label = str(extra) + '/' + name
                folder = out / label; folder.mkdir(parents=True)
                print('GP conditional development', label, flush=True)
                result = simulation(base / req['provider_relative'], targets[name], name=name, extra_bps=extra,
                                    out=folder, base=base, req=req)
                need(result['status'] == 'DAILY_PROXY_DEVELOPMENT_RECONCILED', 'reconciled simulation result required')
                metrics = ('2024_return_pct', '2025_return_pct', 'average_exposure_pct', 'turnover_x_initial')
                need(all(k in result and type(result[k]) in (int, float) and math.isfinite(result[k]) for k in metrics)
                     and type(result.get('unverified_held_marks')) is int and result['unverified_held_marks'] >= 0,
                     'complete finite development metrics required')
                write_once(folder / 'metrics.json', result); results[label] = result
    except BaseException as exc:
        primary = exc
    finally:
        for key, path in paths.items():
            try:
                if sha(path) != expected[key]: mismatches.append({'input': key, 'reason': 'SHA256_CHANGED'})
            except BaseException as exc:
                mismatches.append({'input': key, 'reason': type(exc).__name__})
        post = {'all_inputs_unchanged': not mismatches, 'count': len(paths), 'mismatches': mismatches}
        terminal = {'completed_profiles': list(results), 'pending_profiles': [s for s in labels if s not in results],
            'completed_formation_artifacts': sorted(p.name for p in (out / 'formations').glob('*.json')),
            'original_error': None if primary is None else {'type': type(primary).__name__, 'message': str(primary)},
            'postcheck': post, 'persistence_errors': persistence}
        for name, value in (('case_results.json', results), ('input-postcheck.json', post), ('terminal.json', terminal)):
            try: write_once(out / name, value)
            except BaseException as exc: persistence.append(name + ':' + type(exc).__name__)
    if primary is not None:
        if persistence: primary.add_note('GP terminal persistence: ' + str(persistence))
        raise primary
    need(not mismatches and not persistence, 'unchanged GP inputs and complete terminal required')
    row = results['40/' + PRIMARY]
    values = [row[k] for k in ('2024_return_pct', '2025_return_pct', 'average_exposure_pct')]
    lead = PRIMARY if (all(type(v) in (float, int) and math.isfinite(v) for v in values)
        and min(values[:2]) > 0 and values[2] >= 90 and row['unverified_held_marks'] == 0) else None
    summary = {'status': 'ONE_CONDITIONAL_GP_PRE2026_DEVELOPMENT_COMPLETE', 'candidate_budget': 1,
        'start': START, 'end': END, 'capital_CNY': CAPITAL, 'request_sha256': expected_sha,
        'results_by_extra_bps_and_family': results, 'selected_development_lead': lead,
        'selection_rule': 'Primary only,40bp: each2024/2025 net positive,average exposure>=90%,zero unverified marks; controls cannot be promoted.',
        'targets_sha256': sha(out / 'targets.json'), 'formation_receipts_sha256': sha(out / 'formation_receipts.json'),
        'input_count': len(paths), 'all_inputs_unchanged': True, 'provider_calendar_end': END,
        'historical_arrival_verified': False, 'current_business_identity_verified': False,
        'financial_reporting_compatibility_verified': False, 'financial_version_history_complete': False,
        'raw_share_execution_verified': False, 'investment_factor_admitted': False,
        '2026_financial_or_market_values_read': False, 'sealed_evidence': False, 'objective_achieved': False,
        'claim_status': 'CONDITIONAL_SOURCE_NORMALIZED_DAILY_OPEN_ENGINEERING_SCREEN_REQUIRES_SOURCE_AND_RAW_CONFIRMATION'}
    write_once(out / 'summary.json', summary)
    print('GP conditional screen complete; lead', lead, flush=True)
    return summary


def main():
    p = argparse.ArgumentParser()
    for name in ('source-root', 'membership-file', 'request', 'expected-request-sha256'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    run(Path(a.source_root).resolve(), Path(__file__).resolve().parents[1], Path(a.membership_file).resolve(),
        Path(a.request).resolve(), a.expected_request_sha256)


if __name__ == '__main__': main()
