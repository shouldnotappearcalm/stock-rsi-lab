"""Frozen three-candidate daily recipe screen. No2026 execution entry point."""
import argparse
from datetime import date
from importlib import metadata
import json
import math
from pathlib import Path
import sys

from scripts.prepare_published_strategy_data import CODES, END, sha
from stock_rsi.published_signals import NAMES, admission
from stock_rsi.qlib_snapshot import QlibSnapshot

START = '2024-01-02'
PREFIX = 'experiments/published-strategies'
METHODS = ('src/stock_rsi/published_signals.py', 'src/stock_rsi/published_qlib_strategy.py',
 'src/stock_rsi/qlib_snapshot.py', 'src/stock_rsi/prior_close_orders.py', 'src/stock_rsi/qlib_daily_evidence.py',
 'scripts/prepare_published_strategy_data.py', 'scripts/run_published_strategies.py', 'scripts/audit_published_strategies.py',
 'scripts/run_qlib_profitability_pre2026.py', 'scripts/run_qlib_low_risk_pre2026.py',
 'tests/test_published_strategies.py', 'docs/research/published-strategies-protocol-2026-10-28.md')
PROFILE = {'status': 'FROZEN_THREE_2017_PUBLISHED_A_SHARE_RECIPES', 'candidate_budget': 3,
 'candidates': list(NAMES), 'account_window': [START, END], 'capital_CNY': 1000000,
 'extra_bps': [20, 40], 'target_exposure_cap': .95,
 'development_gate': '40BPS_BOTH_YEARS_POSITIVE_MEAN_EXPOSURE_GE90_ZERO_UNVERIFIED_MARKS',
 'data_evidence': 'QLIB_ADJUSTED_DAILY_ENGINEERING_SCREEN_NOT_RAW_SHARE_QUALIFICATION',
 '2026_values_permitted': False, 'network_permitted': False,
 'forward_rule': 'PASSED_SCREEN_THEN_RAW_ACCOUNT_AND_SOURCE_QA_THEN_SEPARATELY_FREEZE_UNCHANGED2026_EXTENSION'}


