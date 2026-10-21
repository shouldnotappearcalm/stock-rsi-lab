"""Source-only consolidated gross profitability with explicit financial vintages.

No security ranking, portfolio, provider, arrival certification or return scorer.
The table parser deliberately supports only a two-column annual statement schema.
"""
import copy
from datetime import date, datetime, time, timezone
from decimal import Decimal, localcontext
import re
from zoneinfo import ZoneInfo

from stock_rsi.data import digest

CONTRACT = 'CONSOLIDATED_ANNUAL_GP_TO_ASSETS_VINTAGES_V1'
OBSERVED = 'OBSERVED'
RECONSTRUCTED = 'RECONSTRUCTED_PUBLICATION_DAY_END'
CNY_UNITS = {'元': Decimal(1), '万元': Decimal(10000)}
FIELDS = ('revenue', 'cost_of_sales', 'total_assets')
MONEY = r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
TWO_VALUES = re.compile(r'^\s*(?:[一二三四五六七八九十]+、\d+\s+)?(' + MONEY + r')\s+(' + MONEY + r')\s*$')


def need(value, message):
    if not value:
        raise ValueError(message)


def aware(value):
    need(type(value) is str, 'explicit timestamp string required')
    result = datetime.fromisoformat(value)
    need(result.tzinfo is not None and result.utcoffset() is not None, 'timezone-aware timestamp required')
    return result.astimezone(timezone.utc)


def day(value):
    need(type(value) is str and date.fromisoformat(value).isoformat() == value, 'canonical date required')
    return date.fromisoformat(value)


def compact(text):
    return re.sub(r'\s+', '', text)


def amount_CNY(literal, unit):
    need(type(literal) is str and re.fullmatch(MONEY, literal) is not None
         and len(literal.replace(',', '').replace('-', '')) <= 38 and unit in CNY_UNITS,
         'bounded exact monetary literal and explicit unit required')
    with localcontext() as context:
        context.prec = 60
        return Decimal(literal.replace(',', '')) * CNY_UNITS[unit]


def region(pages, heading, following):
    lines = [(i + 1, line.strip()) for i, page in enumerate(pages) for line in page.splitlines()]
    starts = [i for i, (_, line) in enumerate(lines) if compact(line) == heading]
    ends = [i for i, (_, line) in enumerate(lines) if compact(line) == following]
    need(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'unique ordered consolidated/parent table boundaries required')
    selected = lines[starts[0]:ends[0]]
    need(selected and selected[-1][0] - selected[0][0] <= 5, 'bounded contiguous annual table required')
    return selected


def table(pages, heading, following, report_year, income):
    lines = region(pages, heading, following)
    units = [re.fullmatch(r'单位[：:](元|万元)币种[：:]人民币', compact(line)) for _, line in lines[:12]]
    units = [m.group(1) for m in units if m]
    need(len(units) == 1, 'one explicit CNY table unit required')
    suffix = (f'{report_year}年度{report_year-1}年度' if income else
              f'{report_year}年12月31日{report_year-1}年12月31日')
    headers = [(page, line) for page, line in lines[:14] if compact(line) == '项目附注' + suffix]
    need(len(headers) == 1, 'exact current/prior two-year column header required')
    return lines, {'statement': heading, 'header_page': headers[0][0], 'header_line': headers[0][1],
                   'unit': units[0], 'multiplier_CNY': str(CNY_UNITS[units[0]])}


def extract_row(lines, metadata, label, field, report_year):
    matches = []
    for page, line in lines:
        # Keep token separation in numeric cells; normalize only the row label.
        match = re.match(label, line)
        if match:
            values = TWO_VALUES.fullmatch(line[match.end():])
            need(values is not None, 'exact two unambiguous monetary cells required: ' + field)
            matches.append((page, line, values.groups()))
    need(len(matches) == 1, 'one literal consolidated row required: ' + field)
    page, line, values = matches[0]
    result = {}
    for index, literal in enumerate(values):
        value = amount_CNY(literal, metadata['unit'])
        need(value.is_finite() and (value > 0 if field == 'total_assets' else value >= 0),
             'valid explicit annual operating amount required')
        result[f'{report_year-index}-12-31'] = {'value_CNY': format(value, 'f'), 'literal': literal,
            'page': page, 'row_text': line, 'row_text_sha256': digest(line),
            'column_index': index, 'fiscal_end': f'{report_year-index}-12-31', **metadata}
    return result


