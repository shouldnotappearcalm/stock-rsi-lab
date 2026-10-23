"""Chinese annual operating source measure; no ranks, accounts or cash-OP claim."""
import copy
from datetime import date, datetime, time, timezone
from decimal import Decimal, localcontext
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_profitability_v7 as grammar
from stock_rsi.annual_profitability import amount_CNY, aware, compact, need, OBSERVED, RECONSTRUCTED
from stock_rsi.data import digest

CONTRACT = 'CN_OP_EX_RND_SAME_EDITION_LAGGED_ASSETS_V1'
CAS19_REFERENCE = grammar.CAS19_REFERENCE
FIELDS = ('revenue', 'cost_of_sales', 'selling_expenses', 'administrative_expenses', 'research_expenses')
LABELS = dict(zip(FIELDS, (r'^(?:其中[：:]\s*)?营业收入\s*', r'^(?:其中[：:]\s*)?营业成本\s*',
                          r'^销售费用\s*', r'^管理费用\s*', r'^研发费用\s*')))


def row_values(text, label, header):
    match = re.match(label, text)
    need(match is not None, 'literal field label required')
    tail = text[match.end():]
    values = grammar.forms.v2.VALUES.fullmatch(tail)
    if values:
        return values.groups()
    alias = grammar.forms.ALIAS_VALUES.fullmatch(tail)
    need(alias is not None and '附注' in compact(header), 'two exact money columns and explicit note grammar required')
    return alias.groups()[1:]


def extract_signed_row(lines, metadata, label, field, year):
    found = []
    for start, (page, line) in enumerate(lines):
        if re.match(label, line) is None:
            continue
        parsed = None
        for width in range(1, 5):
            block = lines[start:start+width]
            if len(block) != width or any(p != page for p, _ in block):
                break
            text = '\n'.join(t for _, t in block)
            try:
                parsed = row_values(text, label, metadata['header_line'])
            except ValueError:
                continue
            after = start+width
            need(after == len(lines) or not re.fullmatch(grammar.original.MONEY, lines[after][1]),
                 'extra monetary continuation unsupported')
            found.append((page, text, parsed))
            break
        need(parsed is not None, 'bounded same-page row with two monetary cells required: '+field)
    need(len(found) == 1, 'unique consolidated field required: '+field)
    page, text, literals = found[0]
    cells = {}
    for column, literal in enumerate(literals):
        value = amount_CNY(literal, metadata['unit'])
        need(value.is_finite() and (field != 'total_assets' or value > 0), 'finite signed money and positive assets required')
        period = f'{year-column}-12-31'
        cells[period] = {'value_CNY': format(value, 'f'), 'literal': literal, 'page': page,
                         'row_text': text, 'row_text_sha256': digest(text), 'column_index': column,
                         'fiscal_end': period, **metadata}
    return cells


def parse_report(pages, report_year, *, normative_basis=None):
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit annual report year required')
    need(type(pages) in (list, tuple) and pages and all(type(p) is str for p in pages), 'ordered physical source pages required')
    lines, context = grammar.forms.prior.financial_context(pages)
    grammar.prior.reject_local_currency_conflicts(lines)
    currency = grammar.forms.reporting_currency(pages)
    income, imeta = grammar.table(lines, context, currency, pages, normative_basis,
                                  '合并利润表', '母公司利润表', report_year, True)
    balance, bmeta = grammar.table(lines, context, currency, pages, normative_basis,
                                  '合并资产负债表', '母公司资产负债表', report_year, False)
    need(bmeta['reported_comparative_balance_date'] == f'{report_year-1}-12-31',
         'same-edition explicitly dated prior December31 assets required')
    imeta['parser_contract'] = bmeta['parser_contract'] = CONTRACT
    extracted = {field: extract_signed_row(income, imeta, label, field, report_year)
                 for field, label in LABELS.items()}
    return {'income': {f'{year}-12-31': {field: extracted[field][f'{year}-12-31'] for field in FIELDS}
                       for year in (report_year, report_year-1)},
            'balances': extract_signed_row(balance, bmeta, r'^资产总计\s*', 'total_assets', report_year)}


