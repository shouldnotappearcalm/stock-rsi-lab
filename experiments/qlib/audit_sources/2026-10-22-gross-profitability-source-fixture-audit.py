"""Independent arithmetic/source-page check of the fixed two-report pilot.
No production import, network, security ranking, price, account or return query.
The source fixture exists before this auditor is authored; no blinded claim.
"""
import argparse
import copy
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def need(value, message):
    if not value:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def equal(actual, expected):
    need(actual == expected, 'independent source/time/math reconstruction differs')


def check(paths, expected):
    equal(set(paths), set(expected))
    for key, path in paths.items():
        equal(sha(path), expected[key])


def snapshot(records, asof, mode):
    clock = datetime.fromisoformat(asof)
    selected = {}
    for r in records:
        public = datetime.fromisoformat(r['public_day_end_at'])
        observed = datetime.fromisoformat(r['observed_at'])
        if clock < (max(public, observed) if mode == 'OBSERVED' else public):
            continue
        key = r['instrument'], r['fiscal_end']
        if key not in selected or r['public_day_end_at'] > selected[key]['public_day_end_at']:
            selected[key] = r
    rows = []
    for (code, fiscal), r in sorted(selected.items()):
        values = [Decimal(r['payload']['cells'][f]['value_CNY']) for f in ('revenue', 'cost_of_sales', 'total_assets')]
        revenue, cost, assets = values
        ratio = (Fraction(revenue) - Fraction(cost)) / Fraction(assets)
        with localcontext() as context:
            context.prec = 60
            decimal_ratio = Decimal(ratio.numerator) / Decimal(ratio.denominator)
        rows.append({'instrument': code, 'fiscal_end': fiscal, 'record_id': r['record_id'],
                     'gross_profit_CNY': format(revenue - cost, 'f'), 'gross_profit_to_assets': format(decimal_ratio, 'f'),
                     'scope': 'CONSOLIDATED', 'visibility_mode': mode, 'source': copy.deepcopy(r),
                     'historical_arrival_verified': False, 'investment_factor_admitted': False})
    return {'as_of': clock.astimezone(timezone.utc).isoformat(), 'visibility_mode': mode, 'records': rows,
            'historical_arrival_verified': False, 'financial_version_history_complete': False,
            'conditional_publication_day_reconstruction': mode != 'OBSERVED',
            'security_ranking_or_portfolio_returns_computed': False, 'investment_factor_admitted': False}


def reject(fn):
    try:
        fn()
    except (AssertionError, ValueError, KeyError):
        return True
    raise AssertionError('semantic negative was accepted')