def parse_consolidated_tables(pages, report_year):
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit annual report year required')
    need(type(pages) in (list, tuple) and pages and all(type(p) is str for p in pages), 'ordered physical page text required')
    income, imeta = table(pages, '合并利润表', '母公司利润表', report_year, True)
    balance, bmeta = table(pages, '合并资产负债表', '母公司资产负债表', report_year, False)
    extracted = {
        'revenue': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业收入\s*', 'revenue', report_year),
        'cost_of_sales': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业成本\s*', 'cost_of_sales', report_year),
        'total_assets': extract_row(balance, bmeta, r'^资产总计\s*', 'total_assets', report_year)}
    return {f'{year}-12-31': {field: extracted[field][f'{year}-12-31'] for field in FIELDS}
            for year in (report_year, report_year - 1)}


def make_observation(instrument, report_year, fiscal_end, publication_day, observed_at,
                     document_sha256, announcement_id, cells):
    need(re.fullmatch(r'(?:SH|SZ)\d{6}', instrument) is not None, 'canonical source instrument required')
    period, publication, observed = day(fiscal_end), day(publication_day), aware(observed_at)
    need(period.month == 12 and period.day == 31 and period.year in (report_year, report_year - 1)
         and date(report_year, 12, 31) < publication
         and observed.astimezone(ZoneInfo('Asia/Shanghai')).date() >= publication,
         'annual financial period and disclosure/capture chronology required')
    need(re.fullmatch('[a-f0-9]{64}', document_sha256) is not None and type(announcement_id) is str
         and announcement_id.isdigit(), 'original document identity required')
    need(set(cells) == set(FIELDS), 'three complete consolidated cells required')
    for field, cell in cells.items():
        need(cell['fiscal_end'] == fiscal_end and cell['column_index'] == report_year - period.year
             and cell['statement'] == ('合并资产负债表' if field == 'total_assets' else '合并利润表')
             and cell['row_text_sha256'] == digest(cell['row_text']), 'consistent literal financial evidence required')
        need(type(cell['value_CNY']) is str, 'exact normalized numeric string required')
        amount = Decimal(cell['value_CNY'])
        need(amount.is_finite() and (amount > 0 if field == 'total_assets' else amount >= 0)
             and amount == amount_CNY(cell['literal'], cell['unit']),
             'normalized CNY cell must match source literal and unit')
    public_end = datetime.combine(publication, time.max, ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
    payload = {'report_year': report_year, 'column_role': 'CURRENT' if period.year == report_year else 'COMPARATIVE',
               'scope': 'CONSOLIDATED', 'cells': copy.deepcopy(cells), 'document_sha256': document_sha256,
               'announcement_id': announcement_id}
    record = {'contract': CONTRACT, 'instrument': instrument, 'fiscal_end': fiscal_end,
              'publication_day': publication_day, 'public_day_end_at': public_end.isoformat(),
              'observed_at': observed.isoformat(), 'payload': payload}
    record['record_id'] = digest(record)
    return record


def snapshot_observations(records, as_of, *, mode=OBSERVED):
    need(mode in (OBSERVED, RECONSTRUCTED), 'explicit observed or conditional reconstructed visibility required')
    clock = aware(as_of)
    visible = {}
    for record in records:
        # Only visibility metadata is consulted before admission; future payloads
        # are never hashed, validated, or used to replace an earlier observation.
        public, observed = aware(record['public_day_end_at']), aware(record['observed_at'])
        if clock < (max(public, observed) if mode == OBSERVED else public):
            continue
        need(record['contract'] == CONTRACT and record['record_id'] == digest(
             {key: value for key, value in record.items() if key != 'record_id'}), 'visible financial record changed')
        key = (record['instrument'], record['fiscal_end'])
        previous = visible.get(key)
        if previous is not None:
            old_public = aware(previous['public_day_end_at'])
            if public == old_public:
                need(record['record_id'] == previous['record_id'], 'ambiguous same-day financial vintages')
                continue
            if public < old_public:
                continue
        visible[key] = record
    rows = []
    for key in sorted(visible):
        record = visible[key]
        cells = record['payload']['cells']
        revenue, cost, assets = (Decimal(cells[field]['value_CNY']) for field in FIELDS)
        with localcontext() as context:
            context.prec = 60
            gross_profit = revenue - cost
            ratio = gross_profit / assets
        rows.append({'instrument': key[0], 'fiscal_end': key[1], 'record_id': record['record_id'],
                     'gross_profit_CNY': format(gross_profit, 'f'), 'gross_profit_to_assets': format(ratio, 'f'),
                     'scope': 'CONSOLIDATED', 'visibility_mode': mode,
                     'source': copy.deepcopy(record), 'historical_arrival_verified': False,
                     'investment_factor_admitted': False})
    return {'as_of': clock.isoformat(), 'visibility_mode': mode, 'records': rows,
            'historical_arrival_verified': False, 'financial_version_history_complete': False,
            'conditional_publication_day_reconstruction': mode == RECONSTRUCTED,
            'security_ranking_or_portfolio_returns_computed': False, 'investment_factor_admitted': False}
