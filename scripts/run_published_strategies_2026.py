"""User-selected MACD/RSI forward application; immutable signals, no exposure gate."""
import argparse
import csv
from importlib import metadata
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

from scripts import run_published_strategies as base
from scripts.run_published_strategies_strict import strict_simulation
from scripts.prepare_published_strategy_2026_data import inventory, sha, write

CANDIDATES = ('macd', 'rsi')
EXTRA = (20, 40)
END = '2026-10-27'
OLD_REQUEST = 'experiments/published-strategies/development-strict-request.json'
OLD_SHA = '6c7048b9fd2610c0db7db36d133c18ae9211778428c072a518d1b890106c9cd7'
SELECTION = 'experiments/published-strategies/forward-2026/selection.json'
NEW_METHODS = ('scripts/prepare_published_strategy_2026_data.py', 'scripts/run_published_strategies_2026.py',
               'scripts/audit_published_strategies_2026.py', 'tests/test_published_strategies_2026.py',
               'docs/research/published-strategies-2026-plan-2026-10-28.md')
PROFILE = {'status': 'FROZEN_USER_SELECTED_MACD_RSI_THROUGH_20261027', 'candidates': list(CANDIDATES),
 'candidate_budget': 2, 'extra_bps': list(EXTRA), 'continuous_account_start': '2024-01-02', 'end': END,
 'year2026_baseline': '2025_FINAL_NAV_NO_RESET', 'average_exposure_is_hard_gate': False,
 'target_exposure_cap_unchanged': .95, '2026_results_may_change_rules_or_selection': False,
 'network_during_run': False, 'source_evidence': 'ONE_VENDOR_ADJUSTED_DAILY_ENGINEERING_SAMPLE',
 'is_new_sealed_holdout': False, 'raw_share_or_investment_qualified': False}


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    with Path(path).open() as f: return list(csv.DictReader(f))


def per_year(day_rows, initial=1000000):
    previous = float(initial); periods = {}; last_day = ''
    for r in day_rows:
        day = r['session']; nav = float(r['account_value']); stock = float(r['stock_value']); fee = float(r['cost'])
        if day <= last_day or not all(math.isfinite(v) for v in (nav, stock, fee)) or nav <= 0 or fee < 0:
            raise ValueError('ordered finite solvent daily account required')
        year = day[:4]
        if year not in periods:
            periods[year] = {'baseline_CNY': previous, 'first_session': day, 'peak': previous, 'max_drawdown_pct': 0.,
                             'exposure_sum': 0., 'sessions': 0, 'cost_CNY': 0., 'orders': 0}
        p = periods[year]; p['peak'] = max(p['peak'], nav); p['max_drawdown_pct'] = min(p['max_drawdown_pct'], (nav / p['peak'] - 1) * 100)
        p['exposure_sum'] += stock / nav * 100; p['sessions'] += 1; p['cost_CNY'] += fee; p['orders'] += int(r['orders'])
        p.update(last_session=day, ending_nav_CNY=nav, net_return_pct=(nav / p['baseline_CNY'] - 1) * 100)
        previous, last_day = nav, day
    for p in periods.values():
        p['average_exposure_pct'] = p.pop('exposure_sum') / p['sessions']; p.pop('peak')
        p['cost_pct_start_nav'] = p['cost_CNY'] / p['baseline_CNY'] * 100
    return periods


def compare_prefix(short, long):
    """Same data version must yield identical earlier decisions and ledger rows."""
    short, long = Path(short), Path(long)
    count = 0
    for name in ('days.csv', 'orders.csv', 'holdings.csv'):
        a, b = rows(short / name), rows(long / name)
        prefix = [r for r in b if r['session'] <= '2025-12-31']
        if prefix != a: raise ValueError('historical account prefix changed: ' + name)
        count += len(a)
    a, b = read(short / 'decision_intents.json'), read(long / 'decision_intents.json')
    if a != [r for r in b if r['execution_session'] <= '2025-12-31']:
        raise ValueError('historical decision snapshots changed')
    return {'historical_csv_rows_identical': count, 'historical_decision_snapshots_identical': len(a)}


def validate_selection(selection, development):
    if (selection['candidates'] != list(CANDIDATES) or selection['average_exposure_is_hard_gate'] is not False
            or selection['window'] != [PROFILE['continuous_account_start'], END]):
        raise ValueError('honor exact human selection without adding exposure gate')
    for name in CANDIDATES:
        metric = development['results']['40/' + name]
        if any(type(metric.get(y)) not in (int, float) or not math.isfinite(metric[y]) or metric[y] <= 0
               for y in ('2024_return_pct', '2025_return_pct')):
            raise ValueError('fixed candidates were selected from positive 2024/2025 records')