def write(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def inventory(folder):
    root = Path(folder)
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('symlink in frozen inputs')
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def config_path(root, name):
    return root / 'skills' / ('a-share-published-' + name.replace('_', '-')) / 'skill.json'


def bindings(root, provider):
    config = {}
    for name in NAMES:
        config[name] = json.loads(config_path(root, name).read_text())
        expected = {
            'golden_cross': {'symbols': ['SZ000001'], 'history': 121, 'short': 20, 'long': 120},
            'macd': {'symbols': ['SZ000001'], 'history': 100, 'fast': 12, 'slow': 26, 'signal': 9},
            'rsi': {'symbols': ['SZ000001', 'SH601988', 'SZ000068'], 'history': 15, 'period': 14, 'low': 30, 'high': 85, 'cash_fraction': .3},
        }[name]
        if (config[name]['id'] != name or config[name]['max_target_exposure'] != .95
                or any(type(config[name].get(k)) is not type(v) or config[name][k] != v for k, v in expected.items())):
            raise ValueError('original fixed recipe and exposure cap required')
    source = json.loads((root / PREFIX / 'source-manifest.json').read_text())
    if source['snapshot_committer_at'] >= '2024-01-01' or source['snapshot_author_at'] >= '2024-01-01':
        raise ValueError('source must predate both development years')
    if {x['strategy'] for x in source['strategies']} != set(NAMES):
        raise ValueError('exact three original sources required')
    for item in source['strategies']:
        if (config[item['strategy']]['source_snapshot'] != source['snapshot_commit']
                or config[item['strategy']]['source_blob_sha256'] != item['sha256']):
            raise ValueError('skill/source identity mismatch')
        if sha(root / PREFIX / 'upstream' / (item['strategy'] + '.py')) != item['sha256']:
            raise ValueError('original source bytes changed')
    paths = list(METHODS)
    paths += [str(p.relative_to(root)) for p in sorted((root / PREFIX / 'upstream').iterdir())]
    paths += [PREFIX + '/source-manifest.json', PREFIX + '/indicator-reference.json']
    for name in NAMES:
        paths += [str(config_path(root, name).relative_to(root)), str(config_path(root, name).with_name('SKILL.md').relative_to(root))]
    market = QlibSnapshot(provider)
    if market.calendar[-1].isoformat() != END or set(i.symbol for i in market.instruments) != set(CODES):
        raise ValueError('exact source identities and physically pre2026 calendar required')
    expected = json.loads((provider / 'manifest.json').read_text())
    actual = inventory(provider)
    if {k: v for k, v in actual.items() if k != 'manifest.json'} != expected['all_output_sha256'] or expected['2026_quote_values_read'] is not False:
        raise ValueError('prepared price prefix changed')
    runtime = {'python': sys.version.split()[0], **{x: metadata.version(x) for x in ('pyqlib', 'numpy', 'pandas')}}
    return {'method_and_source_sha256': {n: sha(root / n) for n in sorted(paths)},
            'provider_sha256': actual, 'runtime': runtime, 'configs': config}


def freeze(root, provider, path):
    request = {**PROFILE, **bindings(root, provider)}
    write(path, request)
    return sha(path)


def verify(root, provider, path, expected):
    if sha(path) != expected:
        raise ValueError('frozen request hash mismatch')
    req = json.loads(Path(path).read_text())
    if any(type(req.get(k)) is not type(v) or req[k] != v for k, v in PROFILE.items()):
        raise ValueError('frozen three-candidate protocol mismatch')
    if req != {**PROFILE, **bindings(root, provider)}:
        raise ValueError('frozen code/source/config/runtime/data changed')
    return req


def simulate(provider, config, extra, out):
    import pandas as pd
    import qlib
    from qlib.backtest import backtest
    from qlib.constant import REG_CN
    from stock_rsi.published_qlib_strategy import PublishedPriorCloseStrategy
    from stock_rsi.qlib_daily_evidence import reconcile_daily_evidence
    from scripts.run_qlib_profitability_pre2026 import summarize_report
    from scripts.run_qlib_low_risk_pre2026 import OPEN_LIMITS
    snapshot = QlibSnapshot(provider)
    qlib.init(provider_uri=str(provider), region=REG_CN, kernels=1, logging_level=40)
    strategy = PublishedPriorCloseStrategy(config=config, snapshot=snapshot)
    portfolio, indicators = backtest(start_time=START, end_time=END, strategy=strategy,
        executor={'class': 'SimulatorExecutor', 'module_path': 'qlib.backtest.executor',
                  'kwargs': {'time_per_step': 'day', 'generate_portfolio_metrics': True}},
        benchmark='SH000905', account=PROFILE['capital_CNY'],
        exchange_kwargs={'freq': 'day', 'codes': config['symbols'], 'start_time': '2023-01-03', 'end_time': END,
            'limit_threshold': OPEN_LIMITS, 'deal_price': 'open', 'open_cost': .0005 + extra / 10000,
            'close_cost': .0015 + extra / 10000, 'min_cost': 5})
    report, positions = portfolio['1day']
    expected = pd.DatetimeIndex([d for d in snapshot.calendar if START <= d.isoformat() <= END])
    if not report.index.equals(expected) or strategy.decision_days != [d.strftime('%Y-%m-%d') for d in expected]:
        raise ValueError('incomplete continuous daily account')
    for row in strategy.intents:
        asof = pd.Timestamp(row['as_of'][:10])
        equity = float(report.loc[asof, 'account']) if str(asof.date()) >= START else PROFILE['capital_CNY']
        held = positions[asof].get_stock_amount_dict() if str(asof.date()) >= START else {}
        if (not math.isclose(row['equity_at_decision'], equity, abs_tol=.01, rel_tol=1e-10)
                or row['holdings_at_decision'] != {k: float(v) for k, v in held.items()}
                or row['latest_decision_price_read'] > row['as_of'][:10]
                or any(d > row['as_of'][:10] for history in row['histories'].values() for d, _ in history)):
            raise ValueError('decision crossed account/market clock')
    evidence = reconcile_daily_evidence(report, positions, indicators['1day'][1].order_indicator_his,
        snapshot.calendar, initial_cash=PROFILE['capital_CNY'],
        signal_days={date.fromisoformat(x['as_of'][:10]) for x in strategy.intents})
    missing = []
    for row in evidence['holdings']:
        quote = snapshot.value(row['instrument'], 'close', row['session'])
        if quote is None or quote <= 0:
            missing.append({'instrument': row['instrument'], 'session': row['session']})
    report.to_pickle(out / 'report.pkl'); pd.to_pickle(positions, out / 'positions.pkl')
    for key in ('days', 'orders', 'holdings'):
        pd.DataFrame(evidence[key]).to_csv(out / (key + '.csv'), index=False)
    write(out / 'decision_intents.json', strategy.intents)
    write(out / 'missing-held-marks.json', missing)
    return {**summarize_report(report, PROFILE['capital_CNY']), 'unverified_held_marks': len(missing),
            'orders': len(evidence['orders']), 'unfilled_orders': sum(x['fill_status'] == 'UNFILLED' for x in evidence['orders']),
            'decision_snapshots': len(strategy.intents), 'raw_share_qualified': False,
            'historical_stock_status_verified': False, 'all_history_inputs_at_or_before_decision': True}


def run(root, provider, request, expected, out):
    req = verify(root, provider, request, expected)
    if out.exists():
        raise ValueError('preserve previous experiments; new output required')
    out.mkdir(parents=True)
    terminal = {'status': 'PUBLISHED_RECIPE_SCREEN_INCOMPLETE', 'request_sha256': expected,
                'complete': False, '2026_values_read': False, '2026_return_pct': None,
                'investment_admitted': False, 'objective_achieved': False}
    results = {}
    try:
        for extra in PROFILE['extra_bps']:
            for name in NAMES:
                key = str(extra) + '/' + name
                folder = out / key; folder.mkdir(parents=True)
                print('published screen ' + key, flush=True)
                metric = simulate(provider, req['configs'][name], extra, folder)
                write(folder / 'metrics.json', metric); results[key] = metric
        passed = [n for n in NAMES if admission(results['40/' + n])]
        terminal.update(status='PUBLISHED_RECIPE_SCREEN_COMPLETE', complete=True, results=results,
                        passed_development_screen=passed,
                        next_step='RAW_ACCOUNT_AND_SOURCE_QA_BEFORE_ANY2026' if passed else 'REJECT_ALL_THREE_NO2026_ACCESS')
    except BaseException as exc:
        terminal.update(error_type=type(exc).__name__, error=str(exc), failed_case=key)
        raise
    finally:
        # Preserve actual diagnostics on failure; never publish partial ROI as complete.
        try:
            terminal['all_inputs_unchanged'] = verify(root, provider, request, expected) == req
        except BaseException as changed:
            terminal.update(all_inputs_unchanged=False, complete=False, status='PUBLISHED_RECIPE_INPUT_CHANGED',
                            passed_development_screen=[], results={}, error=str(changed))
        terminal['artifact_sha256'] = inventory(out)
        write(out / 'terminal.json', terminal)
        if not terminal['all_inputs_unchanged']:
            raise ValueError('frozen inputs changed; all results quarantined')
    return terminal


def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['freeze', 'run', 'preflight'])
    p.add_argument('--provider', required=True); p.add_argument('--request', required=True)
    p.add_argument('--expected-sha256'); p.add_argument('--out'); a = p.parse_args()
    root = Path(__file__).resolve().parents[1]; provider = Path(a.provider).resolve(); request = Path(a.request).resolve()
    if a.mode == 'freeze': print(freeze(root, provider, request)); return
    if not a.expected_sha256: p.error('explicit frozen request SHA256 required')
    if a.mode == 'preflight': verify(root, provider, request, a.expected_sha256); print('preflight PASS'); return
    if not a.out: p.error('fresh output directory required')
    print(run(root, provider, request, a.expected_sha256, Path(a.out).resolve())['status'])


if __name__ == '__main__':
    main()