def validate_parsed(parsed, year):
    periods = {f'{year}-12-31', f'{year-1}-12-31'}
    need(type(parsed) is dict and set(parsed) == {'income', 'balances'}
         and set(parsed['income']) == set(parsed['balances']) == periods, 'complete same-edition annual columns required')
    metadata = {'income': set(), 'balances': set()}
    for kind in ('income', 'balances'):
        for period in periods:
            fields = parsed[kind][period] if kind == 'income' else {'total_assets': parsed[kind][period]}
            need(set(fields) == (set(FIELDS) if kind == 'income' else {'total_assets'}), 'exact explicit source fields required')
            for field, cell in fields.items():
                column = year-date.fromisoformat(period).year
                header = compact(cell['header_line'])
                suffix = (f'{year}年度{year-1}年度' if kind == 'income'
                          else f'{year}年12月31日{year-1}年12月31日')
                need(cell['parser_contract'] == CONTRACT and cell['fiscal_end'] == period
                     and cell['column_index'] == column and cell['statement'] == ('合并利润表' if kind == 'income' else '合并资产负债表')
                     and header.endswith(suffix) and cell['row_text_sha256'] == digest(cell['row_text'])
                     and type(cell['page']) is int and cell['page'] >= cell['header_page'] > 0,
                     'coherent source scope, fiscal column, header and row evidence required')
                values = row_values(cell['row_text'], LABELS.get(field, r'^资产总计\s*'), cell['header_line'])
                need(cell['literal'] == values[column], 'source literal must occupy claimed fiscal column')
                amount = amount_CNY(cell['literal'], cell['unit'])
                need(type(cell['value_CNY']) is str and cell['value_CNY'] == format(amount, 'f')
                     and cell['multiplier_CNY'] == str(grammar.original.CNY_UNITS[cell['unit']])
                     and (field != 'total_assets' or amount > 0), 'normalized signed source money must match literal/unit')
                if kind == 'balances':
                    need(cell['reported_comparative_balance_date'] == f'{year-1}-12-31'
                         and cell['comparative_date_is_unresolved'] is False, 'prior balance date must be explicit')
                metadata[kind].add((cell['header_page'], cell['header_line'], cell['unit'], cell['unit_evidence_literal']))
    need(all(len(values) == 1 for values in metadata.values()), 'same-table source metadata required within each statement')


def make_report(instrument, report_year, publication_day, observed_at, document_sha256, announcement_id, parsed):
    need(type(instrument) is str and re.fullmatch(r'(SH|SZ)\d{6}', instrument), 'canonical source instrument required')
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit source report year required')
    publication = date.fromisoformat(publication_day)
    observed = aware(observed_at)
    need(publication.isoformat() == publication_day and publication > date(report_year, 12, 31)
         and observed.astimezone(ZoneInfo('Asia/Shanghai')).date() >= publication, 'annual source publication/capture chronology required')
    need(type(document_sha256) is str and re.fullmatch('[a-f0-9]{64}', document_sha256)
         and type(announcement_id) is str and re.fullmatch('[0-9]+', announcement_id), 'original PDF/announcement identity required')
    validate_parsed(parsed, report_year)
    public_end = datetime.combine(publication, time.max, ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
    result = {'contract': CONTRACT, 'instrument': instrument, 'report_year': report_year,
              'publication_day': publication_day, 'public_day_end_at': public_end.isoformat(), 'observed_at': observed.isoformat(),
              'payload': {'scope': 'CONSOLIDATED', 'document_sha256': document_sha256,
                          'announcement_id': announcement_id, 'parsed': copy.deepcopy(parsed)},
              'historical_arrival_verified': False, 'financial_version_history_complete': False,
              'financial_cross_issuer_comparability_verified': False, 'investment_factor_admitted': False}
    result['record_id'] = digest(result)
    return result


def snapshot_reports(reports, as_of, *, mode=OBSERVED):
    need(mode in (OBSERVED, RECONSTRUCTED), 'explicit observed or conditional reconstructed visibility required')
    clock = aware(as_of)
    visible = {}
    for report in reports:
        public, observed = aware(report['public_day_end_at']), aware(report['observed_at'])
        if clock < (max(public, observed) if mode == OBSERVED else public):
            continue
        need(report['contract'] == CONTRACT and report['record_id'] == digest(
             {k: v for k, v in report.items() if k != 'record_id'}), 'visible source record changed')
        payload = report['payload']
        reconstructed = make_report(report['instrument'], report['report_year'], report['publication_day'],
                                    report['observed_at'], payload['document_sha256'], payload['announcement_id'], payload['parsed'])
        need(reconstructed == report, 'visible report must satisfy complete source contract')
        key = (report['instrument'], report['report_year'], public)
        need(key not in visible or visible[key]['record_id'] == report['record_id'], 'ambiguous same-day filing editions')
        visible[key] = report
    rows = []
    for key, report in sorted(visible.items()):
        year = report['report_year']; parsed = report['payload']['parsed']
        fields = parsed['income'][f'{year}-12-31']
        with localcontext() as context:
            context.prec = 60
            revenue, cost, selling, admin = (Decimal(fields[f]['value_CNY']) for f in FIELDS[:4])
            numerator = revenue-cost-selling-admin
            assets = Decimal(parsed['balances'][f'{year-1}-12-31']['value_CNY'])
            ratio = numerator/assets
        rows.append({'instrument': report['instrument'], 'fiscal_end': f'{year}-12-31',
                     'record_id': report['record_id'], 'operating_profit_CNY': format(numerator, 'f'),
                     'lagged_assets_CNY': format(assets, 'f'), 'operating_profit_to_lagged_assets': format(ratio, 'f'),
                     'source': copy.deepcopy(report), 'visibility_mode': mode, 'investment_factor_admitted': False})
    return {'as_of': clock.isoformat(), 'visibility_mode': mode, 'records': rows,
            'all_visible_supported_editions_not_latest_eligibility': True,
            'conditional_publication_day_reconstruction': mode == RECONSTRUCTED,
            'historical_arrival_verified': False, 'financial_version_history_complete': False,
            'security_ranking_or_portfolio_returns_computed': False, 'investment_factor_admitted': False}
