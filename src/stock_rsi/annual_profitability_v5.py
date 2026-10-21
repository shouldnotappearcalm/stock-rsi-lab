"""Source-backed currency/unit and note aliases; no investment or visibility rule.

All V4 successes return their original cells verbatim. The extension still needs
two explicit fiscal columns, three literal consolidated rows and CNY evidence.
Functional currency alone is insufficient.
"""
import re
from stock_rsi import annual_profitability_v4 as prior

original, v2 = prior.original, prior.v2
need, compact = prior.need, prior.compact
CONTRACT = 'CONSOLIDATED_THREE_FIELD_CURRENCY_AND_NOTE_V5'
document_identity = prior.document_identity
NOTE_ALIAS = rf'(?:[1-9]\d{{0,2}}|[{v2.CHINESE}]+/[1-9]\d{{0,2}})'
ALIAS_VALUES = re.compile(r'^\s*(' + NOTE_ALIAS + r')\s+(' + original.MONEY + r')\s+(' + original.MONEY + r')\s*$')
DECLARATION = re.compile(
    r'(?P<literal>(?:(?:本公司|本集团|公司)编制本财务报表时所采用的货币为|'
    r'本(?:公司|集团)记账本位币和编制本财务报表所采用的货币均为)'
    r'(?P<preparation>人民币|美元|港币)[。；;]|本财务报表以(?P<presentation>人民币|美元|港币)列示[。；;])')


def reporting_currency(pages):
    found = prior.reporting_currency(pages)
    for page, text in enumerate(pages, 1):
        positions = [i for i,c in enumerate(text) if not c.isspace()]
        normalized = ''.join(text[i] for i in positions)
        for match in DECLARATION.finditer(normalized):
            line_prefix = text[:positions[match.start()]].rsplit('\n',1)[-1]
            if match.start() and normalized[match.start()-1] not in '。；;：:（(' and line_prefix.strip():
                continue
            literal = text[positions[match.start()]:positions[match.end()-1]+1]
            need(len([line for line in literal.splitlines() if line.strip()]) <= 4,
                 'reporting-currency sentence exceeds four same-page lines')
            currency = match.group('preparation') or match.group('presentation')
            need(currency == '人民币', 'explicit non-CNY financial-report currency unsupported')
            if any(d['page'] == page and compact(literal) in compact(d['literal']) for d in found):
                continue
            found.append({'page':page, 'literal':literal, 'currency':'CNY',
                          'scope':'EXPLICIT_REPORT_PREPARATION_CURRENCY_ONLY' if match.group('preparation') else
                                  'EXPLICIT_REPORT_PRESENTATION_CURRENCY_ONLY'})
    need(len(found) <= 4, 'bounded unambiguous report currency declarations required')
    return found


def explicit_local_unit(line):
    text = compact(line)
    prefix = r'(?:编制单位[：:][^：:]{1,100}?)?'
    patterns = (prefix+r'单位[：:](元|万元)币种[：:]人民币',
                prefix+r'单位[：:]人民币(元|万元)',
                r'[（(](?:除特别(?:注明|说明)外[，,])?金额单位(?:[：:]|(?:均)?为)人民币(元|万元)[）)]')
    matches = [m.group(1) for pattern in patterns if (m := re.fullmatch(pattern,text))]
    need(len(matches) <= 1, 'unambiguous explicit local CNY unit alias')
    return matches[0] if matches else None