def context(root, data, old_run):
    if sha(root / OLD_REQUEST) != OLD_SHA: raise ValueError('original frozen request changed')
    old = read(root / OLD_REQUEST); selection = read(root / SELECTION)
    validate_selection(selection, read(root / 'experiments/published-strategies/results.json'))
    if selection['frozen_original_method_source_skill_sha256'] != old['method_and_source_sha256']:
        raise ValueError('all original strategy source and skills must remain bound')
    for n, h in old['method_and_source_sha256'].items():
        if sha(root / n) != h: raise ValueError('original method or source changed: ' + n)
    methods = {**old['method_and_source_sha256'], **{n: sha(root / n) for n in NEW_METHODS}}
    old_terminal = read(root / 'experiments/published-strategies/development-strict-terminal.json')
    old_files = {n: h for n, h in old_terminal['artifact_sha256'].items() if any(n.startswith(str(e) + '/' + c + '/') for e in EXTRA for c in CANDIDATES)}
    if any(sha(old_run / n) != h for n, h in old_files.items()): raise ValueError('original actual account artifacts changed')
    runtime = {'python': sys.version.split()[0], **{n: metadata.version(n) for n in ('pyqlib', 'numpy', 'pandas')}}
    if runtime != old['runtime']: raise ValueError('same frozen installed research runtime required')
    preparation = read(data / 'preparation.json')
    for folder, end in [('pre2026', '2025-12-31'), ('through2026', END)]:
        manifest = read(data / folder / 'manifest.json')
        if manifest['end'] != end or {k: v for k, v in inventory(data / folder).items() if k != 'manifest.json'} != manifest['all_output_sha256']:
            raise ValueError('whole capped source view changed')
    vendor = read(root / 'experiments/published-strategies/forward-2026/vendor-manifest.json')
    if preparation['archive_sha256'] != vendor['archive_sha256'] or preparation['data_versions_spliced'] is not False:
        raise ValueError('one authenticated source version, no historical splice')
    public = {n: sha(root / n) for n in (OLD_REQUEST, SELECTION, 'experiments/published-strategies/results.json',
              'experiments/published-strategies/development-strict-terminal.json', 'experiments/published-strategies/forward-2026/vendor-manifest.json')}
    return {'method_sha256': methods, 'public_sha256': public, 'data_sha256': inventory(data),
            'original_case_sha256': old_files, 'runtime': runtime,
            'configs': {n: old['configs'][n] for n in CANDIDATES},
            'source_historical_prefixes_identical': preparation['all_old_quote_prefixes_identical']}


def freeze(root, data, old_run, request):
    value = {**PROFILE, **context(root, data, old_run)}
    write(request, value); return sha(request)


def verify(root, data, old_run, request, expected):
    if sha(request) != expected: raise ValueError('explicit frozen forward request hash mismatch')
    req = read(request)
    if req != {**PROFILE, **context(root, data, old_run)}: raise ValueError('frozen forward method/source/runtime/profile changed')
    return req


def simulate(provider, config, extra, out, end):
    # Reuse the original simulator and strict Exchange verbatim. The sole
    # simulation-scope change is its permitted end date; global is restored.
    with patch.object(base, 'END', end):
        metrics = strict_simulation(provider, config, extra, out)
    metrics['per_year'] = per_year(rows(out / 'days.csv'))
    return metrics


def run(root, data, old_run, request, expected, out):
    req = verify(root, data, old_run, request, expected)
    if out.exists(): raise ValueError('fresh account outputs only')
    out.mkdir(parents=True)
    state = {'status': 'FORWARD_APPLICATION_INCOMPLETE', 'complete': False, 'request_sha256': expected,
             'candidates': list(CANDIDATES), 'average_exposure_is_hard_gate': False,
             '2026_results_used_to_change_rules': False, '2026_portfolio_attempted': False,
             'raw_share_or_investment_qualified': False, 'objective_achieved': False}
    results = {}; prefix = {}; stage = 'SETUP'
    try:
        for phase, source, end in [('baseline', 'pre2026', '2025-12-31'), ('forward', 'through2026', END)]:
            for extra in EXTRA:
                for name in CANDIDATES:
                    label = str(extra) + '/' + name; stage = phase + '/' + label
                    folder = out / stage; folder.mkdir(parents=True)
                    print(stage, flush=True)
                    if phase == 'forward': state['2026_portfolio_attempted'] = True
                    metric = simulate(data / source, req['configs'][name], extra, folder, end)
                    write(folder / 'metrics.json', metric); results[stage] = metric
                    if phase == 'baseline' and req['source_historical_prefixes_identical']:
                        prefix['original/' + label] = compare_prefix(old_run / label, folder)
                    if phase == 'forward': prefix['forward/' + label] = compare_prefix(out / 'baseline' / label, folder)
            write(out / (phase + '-results.json'), {k: v for k, v in results.items() if k.startswith(phase + '/')})
        state.update(status='FROZEN_MACD_RSI_2026_APPLICATION_COMPLETE', complete=True, results=results, prefix_checks=prefix,
                     period_2026=['2026-01-05', END], no_yearly_account_reset=True,
                     actual_2026_return_ge10_by_case={str(e) + '/' + n: results['forward/' + str(e) + '/' + n]['per_year']['2026']['net_return_pct'] >= 10 for e in EXTRA for n in CANDIDATES})
    except BaseException as exc:
        state.update(error_type=type(exc).__name__, error=str(exc), failed_stage=stage); raise
    finally:
        try: state['all_inputs_unchanged'] = verify(root, data, old_run, request, expected) == req
        except BaseException as exc:
            state.update(complete=False, all_inputs_unchanged=False, status='INPUT_CHANGED_RESULTS_QUARANTINED', results={}, error=str(exc))
        state['artifact_sha256'] = inventory(out); write(out / 'terminal.json', state)
        if not state['all_inputs_unchanged']: raise ValueError('changed forward inputs; results quarantined')
    return state


def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['freeze', 'preflight', 'run'])
    for n in ('data', 'old-run', 'request'): p.add_argument('--' + n, required=True)
    p.add_argument('--expected-sha256'); p.add_argument('--out'); a = p.parse_args()
    root = Path(__file__).resolve().parents[1]; data = Path(a.data).resolve(); old = Path(a.old_run).resolve(); request = Path(a.request).resolve()
    if a.mode == 'freeze': print(freeze(root, data, old, request)); return
    if not a.expected_sha256: p.error('explicit frozen request SHA256 required')
    if a.mode == 'preflight': verify(root, data, old, request, a.expected_sha256); print('preflight PASS'); return
    if not a.out: p.error('fresh output required')
    print(run(root, data, old, request, a.expected_sha256, Path(a.out).resolve())['status'])


if __name__ == '__main__': main()
