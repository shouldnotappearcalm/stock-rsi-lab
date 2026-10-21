"""Bounded original-header formats; an undated opening column stays undated.
V6 successes return unchanged. No investment, currency or visibility policy.
"""
import re
from stock_rsi import annual_profitability_v6 as prior

forms=prior.prior
original,need,compact=forms.original,forms.need,forms.compact
CONTRACT='CONSOLIDATED_THREE_FIELD_DATE_ANCHORED_CURRENT_AND_HEADERS_V7'
document_identity=prior.document_identity
CAS19_REFERENCE=prior.CAS19_REFERENCE
CHINESE=forms.v2.CHINESE
NOTE_HEADER=rf'(?:附注(?:[{CHINESE}]{{1,4}}|（[{CHINESE}]{{1,4}}）|\([{CHINESE}]{{1,4}}\))?)?'
PREFIX=re.compile(r'^项目'+NOTE_HEADER)
MAX_HEADER_LINES=20


def headers(selected,year,income):
    suffixes=({f'{year}年度{year-1}年度':('EXPLICIT_TWO_FISCAL_COLUMNS',None)} if income else {
        f'{year}年12月31日{year-1}年12月31日':('EXPLICIT_TWO_FISCAL_COLUMNS',f'{year-1}-12-31'),
        f'{year}年12月31日{year}年1月1日':('EXPLICIT_TWO_FISCAL_COLUMNS',f'{year}-01-01'),
        '期末余额期初余额':('GENERIC_CURRENT_AND_UNDATED_OPENING',None)})
    found=[]
    for start,(page,line) in enumerate(selected):
        if not compact(line).startswith('项目'):continue
        candidates=[]
        for width in range(1,MAX_HEADER_LINES+1):
            block=selected[start:start+width]
            if len(block)!=width or any(p!=page for p,_ in block):break
            literal='\n'.join(t for _,t in block);clean=compact(literal);prefix=PREFIX.match(clean)
            if prefix is None:continue
            suffix=clean[prefix.end():]
            if suffix not in suffixes:continue
            after=start+width
            need(after==len(selected) or not re.match(
                r'^(?:\d{4}|调整|重述|[（(](?:经)?重述|期末余额|期初余额|年初余额|上年年末|本期发生额|上期发生额)',
                compact(selected[after][1])),'extra fiscal/header column unsupported')
            kind,comparison=suffixes[suffix]
            candidates.append({'page':page,'literal':literal,'kind':kind,'comparison':comparison,
                               'start_index':start,'normalized':clean})
            break
        need(len(candidates)==1,'one exact bounded source header at each project-column heading required')
        found.extend(candidates)
    need(found and found[0]['start_index']<32 and len(found)<=6,'bounded primary fiscal header required')
    need(len({h['page'] for h in found})==len(found)
         and all(h['normalized']==found[0]['normalized'] for h in found),'only identical later-page fiscal header continuations supported')
    return found


def current_date_anchor(selected,first,year):
    found=[];page=first['page']
    for start in range(first['start_index']):
        for width in range(1,8):
            block=selected[start:start+width]
            if start+width>first['start_index'] or len(block)!=width or any(p!=page for p,_ in block):break
            literal='\n'.join(t for _,t in block)
            if compact(literal)==f'{year}年12月31日':
                found.append({'page':page,'literal':literal,'date':f'{year}-12-31',
                              'scope':'SAME_PAGE_STATEMENT_DATE_BEFORE_GENERIC_BALANCE_HEADER'})
    need(len(found)==1,'generic balance needs one explicit same-page annual year-end date before its header')
    return found[0]


