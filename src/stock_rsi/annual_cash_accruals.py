"""Original consolidated NI/CFO/asset cells, not a paper replication or score.

Chinese consolidated total NI/CFO can differ from US continuing-operations
measures. This source contract makes no cross-issuer/version admission claim.
"""
from copy import deepcopy
from datetime import date,datetime,time,timezone
import re
from zoneinfo import ZoneInfo
from stock_rsi import annual_operating as op
from stock_rsi.data import digest

grammar=op.grammar
need,aware,compact=op.need,op.aware,op.compact
OBSERVED,RECONSTRUCTED=op.OBSERVED,op.RECONSTRUCTED
CONTRACT='CN_CONSOLIDATED_TOTAL_NI_CFO_AND_SAME_EDITION_ASSETS_SOURCE_V1'
LABELS={'net_profit':r'^(?:[一二三四五六七八九十]+[、.]\s*)?净利润(?:（净亏损以[“"‘]?[-－][”"’]?号填列）)?\s*',
        'operating_cashflow':r'^经营活动产生的现金流量净额\s*','total_assets':r'^资产总计\s*'}
STATEMENTS={'income':('合并利润表','母公司利润表','net_profit',True),'cashflows':('合并现金流量表','母公司现金流量表','operating_cashflow',True),'balances':('合并资产负债表','母公司资产负债表','total_assets',False)}

def parse_report(pages,report_year,*,normative_basis=None):
    need(type(report_year) is int and 1900<=report_year<=9998,'explicit annual report year')
    need(type(pages) in (list,tuple) and pages and all(type(v) is str for v in pages),'ordered physical page text')
    lines,context=grammar.forms.prior.financial_context(pages);grammar.prior.reject_local_currency_conflicts(lines);currency=grammar.forms.reporting_currency(pages);result={}
    for kind,(heading,following,field,annual) in STATEMENTS.items():
        rows,meta=grammar.table(lines,context,currency,pages,normative_basis,heading,following,report_year,annual)
        if not annual:need(meta['reported_comparative_balance_date']==f'{report_year-1}-12-31','explicit same-edition previousDecember31assets')
        meta['parser_contract']=CONTRACT;cells=op.extract_signed_row(rows,meta,LABELS[field],field,report_year)
        result[kind]=cells if kind=='balances' else {period:{field:cell} for period,cell in cells.items()}
    validate_parsed(result,report_year);return result

def validate_parsed(parsed,year):
    need(type(parsed) is dict and set(parsed)==set(STATEMENTS),'exact three statement source contract');periods={f'{year}-12-31',f'{year-1}-12-31'}
    for kind,(heading,following,field,annual) in STATEMENTS.items():
        need(type(parsed[kind]) is dict and set(parsed[kind])==periods,'both explicit fiscal columns required');table_metadata=set()
        for period in periods:
            fields={'total_assets':parsed[kind][period]} if kind=='balances' else parsed[kind][period]
            need(type(fields) is dict and set(fields)=={field},'one exact consolidated source field')
            cell=fields[field];column=year-date.fromisoformat(period).year;suffix=f'{year}年度{year-1}年度' if annual else f'{year}年12月31日{year-1}年12月31日'
            need(cell['parser_contract']==CONTRACT and cell['statement']==heading and cell['fiscal_end']==period and type(cell['column_index']) is int and cell['column_index']==column and compact(cell['header_line']).endswith(suffix) and type(cell['header_page']) is int and type(cell['page']) is int and cell['page']>=cell['header_page']>0 and cell['row_text_sha256']==digest(cell['row_text']),'coherent physical statement/header/row/fiscal evidence')
            literals=op.row_values(cell['row_text'],LABELS[field],cell['header_line']);need(cell['literal']==literals[column],'literal occupies claimed fiscal column');op.validate_unit_evidence(cell,year);amount=op.amount_CNY(cell['literal'],cell['unit'])
            need(type(cell['value_CNY']) is str and cell['value_CNY']==format(amount,'f') and cell['multiplier_CNY']==str(grammar.original.CNY_UNITS[cell['unit']]) and amount.is_finite() and (field!='total_assets' or amount>0),'signed source money and positive assets must match units/literals')
            if not annual:need(cell['reported_comparative_balance_date']==f'{year-1}-12-31' and cell['comparative_date_is_unresolved'] is False,'explicit priorDecember31balance')
            table_metadata.add((cell['header_page'],cell['header_line'],cell['unit'],cell['unit_evidence_literal']))
        need(len(table_metadata)==1,'same table and units for both fiscal columns')

def metadata(document):
    year=document['effective_fiscal_year'];publication=date.fromisoformat(document['day']);observed=aware(document['captured_at_utc'])
    need(type(year) is int and 1900<=year<=9998 and publication.isoformat()==document['day'] and publication>date(year,12,31),'canonical annual period/publication')
    need(re.fullmatch(r'(SH|SZ)\d{6}',document['instrument']) and re.fullmatch(r'[a-f0-9]{64}',document['source_sha256']) and re.fullmatch(r'[0-9]+',document['announcement_id']),'canonical source identity')
    public=datetime.combine(publication,time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc);need(observed>=public,'publication before registered observation');return year,public,observed

def make_report(document,parsed):
    year,public,observed=metadata(document);validate_parsed(parsed,year)
    result={'contract':CONTRACT,'instrument':document['instrument'],'capture_key':document['capture_key'],'report_year':year,'publication_day':document['day'],'public_day_end_at':public.isoformat(),'observed_at':observed.isoformat(),'source_sha256':document['source_sha256'],'announcement_id':document['announcement_id'],'parsed':deepcopy(parsed),'historical_arrival_verified':False,'financial_version_history_complete':False,'financial_cross_issuer_comparability_verified':False,'investment_factor_admitted':False,'ratios_or_rankings_computed':False}
    result['record_id']=digest(result);return result

def visible_report(document,as_of,loader,mode):
    need(mode in (OBSERVED,RECONSTRUCTED),'explicit source visibility mode');clock=aware(as_of);_,public,observed=metadata(document)
    if clock<(max(public,observed) if mode==OBSERVED else public):return None
    report=loader();need(type(report) is dict and report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'}),'visible report digest required')
    need(make_report(document,report['parsed'])==report,'one coherent visible source edition');return report
