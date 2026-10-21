"""Bounded source-format extension; old parser and vintage visibility unchanged.

This extracts three literal consolidated fields, never a financial-sector proxy.
Successful extraction does not establish accounting or investment suitability.
"""
import re

from stock_rsi import annual_profitability as original

CONTRACT = 'CONSOLIDATED_THREE_FIELD_SOURCE_GRAMMAR_V2'
need, compact = original.need, original.compact
CHINESE = '一二三四五六七八九十百'
NOTE = rf'(?:[{CHINESE}]+、\d{{1,3}}|[{CHINESE}]+[、]?\s*[（(](?:[{CHINESE}]+|\d{{1,3}})[）)])'
VALUES = re.compile(r'^\s*(?:' + NOTE + r'\s+)?(' + original.MONEY + r')\s+(' + original.MONEY + r')\s*$')
TITLES = ('合并资产负债表', '母公司资产负债表', '合并利润表', '母公司利润表')


def title(line):
    return re.sub(r'^\d{1,2}[、.．]', '', compact(line))


def document_identity(pages, instrument, year):
    need(re.fullmatch(r'(SH|SZ)\d{6}', instrument) is not None, 'canonical source instrument required')
    # Keep numeric token/line boundaries. No substring matching against a credit code.
    matches = []
    pattern = r'(?:公司|股票|证券)\s*代码\s*[：:|｜]?\s*(\d{6})(?!\d)'
    for i, page in enumerate(pages[:20]):
        for match in re.finditer(pattern, page):
            matches.append({'code': match.group(1), 'physical_page': i + 1, 'literal': match.group(0)})
    codes = {m['code'] for m in matches}
    annual = bool(re.search(str(year) + r'\s*年?\s*年度报告', '\n'.join(pages[:5])))
    return {'code_consistent': codes == {instrument[2:]}, 'annual_year_consistent': annual,
            'literal_code_evidence': matches, 'code_window_physical_pages': 20,
            'annual_title_window_physical_pages': 5}


def region(pages, heading, following):
    lines = [(i + 1, line.strip()) for i, page in enumerate(pages) for line in page.splitlines()]
    starts = [i for i, (_, line) in enumerate(lines) if title(line) == heading]
    ends = [i for i, (_, line) in enumerate(lines) if title(line) == following]
    need(len(starts) == len(ends) == 1 and starts[0] < ends[0],
         'unique ordered consolidated/parent table boundaries required')
    start, end = starts[0], ends[0]
    selected = lines[start:end]
    need(selected[-1][0] - selected[0][0] <= 5, 'bounded contiguous annual table required')
    # Only same-page, immediately preceding local financial-section evidence.
    local = [(p, line) for p, line in lines[max(0, start - 3):start] if p == lines[start][0]]
    return selected, local


def table(pages, heading, following, year, income):
    lines, preceding = region(pages, heading, following)
    units = []
    for page, line in lines[:12]:
        exact = re.fullmatch(r'单位[：:](元|万元)币种[：:]人民币', compact(line))
        bare = re.fullmatch(r'单位[：:](元|万元)', compact(line))
        if exact:
            units.append((exact.group(1), page, line, 'LOCAL_TABLE_CURRENCY_AND_UNIT'))
        elif bare:
            evidence = [(p, text) for p, text in preceding if re.fullmatch(
                r'财务附注中报表的单位为[：:]人民币' + bare.group(1), compact(text))]
            need(len(evidence) == 1, 'bare unit requires one same-page local explicit RMB scope')
            units.append((bare.group(1), page, line + '\n' + evidence[0][1], 'LOCAL_FINANCIAL_SECTION_EXPLICIT_RMB'))
    need(len(units) == 1, 'one explicit CNY table unit required')
    suffix = (f'{year}年度{year - 1}年度' if income else
              f'{year}年12月31日{year - 1}年12月31日')
    headers = []
    for start, (page, line) in enumerate(lines[:14]):
        if not compact(line).startswith('项目'):
            continue
        for width in range(1, 5):
            selected = lines[start:start + width]
            if len(selected) != width or any(p != page for p, _ in selected):
                break
            literal = '\n'.join(text for _, text in selected)
            if compact(literal) in ('项目附注' + suffix, '项目' + suffix):
                after = start + width
                need(after == len(lines) or not re.match(r'^(?:\d{4}|调整|重述)', compact(lines[after][1])),
                     'extra fiscal header line unsupported')
                headers.append((page, literal))
                break
    need(len(headers) == 1, 'exact two fiscal columns within four same-page header lines required')
    unit, unit_page, literal, scope = units[0]
    return lines, {'statement': heading, 'header_page': headers[0][0], 'header_line': headers[0][1],
        'unit': unit, 'multiplier_CNY': str(original.CNY_UNITS[unit]), 'unit_evidence_page': unit_page,
        'unit_evidence_literal': literal, 'unit_evidence_scope': scope, 'parser_contract': CONTRACT}


def extract_row(lines, metadata, label, field, year):
    found = []
    for page, line in lines:
        match = re.match(label, line)
        if match:
            values = VALUES.fullmatch(line[match.end():])
            need(values is not None, 'exact two monetary cells and explicit note grammar required: ' + field)
            found.append((page, line, values.groups()))
    need(len(found) == 1, 'one literal consolidated row required: ' + field)
    page, line, values = found[0]
    result = {}
    for index, literal in enumerate(values):
        value = original.amount_CNY(literal, metadata['unit'])
        need(value.is_finite() and (value > 0 if field == 'total_assets' else value >= 0),
             'valid explicit annual operating amount required')
        period = f'{year - index}-12-31'
        result[period] = {'value_CNY': format(value, 'f'), 'literal': literal, 'page': page,
            'row_text': line, 'row_text_sha256': original.digest(line), 'column_index': index,
            'fiscal_end': period, **metadata}
    return result


def parse_consolidated_tables(pages, report_year):
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit annual report year required')
    need(type(pages) in (list, tuple) and pages and all(type(p) is str for p in pages),
         'ordered physical page text required')
    income, imeta = table(pages, '合并利润表', '母公司利润表', report_year, True)
    balance, bmeta = table(pages, '合并资产负债表', '母公司资产负债表', report_year, False)
    fields = {
        'revenue': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业收入\s*', 'revenue', report_year),
        'cost_of_sales': extract_row(income, imeta, r'^(?:其中[：:]\s*)?营业成本\s*', 'cost_of_sales', report_year),
        'total_assets': extract_row(balance, bmeta, r'^资产总计\s*', 'total_assets', report_year)}
    return {f'{year}-12-31': {field: fields[field][f'{year}-12-31'] for field in original.FIELDS}
            for year in (report_year, report_year - 1)}