def main():
    parser = argparse.ArgumentParser()
    for name in ('repo-root', 'source-root', 'request', 'expected-request-sha256', 'run-dir', 'output'):
        parser.add_argument('--' + name, required=True)
    a = parser.parse_args()
    root, base, run, out = map(lambda p: Path(p).resolve(), (a.repo_root, a.source_root, a.run_dir, a.output))
    need(not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(root), 'new external audit report required')
    requestfile = Path(a.request).resolve()
    equal(sha(requestfile), a.expected_request_sha256)
    request = read(requestfile)
    need(request['portfolio_returns_permitted'] is False and request['ranking_permitted'] is False
         and request['2026_financial_or_market_values_permitted'] is False, 'source-only permissions')
    paths = {key: (root if key.startswith('repo/') else base) / key.split('/', 1)[1]
             for key in request['input_sha256']}
    need(len(paths) == 32, 'fixed32 input files')
    paths['frozen_source_request'] = requestfile
    expected = {**request['input_sha256'], 'frozen_source_request': a.expected_request_sha256}
    check(paths, expected)
    initial_outputs = {p.name: sha(p) for p in sorted(run.iterdir()) if p.is_file()}
    capture = read(root / 'experiments/qlib/fundamental-primary-documents-capture-manifest.json')
    review = read(root / 'experiments/qlib/gross-profitability-source-review-2026-10-22.json')
    records = read(run / 'observations.json')
    import pypdf
    equal(pypdf.__version__, '6.10.0')
    specifications = {2023: {'revenue': (108, 108, '其中：营业收入'), 'cost_of_sales': (108, 108, '其中：营业成本'),
                             'total_assets': (105, 104, '资产总计')},
                      2024: {'revenue': (102, 102, '其中：营业收入'), 'cost_of_sales': (102, 102, '其中：营业成本'),
                             'total_assets': (99, 98, '资产总计')}}
    equal(len(records), 4)
    source_cells = {}
    for d in capture['documents']:
        year = int(d['statDate'][:4])
        pdf = base / 'fundamental-primary-documents-20261017' / d['file']
        equal(sha(pdf), d['sha256'])
        reader = pypdf.PdfReader(pdf)
        source_cells[year] = {}
        for field, (page, headerpage, label) in specifications[year].items():
            text = reader.pages[page - 1].extract_text()
            head = reader.pages[headerpage - 1].extract_text()
            need(('合并资产负债表' if field == 'total_assets' else '合并利润表') in head,
                 'visually reviewed consolidated source header')
            line = [line.strip() for line in text.splitlines() if line.strip().startswith(label)]
            equal(len(line), 1)
            # Independent curated-source extraction: the two rightmost cells,
            # not the production parser's table-region or monetary regex.
            literals = line[0].split()[-2:]
            amounts = [format(Decimal(v.replace(',', '')), 'f') for v in literals]
            for index in (0, 1):
                fiscal = str(year - index) + '-12-31'
                source_cells[year].setdefault(fiscal, {})[field] = amounts[index]
                r = next(r for r in records if r['payload']['report_year'] == year and r['fiscal_end'] == fiscal)
                cell = r['payload']['cells'][field]
                equal({k: cell[k] for k in ('value_CNY', 'literal', 'page', 'header_page', 'row_text', 'column_index', 'unit')},
                      {'value_CNY': amounts[index], 'literal': literals[index], 'page': page, 'header_page': headerpage,
                       'row_text': line[0], 'column_index': index, 'unit': '元'})
                equal(r['publication_day'], d['day'])
                equal(r['public_day_end_at'], datetime.combine(date.fromisoformat(d['day']), time.max,
                      timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat())
                equal(r['observed_at'], datetime.fromisoformat(d['captured_at_utc']).isoformat())
                equal(r['payload']['document_sha256'], d['sha256'])
        equal(source_cells[year], review['expected_cells_CNY'][str(year)])
    for r in records:
        content = {key: value for key, value in r.items() if key != 'record_id'}
        equal(r['record_id'], hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True,
                              separators=(',', ':'), allow_nan=False).encode()).hexdigest())
    snapshots = read(run / 'snapshots.json')
    equal(set(snapshots), {'OBSERVED', 'RECONSTRUCTED_PUBLICATION_DAY_END'})
    for mode, group in snapshots.items():
        equal(set(group), {'2024-04-26', '2024-04-27', '2024-04-29', '2024-12-31',
                           '2025-04-25', '2025-04-26', '2025-04-28', '2025-12-31'})
        for day, stated in group.items():
            equal(stated, snapshot(records, day + 'T15:05:00+08:00', mode))
    historical = snapshots['RECONSTRUCTED_PUBLICATION_DAY_END']['2024-12-31']
    observed = snapshots['OBSERVED']['2024-12-31']
    equal(observed['records'], [])
    equal(historical, snapshot([r for r in records if r['payload']['report_year'] == 2023],
                              '2024-12-31T15:05:00+08:00', 'RECONSTRUCTED_PUBLICATION_DAY_END'))
    controls = {}
    changed = copy.deepcopy(historical)
    changed['records'][-1]['source']['payload']['cells']['cost_of_sales']['value_CNY'] = '49997740569.45'
    controls['later_comparative_backfilled_into_2024_rejected'] = reject(lambda: equal(changed, historical))
    changed2 = copy.deepcopy(historical)
    changed2['records'][-1]['source']['payload']['cells']['total_assets']['value_CNY'] = '42504095257.83'
    controls['parent_assets_substituted_for_consolidated_rejected'] = reject(lambda: equal(changed2, historical))
    changed3 = copy.deepcopy(historical)
    changed3['records'][-1]['gross_profit_to_assets'] = '999'
    controls['changed_profitability_ratio_rejected'] = reject(lambda: equal(changed3, historical))
    controls['reconstructed_data_presented_as_observed_rejected'] = reject(lambda: equal(observed, historical))
    equal(read(run / 'input-before.json'), expected)
    post = read(run / 'input-postcheck.json')
    equal(post, {'all_inputs_unchanged': True, 'count': 33, 'mismatches': [], 'source_request_rehashed_after_processing': True})
    terminal = read(run / 'terminal.json')
    need(terminal['completed'] is True and terminal['original_error'] is None and terminal['persistence_errors'] == [], 'successful terminal')
    equal(terminal['postcheck'], post)
    summary = read(run / 'summary.json')
    need(summary['input_count'] == 33 and summary['issuer_count'] == 1 and summary['observations'] == 4
         and summary['snapshot_queries'] == 16 and summary['investment_factor_admitted'] is False
         and summary['portfolio_returns_computed'] is False and summary['objective_achieved'] is False, 'source-only summary scope')
    equal(summary['request_sha256'], a.expected_request_sha256)
    equal(summary['artifacts_sha256'], {n: sha(run / n) for n in ('observations.json', 'snapshots.json', 'page_text_sha256.json')})
    outputs = {p.name: sha(p) for p in sorted(run.iterdir()) if p.is_file()}
    equal(outputs, initial_outputs)
    equal(set(outputs), {'observations.json', 'snapshots.json', 'page_text_sha256.json', 'input-before.json',
                         'input-postcheck.json', 'terminal.json', 'summary.json'})
    check(paths, expected)
    report = {'status': 'PASS_SEPARATE_GP_SOURCE_PAGE_AND_FRACTION_AUDIT', 'audit_code_sha256': sha(__file__),
              'request_sha256': a.expected_request_sha256, 'summary_sha256': sha(run / 'summary.json'),
              'all33_inputs_sha256': expected, 'all7_outputs_sha256': outputs,
              'source_cells_CNY': source_cells, 'consolidated_cells_checked': 12, 'snapshots_checked': 16,
              'semantic_negative_controls_rejected': controls, 'production_modules_imported': False,
              'source_page_reader_dependency_shared_pypdf': '6.10.0', 'ratio_arithmetic': 'independent Fraction then Decimal60',
              'blinded_audit_claimed': False, 'data_scope': 'Two previously selected reports, one issuer, no complete universe/vintage claim',
              'historical_arrival_verified': False, 'financial_version_history_complete': False,
              'investment_factor_admitted': False, 'stock_ranking_or_account_or_returns_computed': False,
              '2026_financial_or_market_values_read': False, 'objective_achieved': False}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(report['status'], sha(out))


if __name__ == '__main__':
    main()
