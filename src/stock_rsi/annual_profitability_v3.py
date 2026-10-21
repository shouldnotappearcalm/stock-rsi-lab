"""Source-context grammar V3; original/V2 parsers and visibility are unchanged."""
import re

from stock_rsi import annual_profitability as original
from stock_rsi import annual_profitability_v2 as v2

CONTRACT = 'CONSOLIDATED_THREE_FIELD_SOURCE_CONTEXT_V3'
need, compact = original.need, original.compact
TITLES = v2.TITLES


def document_identity(pages, instrument, year):
    need(re.fullmatch(r'(SH|SZ)\d{6}', instrument) is not None, 'canonical source instrument required')
    pattern = r'(?:公司|股票|证券)\s*代码\s*[：:|｜]?\s*(\d{6})(?!\d)'
    cover, company, context = [], [], []
    for i, page in enumerate(pages[:20]):
        for match in re.finditer(pattern, page):
            item = {'code': match.group(1), 'physical_page': i + 1, 'literal': match.group(0)}
            context.append(item)
            if i < 5:
                cover.append(item)
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for j, line in enumerate(lines):
            if compact(line) in ('一、公司信息', '公司信息', '公司股票简况', '五、公司股票简况'):
                block = '\n'.join(lines[j:j + 8])
                for match in re.finditer(pattern, block):
                    company.append({'code': match.group(1), 'physical_page': i + 1,
                                    'literal': match.group(0), 'context': block})
            if compact(line) == '股票种类股票上市交易所股票简称股票代码变更前股票简称' and j + 1 < len(lines):
                row = lines[j + 1]
                tokens = re.findall(r'(?<!\d)\d{6}(?!\d)', row)
                if re.match(r'^A\s*股\s+', row) and len(tokens) == 1:
                    company.append({'code': tokens[0], 'physical_page': i + 1,
                                    'literal': line + '\n' + row, 'context': 'ISSUER_STOCK_INFORMATION_TABLE'})
    selected = cover if cover else company
    year_pattern = r'(?<!\d)' + r'\s*'.join(str(year)) + r'\s*年?\s*年\s*度\s*报\s*告'
    annual = bool(re.search(year_pattern, '\n'.join(pages[:5])))
    return {'code_consistent': {m['code'] for m in selected} == {instrument[2:]},
        'annual_year_consistent': annual, 'literal_code_evidence': selected,
        'code_selection_scope': 'FIRST5_COVER' if cover else 'FIRST20_ISSUER_INFORMATION',
        'other_literal_codes_retained_for_context': context,
        'code_window_physical_pages': 20, 'annual_title_window_physical_pages': 5}


def source_lines(pages):
    result = []
    for page, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.fullmatch(r'\d{1,2}[、]?', compact(line)) and i + 1 < len(lines):
                following = compact(lines[i + 1])
                if following.lstrip('、') in TITLES:
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