def table(lines,context,currency,pages,normative_basis,heading,following,year,income):
    starts=[i for i,(_,t) in enumerate(lines) if forms.v2.title(t)==heading]
    ends=[i for i,(_,t) in enumerate(lines) if forms.v2.title(t)==following]
    need(len(starts)==len(ends)==1 and starts[0]<ends[0],'unique scoped consolidated/parent table boundaries required')
    selected=lines[starts[0]:ends[0]]
    need(selected[-1][0]-selected[0][0]<=5,'bounded contiguous annual table required')
    units=[]
    for page,line in selected[:12]:
        explicit=forms.explicit_local_unit(line);bare=re.fullmatch(r'单位[：:](元|万元)',compact(line))
        if explicit:units.append((explicit,page,line,[]))
        elif bare:
            declarations=context['currency_declarations']+currency
            if not declarations:
                need(year>=2007,'regulatory inference requires a full fiscal year after the2006 publisher date')
                currency.extend(prior.cas_currency_evidence(pages,lines,context,normative_basis))
                declarations=context['currency_declarations']+currency
            need(declarations and all(d.get('unit',bare.group(1))==bare.group(1) for d in declarations),
                 'bare unit requires matching explicit or registered regulatory currency evidence')
            units.append((bare.group(1),page,line,declarations))
    need(len(units)==1,'one explicit local monetary unit required')
    found=headers(selected,year,income);first=found[0]
    anchor=current_date_anchor(selected,first,year) if first['kind']=='GENERIC_CURRENT_AND_UNDATED_OPENING' else None
    unit,page,literal,evidence=units[0]
    metadata={'statement':heading,'header_page':first['page'],'header_line':first['literal'],
        'header_occurrences':[{'page':h['page'],'literal':h['literal']} for h in found],
        'unit':unit,'multiplier_CNY':str(original.CNY_UNITS[unit]),'unit_evidence_page':page,'unit_evidence_literal':literal,
        'currency_scope_evidence':evidence,'financial_section_context':context,'parser_contract':CONTRACT,
        'row_text_representation':'STRIPPED_NONEMPTY_SAME_PAGE_SOURCE_LINES'}
    if not income:
        metadata.update(reported_comparative_balance_date=first['comparison'],
            balance_header_semantics=first['kind'],comparative_date_is_unresolved=anchor is not None,
            balance_current_date_anchor=anchor,current_column_date_is_inferred_from_explicit_statement_date=anchor is not None)
    return selected,metadata


def extract_row(lines,metadata,label,field,year,admitted_years):
    found=[]
    for start,(page,line) in enumerate(lines):
        match=re.match(label,line)
        if match is None:continue
        values=None
        for width in range(1,5):
            block=lines[start:start+width]
            if len(block)!=width or any(p!=page for p,_ in block):break
            text='\n'.join(t for _,t in block);tail=text[match.end():]
            old=forms.v2.VALUES.fullmatch(tail);alias=None if old else forms.ALIAS_VALUES.fullmatch(tail)
            if alias:
                need('附注' in compact(metadata['header_line']),'note alias needs an explicit note header')
                values=alias.groups()[1:]
            elif old:values=old.groups()
            if values:
                after=start+width
                need(after==len(lines) or not re.fullmatch(original.MONEY,lines[after][1]),'extra monetary continuation cell unsupported')
                found.append((page,text,values));break
        need(values is not None,'exact two monetary cells in bounded same-page row block required: '+field)
    need(len(found)==1,'one literal consolidated row required: '+field)
    page,text,values=found[0]
    amounts=[original.amount_CNY(v,metadata['unit']) for v in values]
    need(all(v.is_finite() and (v>0 if field=='total_assets' else v>=0) for v in amounts),'valid annual amount required')
    # Never assign a fiscal date to the undated opening balance column.
    return {f'{y}-12-31':{'value_CNY':format(amounts[year-y],'f'),'literal':values[year-y],
        'page':page,'row_text':text,'row_text_sha256':original.digest(text),'column_index':year-y,
        'fiscal_end':f'{y}-12-31',**metadata} for y in admitted_years}


def parse_consolidated_tables(pages,report_year,*,normative_basis=None):
    try:return prior.parse_consolidated_tables(pages,report_year,normative_basis=normative_basis)
    except ValueError:pass
    need(type(report_year) is int and 1900<=report_year<=9998,'explicit annual report year required')
    need(type(pages) in (list,tuple) and pages and all(type(p) is str for p in pages),'ordered physical page text required')
    lines,context=forms.prior.financial_context(pages)
    prior.reject_local_currency_conflicts(lines)
    currency=forms.reporting_currency(pages)
    income,imeta=table(lines,context,currency,pages,normative_basis,'合并利润表','母公司利润表',report_year,True)
    balance,bmeta=table(lines,context,currency,pages,normative_basis,'合并资产负债表','母公司资产负债表',report_year,False)
    years=(report_year,report_year-1) if bmeta['reported_comparative_balance_date']==f'{report_year-1}-12-31' else (report_year,)
    fields={
        'revenue':extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业收入\s*','revenue',report_year,years),
        'cost_of_sales':extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业成本\s*','cost_of_sales',report_year,years),
        'total_assets':extract_row(balance,bmeta,r'^资产总计\s*','total_assets',report_year,years)}
    return {f'{y}-12-31':{f:fields[f][f'{y}-12-31'] for f in original.FIELDS} for y in years}