def table(lines, context, currency, heading, following, year, income):
    starts = [i for i,(_,line) in enumerate(lines) if v2.title(line) == heading]
    ends = [i for i,(_,line) in enumerate(lines) if v2.title(line) == following]
    need(len(starts) == len(ends) == 1 and starts[0] < ends[0], 'unique scoped consolidated/parent table boundaries required')
    selected = lines[starts[0]:ends[0]]
    need(selected[-1][0]-selected[0][0] <= 5, 'bounded contiguous annual table required')
    units = []
    for page,line in selected[:12]:
        explicit = explicit_local_unit(line)
        bare = re.fullmatch(r'单位[：:](元|万元)',compact(line))
        if explicit:
            units.append((explicit,page,line,[]))
        elif bare:
            declarations = context['currency_declarations'] + currency
            need(declarations and all(d.get('unit',bare.group(1)) == bare.group(1) for d in declarations),
                 'bare unit requires matching explicit section or report-preparation RMB evidence')
            units.append((bare.group(1),page,line,declarations))
    need(len(units) == 1, 'one explicit CNY table unit required')
    suffixes = ({f'{year}年度{year-1}年度':None} if income else {
        f'{year}年12月31日{year-1}年12月31日':f'{year-1}-12-31',
        f'{year}年12月31日{year}年1月1日':f'{year}-01-01'})
    headers = []
    for start,(page,line) in enumerate(selected[:16]):
        if not compact(line).startswith('项目'): continue
        for width in range(1,9):
            block = selected[start:start+width]
            if len(block) != width or any(p != page for p,_ in block): break
            literal = '\n'.join(t for _,t in block)
            matching = [s for s in suffixes if compact(literal) in ('项目附注'+s,'项目'+s)]
            if matching:
                after = start+width
                need(after == len(selected) or not re.match(r'^(?:\d{4}|调整|重述)',compact(selected[after][1])),
                     'extra fiscal header line unsupported')
                headers.append((page,literal,suffixes[matching[0]])); break
    need(len(headers) == 1, 'exact two fiscal columns within eight same-page nonempty header lines required')
    unit,page,literal,evidence = units[0]
    metadata = {'statement':heading,'header_page':headers[0][0],'header_line':headers[0][1],
        'unit':unit,'multiplier_CNY':str(original.CNY_UNITS[unit]),'unit_evidence_page':page,
        'unit_evidence_literal':literal,'currency_scope_evidence':evidence,
        'financial_section_context':context,'parser_contract':CONTRACT,
        'row_text_representation':'STRIPPED_NONEMPTY_SAME_PAGE_SOURCE_LINES'}
    if not income: metadata['reported_comparative_balance_date'] = headers[0][2]
    return selected,metadata


def extract_row(lines, metadata, label, field, year):
    found = []
    for start,(page,line) in enumerate(lines):
        match = re.match(label,line)
        if not match: continue
        values = None
        for width in range(1,5):
            block = lines[start:start+width]
            if len(block) != width or any(p != page for p,_ in block): break
            text = '\n'.join(t for _,t in block)
            tail = text[match.end():]
            old = v2.VALUES.fullmatch(tail)
            alias = None if old else ALIAS_VALUES.fullmatch(tail)
            if alias:
                need('附注' in compact(metadata['header_line']), 'new note alias needs an explicit note column header')
                values = alias.groups()[1:]
            elif old: values = old.groups()
            if values:
                after = start+width
                need(after == len(lines) or not re.fullmatch(original.MONEY,lines[after][1]), 'extra monetary continuation cell unsupported')
                found.append((page,text,values)); break
        need(values is not None, 'exact two monetary cells in bounded same-page row block required: '+field)
    need(len(found) == 1, 'one literal consolidated row required: '+field)
    page,text,values = found[0]
    result = {}
    for index,literal in enumerate(values):
        amount = original.amount_CNY(literal,metadata['unit'])
        need(amount.is_finite() and (amount > 0 if field == 'total_assets' else amount >= 0), 'valid annual amount required')
        period = f'{year-index}-12-31'
        result[period] = {'value_CNY':format(amount,'f'),'literal':literal,'page':page,
            'row_text':text,'row_text_sha256':original.digest(text),'column_index':index,'fiscal_end':period,**metadata}
    return result


def parse_consolidated_tables(pages, report_year):
    try:
        return prior.parse_consolidated_tables(pages,report_year)
    except ValueError:
        pass
    need(type(report_year) is int and 1900 <= report_year <= 9998, 'explicit annual report year required')
    need(type(pages) in (list,tuple) and pages and all(type(p) is str for p in pages), 'ordered physical page text required')
    lines,context = prior.financial_context(pages)
    currency = reporting_currency(pages)
    income,imeta = table(lines,context,currency,'合并利润表','母公司利润表',report_year,True)
    balance,bmeta = table(lines,context,currency,'合并资产负债表','母公司资产负债表',report_year,False)
    fields = {
        'revenue':extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业收入\s*','revenue',report_year),
        'cost_of_sales':extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业成本\s*','cost_of_sales',report_year),
        'total_assets':extract_row(balance,bmeta,r'^资产总计\s*','total_assets',report_year)}
    years = (report_year,report_year-1) if bmeta['reported_comparative_balance_date'] == f'{report_year-1}-12-31' else (report_year,)
    return {f'{year}-12-31':{field:fields[field][f'{year}-12-31'] for field in original.FIELDS} for year in years}