def reporting_currency(pages):
    # Functional currency alone is insufficient. This reviewed sentence explicitly
    # names the currency used to prepare these financial statements and its unit.
    found = []
    pattern = (r'本集团记账本位币和编制本财务报表所采用的货币均为人民币[。；;]'
               r'除有特别说明外[，,]?均以人民币(元|万元)为单位表示[。]?')
    for page, text in enumerate(pages, 1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for start in range(len(lines)):
            for width in range(1, 5):
                block = lines[start:start + width]
                if len(block) != width:
                    break
                literal = '\n'.join(block)
                match = re.fullmatch(pattern, compact(literal))
                if match:
                    found.append({'page': page, 'literal': literal, 'unit': match.group(1),
                                  'scope': 'EXPLICIT_REPORT_PREPARATION_CURRENCY_AND_UNIT'})
                    break
    need(len(found) <= 1, 'ambiguous report-preparation currency evidence')
    return found


def table(lines, context, report_currency, heading, following, year, income):
    starts = [i for i, (_, line) in enumerate(lines) if v2.title(line) == heading]
    ends = [i for i, (_, line) in enumerate(lines) if v2.title(line) == following]
    need(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'unique scoped consolidated/parent table boundaries required')
    selected = lines[starts[0]:ends[0]]
    need(selected[-1][0] - selected[0][0] <= 5, 'bounded contiguous annual table required')
    units = []
    for page, line in selected[:12]:
        exact = re.fullmatch(r'单位[：:](元|万元)币种[：:]人民币', compact(line))
        bare = re.fullmatch(r'单位[：:](元|万元)', compact(line))
        if exact:
            units.append((exact.group(1), page, line, []))
        elif bare:
            declarations = context['currency_declarations'] + report_currency
            need(declarations and all(d['unit'] == bare.group(1) for d in declarations),
                 'bare unit requires matching explicit section or report-preparation RMB evidence')
            units.append((bare.group(1), page, line, declarations))
    need(len(units) == 1, 'one explicit CNY table unit required')
    suffixes = ({f'{year}年度{year-1}年度': None} if income else {
        f'{year}年12月31日{year-1}年12月31日': f'{year-1}-12-31',
        f'{year}年12月31日{year}年1月1日': f'{year}-01-01'})
    headers = []
    for start, (page, line) in enumerate(selected[:16]):
        if not compact(line).startswith('项目'):
            continue
        for width in range(1, 9):
            block = selected[start:start + width]
            if len(block) != width or any(p != page for p, _ in block):
                break
            literal = '\n'.join(text for _, text in block)
            normalized = compact(literal)
            matching = [suffix for suffix in suffixes if normalized in ('项目附注' + suffix, '项目' + suffix)]
            if matching:
                after = start + width
                need(after == len(selected) or not re.match(r'^(?:\d{4}|调整|重述)', compact(selected[after][1])),
                     'extra fiscal header line unsupported')
                headers.append((page, literal, suffixes[matching[0]]))
                break
    need(len(headers) == 1, 'exact two fiscal columns within eight same-page nonempty header lines required')
    unit, unit_page, literal, evidence = units[0]
    metadata = {'statement': heading, 'header_page': headers[0][0], 'header_line': headers[0][1],
        'unit': unit, 'multiplier_CNY': str(original.CNY_UNITS[unit]), 'unit_evidence_page': unit_page,
        'unit_evidence_literal': literal, 'currency_scope_evidence': evidence,
        'financial_section_context': context, 'parser_contract': CONTRACT,
        'row_text_representation': 'STRIPPED_NONEMPTY_SAME_PAGE_SOURCE_LINES'}
    if not income:
        metadata['reported_comparative_balance_date'] = headers[0][2]
    return selected, metadata


def extract_row(lines, metadata, label, field, year):
    found = []
    for start, (page, line) in enumerate(lines):
        match = re.match(label, line)
        if not match:
            continue
        value = None
        for width in range(1, 5):
            block = lines[start:start + width]
            if len(block) != width or any(p != page for p, _ in block):
                break
            text = '\n'.join(text for _, text in block)
            value = v2.VALUES.fullmatch(text[match.end():])
            if value:
                # A third amount on its own continuation line is not another row.
                after = start + width
                need(after == len(lines) or not re.fullmatch(original.MONEY, lines[after][1]),
                     'extra monetary continuation cell unsupported')
                found.append((page, text, value.groups()))
                break
        need(value is not None, 'exact two monetary cells in bounded same-page row block required: ' + field)
    need(len(found) == 1, 'one literal consolidated row required: ' + field)
    page, text, values = found[0]
    result = {}
    for index, literal in enumerate(values):
        amount = original.amount_CNY(literal, metadata['unit'])
        need(amount.is_finite() and (amount > 0 if field == 'total_assets' else amount >= 0), 'valid annual amount required')
        period = f'{year-index}-12-31'
        result[period] = {'value_CNY': format(amount, 'f'), 'literal': literal, 'page': page,
            'row_text': text, 'row_text_sha256': original.digest(text), 'column_index': index,
            'fiscal_end': period, **metadata}
    return result


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
