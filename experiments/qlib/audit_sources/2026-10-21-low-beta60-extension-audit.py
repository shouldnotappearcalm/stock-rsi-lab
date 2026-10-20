"""Independent stdlib regression/formation audit, with no portfolio calculation."""
import argparse
import copy
import hashlib
import json
import math
import struct
from datetime import date
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


parser = argparse.ArgumentParser()
for name in ('source-root', 'provider-uri', 'formation-dir', 'output'):
    parser.add_argument('--' + name, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[3]
base, provider, outdir = Path(args.source_root), Path(args.provider_uri), Path(args.formation_dir)
request_path = repo / 'experiments/qlib/low-beta60-calendar-extension-formations-request.json'
assert sha(request_path) == '70874ee1f91dc3521c4ddf474f3aed4754067c7d2b54d3d045972b18e5d8054c'
request = read(request_path)
summary = read(outdir / 'summary.json')
assert summary['request_sha256'] == sha(request_path)
for field, root in (('method_code_sha256', repo), ('public_evidence_sha256', repo), ('local_source_sha256', base)):
    assert all(sha(root / n) == h for n, h in request[field].items())
assert all(sha(outdir / n) == h for n, h in summary['artifact_sha256'].items())
calendar = (provider / 'calendars/day.txt').read_text().splitlines()
assert calendar == sorted(set(calendar)) and calendar[-1] == '2026-10-13'
membership = {}
for line in (provider / 'instruments/csi500.txt').read_text().splitlines():
    code, first, last = line.split()
    if code.startswith(('SH600', 'SH601', 'SH603', 'SH605', 'SZ000', 'SZ001', 'SZ002', 'SZ003')):
        membership.setdefault(code, []).append((first, last))
for end, field in (('2025-12-31', 'pre2026_input_sha256'), ('2026-10-13', 'extension_input_sha256')):
    codes = sorted(c for c, spans in membership.items() if any(a <= end and b >= '2023-12-29' for a, b in spans))
    paths = ['instruments/all.txt'] + [f'features/{c.lower()}/{f}.day.bin' for c in codes
             for f in ('open', 'high', 'low', 'close', 'volume', 'factor', 'amount', 'adjclose')]
    paths.append('features/sh000905/adjclose.day.bin')
    h = hashlib.sha256()
    for n in paths:
        h.update(n.encode() + b'\0')
        h.update((provider / n).read_bytes())
        h.update(b'\0')
    assert h.hexdigest() == request[field]['price_files']
    for n, expected in request[field].items():
        if n != 'price_files':
            assert sha(provider / n) == expected
index = {d: i for i, d in enumerate(calendar)}
cache = {}


def value(code, field, day):
    key = code, field
    if key not in cache:
        raw = (provider / f'features/{code.lower()}/{field}.day.bin').read_bytes()
        assert len(raw) >= 8 and len(raw) % 4 == 0
        values = struct.unpack('<' + 'f' * (len(raw) // 4), raw)
        assert values[0] == int(values[0]) >= 0
        cache[key] = int(values[0]), values[1:]
    offset, prices = cache[key]
    i = index[day] - offset
    return prices[i] if 0 <= i < len(prices) and math.isfinite(prices[i]) else None


def good(values):
    return all(type(x) in (float, int) and math.isfinite(x) and x > 0 for x in values)


expected = []
for i, session in enumerate(calendar):
    if not '2024-01-02' <= session <= '2026-10-13' or i == 0 or calendar[i - 1][:7] == session[:7]:
        continue
    previous = calendar[i - 1]
    months = {}
    for day in calendar[:i]:
        months[day[:7]] = day
    ends = list(months.values())[-61:]
    assert len(ends) == 61 and ends[-1] == previous
    numbers = [date.fromisoformat(d).year * 12 + date.fromisoformat(d).month for d in ends]
    assert all(b - a == 1 for a, b in zip(numbers, numbers[1:]))
    mp = [value('SH000905', 'close', d) for d in ends]
    assert good(mp)
    xs = [mp[j + 1] / mp[j] - 1 for j in range(60)]
    xm = sum(xs) / 60
    xx = math.fsum((x - xm) ** 2 for x in xs)
    assert xx > 1e-24
    names = sorted(c for c, spans in membership.items() if any(a <= previous <= b for a, b in spans))
    assert len(names) >= 200
    scores, coefficients, vols, excluded = {}, {}, {}, {}
    for c in names:
        if not good([value(c, f, previous) for f in ('factor', 'volume', 'close')]):
            excluded[c] = 'MISSING_OR_INACTIVE_FORMATION'
            continue
        closes = [value(c, 'close', d) for d in ends]
        if not good(closes):
            excluded[c] = 'INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY'
            continue
        ys = [closes[j + 1] / closes[j] - 1 for j in range(60)]
        ym = sum(ys) / 60
        yy = math.fsum((y - ym) ** 2 for y in ys)
        if yy <= 1e-24:
            excluded[c] = 'INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY'
            continue
        beta = math.fsum((xs[j] - xm) * (ys[j] - ym) for j in range(60)) / xx
        scores[c] = beta
        coefficients[c] = {'beta': beta, 'alpha': ym - beta * xm}
        vols[c] = math.sqrt(12 * yy / 59)
    assert len(scores) >= 100 and len(scores) >= .5 * len(names)
    selected = sorted(scores, key=lambda c: (scores[c], c))[:len(scores) // 10]
    control = sorted(vols, key=lambda c: (vols[c], c))[:len(vols) // 10]
    expected.append({'execution_session': session, 'formation_asof': previous, 'endpoints': ends,
                     'members': len(names), 'scores': scores, 'coefficients': coefficients,
                     'vols': vols, 'excluded': excluded, 'selected': selected, 'control': control})
assert len(expected) == 34


def close(a, b):
    assert type(a) in (int, float) and math.isfinite(a) and math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12)


def verify(targets, receipts):
    assert set(targets) == {'low_beta60', 'eligible_equal_weight', 'low_vol60_control'}
    assert len(receipts) == 34
    assert all(list(rows) == [e['execution_session'] for e in expected] for rows in targets.values())
    for r, e in zip(receipts, expected):
        assert r['execution_session'] == e['execution_session'] and r['formation_asof'] == e['formation_asof']
        assert r['latest_factor_price_read'] == e['formation_asof'] and r['market_instrument'] == 'SH000905'
        assert r['regression_begin_close'] == e['endpoints'][0]
        assert r['return_months'] == [d[:7] for d in e['endpoints'][1:]]
        assert r['historical_members'] == e['members'] and r['eligible'] == len(e['scores'])
        assert r['excluded'] == e['excluded'] and r['selected'] == e['selected'] and r['control_selected'] == e['control']
        for field, expected_values in (('scores', e['scores']), ('control_volatility_scores', e['vols'])):
            assert set(r[field]) == set(expected_values)
            for code, v in expected_values.items():
                close(r[field][code], v)
        assert set(r['regression_coefficients']) == set(e['coefficients'])
        for c, v in e['coefficients'].items():
            assert set(r['regression_coefficients'][c]) == {'beta', 'alpha'}
            for k in ('beta', 'alpha'):
                close(r['regression_coefficients'][c][k], v[k])
        for family, selected in (('low_beta60', e['selected']), ('eligible_equal_weight', sorted(e['scores'])),
                                  ('low_vol60_control', e['control'])):
            row = targets[family][e['execution_session']]
            assert row['as_of'] == e['formation_asof'] and list(row['weights']) == selected
            for w in row['weights'].values():
                close(w, .95 / len(selected))


targets, receipts = read(outdir / 'targets.json'), read(outdir / 'formation_receipts.json')
verify(targets, receipts)
old_target = (base / request['reference_targets_file']).read_bytes()
old_receipt = (base / request['reference_receipts_file']).read_bytes()
assert (outdir / 'pre2026_targets.json').read_bytes() == old_target
assert (outdir / 'pre2026_formation_receipts.json').read_bytes() == old_receipt
assert encoded({k: {d: v for d, v in rows.items() if d < '2026'} for k, rows in targets.items()}) == old_target
assert encoded(receipts[:24]) == old_receipt
negative = {}
for label in ('changed_2026_beta', 'future_formation_clock', 'changed_target_weight'):
    t, r = copy.deepcopy(targets), copy.deepcopy(receipts)
    last = r[-1]
    if label == 'changed_2026_beta':
        c = next(iter(last['scores']))
        last['scores'][c] += .01
    elif label == 'future_formation_clock':
        last['latest_factor_price_read'] = last['execution_session']
    else:
        row = t['low_beta60'][last['execution_session']]['weights']
        row[next(iter(row))] += .01
    try:
        verify(t, r)
    except AssertionError:
        negative[label] = True
    else:
        raise AssertionError('accepted no-hash semantic tamper: ' + label)
assert summary['formations'] == 34 and summary['extension_formations'] == 10
assert summary['portfolio_returns_computed'] is summary['objective_achieved'] is summary['sealed_evidence'] is False
result = {'status': 'INDEPENDENT_34_FORMATIONS_REGRESSIONS_AND_FROZEN24_PREFIX_VERIFIED',
          'audit_code_sha256': sha(__file__), 'request_sha256': sha(request_path),
          'summary_sha256': sha(outdir / 'summary.json'), 'formations_reconstructed': len(expected),
          'extension_formations': 10, 'all3family_targets_reconstructed': True,
          'all_eligible_beta_alpha_volatility_and_exclusions_recomputed': True,
          'old24_targets_and_receipts_byte_identical': True, 'semantic_negative_controls_rejected': negative,
          'negative_controls_use_hash_gate': False, 'imports_project_code': False,
          'source_calendar_end': calendar[-1], 'latest_formation_asof': expected[-1]['formation_asof'],
          'portfolio_returns_computed': False, 'historical_arrival_verified': False,
          'OS_future_isolation': False, 'requested_full_october_complete': False,
          'candidate_promoted': False, 'objective_achieved': False}
output = Path(args.output)
with output.open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('independent all34 formations and original24 byte prefix verified; three semantic negatives rejected; no ROI')
