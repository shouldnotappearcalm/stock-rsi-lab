"""V4 boundary repair: printed page numbers are not enumeration prefixes.
V3 failed source run is immutable. Other source context and visibility stay fixed.
"""
import re
from stock_rsi import annual_profitability_v3 as prior

original, v2 = prior.original, prior.v2
need, compact, TITLES = prior.need, prior.compact, prior.TITLES
CONTRACT = 'CONSOLIDATED_THREE_FIELD_SOURCE_CONTEXT_V4'
document_identity = prior.document_identity
reporting_currency = prior.reporting_currency
extract_row = prior.extract_row


def source_lines(pages):
    result = []
    for page, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            if i + 1 < len(lines):
                following = compact(lines[i + 1])
                split_after_number = re.fullmatch(r'\d{1,2}', compact(line)) and following.startswith('、') and following[1:] in TITLES
                split_after_separator = re.fullmatch(r'\d{1,2}、', compact(line)) and following in TITLES
                if split_after_number or split_after_separator:
                    line += '\n' + lines[i + 1]
                    i += 1
            result.append((page, line))
            i += 1
    return result


def financial_context(pages):
    lines = source_lines(pages)
    starts = [i for i, (_, line) in enumerate(lines) if compact(line) == '二、财务报表']
    if not starts:
        return lines, {'kind': 'GLOBAL_UNIQUE_TABLES', 'currency_declarations': []}
    need(len(starts) == 1, 'one primary financial statements section required')
    start = starts[0]
    ends = [i for i, (_, line) in enumerate(lines) if i > start and compact(line) in (
        '三、公司基本情况', '三、财务报表附注', '财务报表附注')]
    need(ends, 'explicit end of primary financial statements section required')
    end = min(ends)
    need(0 < lines[end][0] - lines[start][0] <= 40, 'primary statements section bounded to40physical pages')
    selected = lines[start:end]
    positions = [[i for i, (_, line) in enumerate(selected) if v2.title(line) == heading] for heading in TITLES]
    need(all(len(p) == 1 for p in positions) and [p[0] for p in positions] == sorted(p[0] for p in positions),
         'unique ordered primary consolidated/parent balance and income statements required')
    declarations = []
    for page, line in selected[:12]:
        match = re.fullmatch(r'财务附注中报表的单位为[：:]人民币(元|万元)', compact(line))
        if match:
            declarations.append({'page': page, 'literal': line, 'unit': match.group(1),
                                 'scope': 'EXPLICIT_PRIMARY_FINANCIAL_SECTION_RMB'})
    need(len(declarations) <= 1, 'one unambiguous primary-section currency declaration')
    return selected, {'kind': 'PRIMARY_FINANCIAL_STATEMENTS_SECTION', 'start_page': lines[start][0],
        'end_page_exclusive': lines[end][0], 'start_literal': lines[start][1],
        'end_literal': lines[end][1], 'currency_declarations': declarations}


def table(*args):
    lines, metadata = prior.table(*args)
    metadata['parser_contract'] = CONTRACT
    return lines, metadata


def parse_consolidated_tables(pages, report_year):
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit annual report year required')
    need(type(pages) in (list, tuple) and pages and all(type(p) is str for p in pages), 'ordered physical page text required')
    lines, context = financial_context(pages)
    currency = reporting_currency(pages)
    income, imeta = table(lines, context, currency, '合并利润表', '母公司利润表', report_year, True)
    balance, bmeta = table(lines, context, currency, '合并资产负债表', '母公司资产负债表', report_year, False)
    fields = {
        'revenue': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业收入\s*', 'revenue', report_year),
        'cost_of_sales': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业成本\s*', 'cost_of_sales', report_year),
        'total_assets': extract_row(balance, bmeta, r'^资产总计\s*', 'total_assets', report_year)}
    # A Jan1 opening balance is not silently relabelled as the preceding Dec31.
    # Current annual GP still has three complete current-period source fields;
    # comparative amounts remain literal row evidence, without a prior-year GP.
    years = ((report_year, report_year-1) if bmeta['reported_comparative_balance_date'] == f'{report_year-1}-12-31'
             else (report_year,))
    return {f'{year}-12-31': {field: fields[field][f'{year}-12-31'] for field in original.FIELDS} for year in years}
