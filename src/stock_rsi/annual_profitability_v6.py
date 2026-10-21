"""Explicitly labelled CAS19 currency inference; V1-V5 successes stay verbatim.
No investment rule, currency conversion, source replacement or visibility change.
"""
import re
from stock_rsi import annual_profitability_v5 as prior

original, need, compact = prior.original, prior.need, prior.compact
CONTRACT = 'CONSOLIDATED_THREE_FIELD_EXPLICIT_CAS19_BASIS_V6'
document_identity = prior.document_identity
CAS19_REFERENCE = {
    'standard':'CAS19_ART4','publisher':'MINISTRY_OF_FINANCE_CHINA',
    'official_url':'https://kjs.mof.gov.cn/zt/kjzzss/kuaijizhunzeshishi/200806/t20080618_46229.htm',
    'publisher_displayed_day':'2006-03-09',
    'archived_body_sha256':'a31fbfe26c8783fe1657b5730db90cf693bdb7d0dadd5e6858e2a998cfe46bfe',
    'archived_text_sha256':'75371ec30fbccc52cab3c2966815b033498850434772642974b49ad36534a74a',
    'normative_phrase':'编报的财务报表应当折算为人民币'}
HEADING = '遵循企业会计准则的声明'
CLAIM = re.compile(r'^(?:本(?:公司|集团)(?:所)?(?:编制的|的)?|公司(?:所)?编制的|本)财务报表符合(?:财政部颁布的)?企业会计准则的(?:要求|规定)[，,。]')


def cas_currency_evidence(pages, lines, context, normative_basis):
    need(normative_basis == CAS19_REFERENCE,'archived pre2024 CAS19 reference required for regulatory currency inference')
    if context['kind'] == 'PRIMARY_FINANCIAL_STATEMENTS_SECTION':
        anchor_page,anchor_literal = context['end_page_exclusive'],context['end_literal']
        limit = 20
    else:
        anchors = [(page,line) for page,line in lines if prior.v2.title(line) == '母公司利润表']
        need(len(anchors) == 1,'unique parent-income anchor for post-statement CAS evidence')
        anchor_page,anchor_literal = anchors[0];limit = 30
    found = []
    for page in range(anchor_page,min(len(pages),anchor_page+limit)+1):
        raw = [t.strip() for t in pages[page-1].splitlines() if t.strip()]
        for j,line in enumerate(raw):
            clean = compact(line)
            direct = re.fullmatch(r'(?:\d{1,2}[、.．]|[一二三四五六七八九十]+[、.．])?'+HEADING,clean)
            split = clean == '、'+HEADING and j>0 and re.fullmatch(r'\d{1,2}',compact(raw[j-1]))
            if not (direct or split):continue
            if page == anchor_page and anchor_literal not in '\n'.join(raw[:j]):continue
            quoted = None
            for width in range(1,5):
                block = raw[j+1:j+1+width]
                if len(block) != width:break
                literal = '\n'.join(block)
                if '。' not in literal:continue
                plain = compact(literal)
                if CLAIM.match(plain):
                    nearby = compact('\n'.join(raw[j+1:j+7]))
                    need(not re.search(r'不符合|未遵循|不完全符合|IFRS|香港财务报告准则|国际财务报告准则|但是|但[，,]',nearby,re.I),
                         'conflicting/qualified accounting-basis declaration unsupported')
                    quoted = literal
                break
            if quoted is None:continue
            found.append({'scope':'INFERRED_FROM_EXPLICIT_CAS_COMPLIANCE_AND_CAS19_ART4',
                'currency':'CNY','currency_is_regulatory_inference_not_literal_quote':True,
                'page':page,'literal':quoted,'heading_literal':'\n'.join(raw[j-1:j+1]) if split else line,
                'statement_scope_anchor':{'page':anchor_page,'literal':anchor_literal,'maximum_following_pages':limit},
                'normative_reference':dict(normative_basis)})
    need(len(found) == 1,'one scoped explicit Chinese-CAS financial-statement compliance declaration required')
    return found


def reject_local_currency_conflicts(lines):
    for heading,following in (('合并资产负债表','母公司资产负债表'),('合并利润表','母公司利润表')):
        starts = [i for i,(_,line) in enumerate(lines) if prior.v2.title(line) == heading]
        ends = [i for i,(_,line) in enumerate(lines) if prior.v2.title(line) == following]
        need(len(starts) == len(ends) == 1 and starts[0] < ends[0],'unique scoped consolidated/parent table boundaries required')
        for _,line in lines[starts[0]:min(ends[0],starts[0]+12)]:
            normalized = compact(line).replace('：',':')
            if '币种:' in normalized:
                declared = normalized.split('币种:',1)[1].split('单位:',1)[0]
                need(declared == '人民币','conflicting explicit primary table currency')
            need(not re.search(r'单位[：:](?:美元|港币|欧元|日元|USD|HKD|EUR|JPY)',compact(line),re.I),
                 'explicit non-CNY primary table unit unsupported')


def parse_consolidated_tables(pages, report_year, *, normative_basis=None):
    try:return prior.parse_consolidated_tables(pages,report_year)
    except ValueError:pass
    need(type(report_year) is int and 1900 <= report_year <= 9998,'explicit annual report year required')
    need(type(pages) in (list,tuple) and pages and all(type(p) is str for p in pages),'ordered physical page text required')
    lines,context = prior.prior.financial_context(pages)
    reject_local_currency_conflicts(lines)
    currency = prior.reporting_currency(pages)  # explicit foreign reporting currency still fails
    if not currency and not context['currency_declarations']:
        need(report_year >= 2007,'regulatory inference requires a full fiscal year after the2006 publisher date')
        currency = cas_currency_evidence(pages,lines,context,normative_basis)
    income,imeta = prior.table(lines,context,currency,'合并利润表','母公司利润表',report_year,True)
    balance,bmeta = prior.table(lines,context,currency,'合并资产负债表','母公司资产负债表',report_year,False)
    for meta in (imeta,bmeta):meta['parser_contract'] = CONTRACT
    fields = {
        'revenue':prior.extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业收入\s*','revenue',report_year),
        'cost_of_sales':prior.extract_row(income,imeta,r'^(?:其中[：:]\s*)?营业成本\s*','cost_of_sales',report_year),
        'total_assets':prior.extract_row(balance,bmeta,r'^资产总计\s*','total_assets',report_year)}
    years = (report_year,report_year-1) if bmeta['reported_comparative_balance_date'] == f'{report_year-1}-12-31' else (report_year,)
    return {f'{year}-12-31':{field:fields[field][f'{year}-12-31'] for field in original.FIELDS} for year in years}
