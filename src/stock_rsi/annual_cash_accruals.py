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

def context(pages,year):
    need(type(year) is int and 1900<=year<=9998,'explicit annual report year')
    need(type(pages) in (list,tuple) and pages and all(type(v) is str for v in pages),'ordered physical page text')
    lines,scope=grammar.forms.prior.financial_context(pages);grammar.prior.reject_local_currency_conflicts(lines)
    return lines,scope,grammar.forms.reporting_currency(pages)

def source_table(lines,scope,currency,pages,year,normative_basis,kind):
    heading,following,field,annual=STATEMENTS[kind]
    rows,meta=grammar.table(lines,scope,currency,pages,normative_basis,heading,following,year,annual);meta['parser_contract']=CONTRACT
    return {'lines':[[p,t] for p,t in rows],'metadata':meta}

def table_cells(table,year,kind,require_prior=True):
    heading,following,field,annual=STATEMENTS[kind];rows=table['lines'];meta=table['metadata'];headers=grammar.headers(rows,year,annual)
    first=headers[0];body_start=first['start_index']+len(first['literal'].splitlines())
    if not annual:
        dated=meta['reported_comparative_balance_date']==f'{year-1}-12-31'
        need(not require_prior or dated,'explicit same-edition previousDecember31assets')
        years=(year,year-1) if dated else (year,)
        cells=grammar.extract_row(rows[body_start:],meta,LABELS[field],field,year,years)
    else:cells=op.extract_signed_row(rows[body_start:],meta,LABELS[field],field,year)
    sample=next(iter(cells.values()));parts=sample['row_text'].splitlines();found=[]
    for start in range(body_start,len(rows)):
        block=rows[start:start+len(parts)]
        if len(block)==len(parts) and all(p==sample['page'] for p,_ in block) and [t for _,t in block]==parts:found.append(start)
    need(len(found)==1,'one physical source row position after fiscal header');start=found[0]
    on_page=[h for h in headers if h['page']==sample['page']]
    need(not on_page or start>=on_page[0]['start_index']+len(on_page[0]['literal'].splitlines()),'source row cannot precede its same-page fiscal header')
    preceding=max(h['start_index'] for h in headers if h['start_index']<start)
    for cell in cells.values():cell.update(row_source_start_index=start,row_source_end_index=start+len(parts),preceding_header_source_start_index=preceding)
    return cells

def parse_asset_cells(pages,year,*,normative_basis=None):
    lines,scope,currency=context(pages,year);table=source_table(lines,scope,currency,pages,year,normative_basis,'balances')
    return table_cells(table,year,'balances',require_prior=False)

def parse_report(pages,report_year,*,normative_basis=None):
    lines,scope,currency=context(pages,report_year);result={'tables':{}}
    for kind in STATEMENTS:
        table=source_table(lines,scope,currency,pages,report_year,normative_basis,kind);result['tables'][kind]=table;cells=table_cells(table,report_year,kind)
        result[kind]=cells if kind=='balances' else {period:{STATEMENTS[kind][2]:cell} for period,cell in cells.items()}
    validate_parsed(result,report_year);return result

def validate_parsed(parsed,year):
    need(type(parsed) is dict and set(parsed)=={*STATEMENTS,'tables'} and type(parsed['tables']) is dict and set(parsed['tables'])==set(STATEMENTS),'exact three statement source contract and table witnesses')
    for kind,(heading,following,field,annual) in STATEMENTS.items():
        table=parsed['tables'][kind];need(type(table) is dict and set(table)=={'lines','metadata'},'complete source table witness');rows=table['lines'];meta=table['metadata']
        need(type(rows) is list and rows and all(type(v) is list and len(v)==2 and type(v[0]) is int and v[0]>0 and type(v[1]) is str and v[1] and v[1]==v[1].strip() for v in rows) and [v[0] for v in rows]==sorted(v[0] for v in rows),'ordered physical source lines')
        scope=meta['financial_section_context'];evidence=meta['currency_scope_evidence'];declarations=scope['currency_declarations']
        if grammar.forms.explicit_local_unit(meta['unit_evidence_literal']) is not None:currency=[]
        else:
            need(evidence[:len(declarations)]==declarations,'scoped currency evidence prefix must agree');currency=evidence[len(declarations):]
        rebuilt=source_table(rows+[[rows[-1][0],following]],scope,currency,[],year,None,kind)
        need(rebuilt==table,'complete supported header/unit/location/statement provenance must match source witness')
        cells=table_cells(table,year,kind);expected=cells if kind=='balances' else {period:{field:cell} for period,cell in cells.items()}
        need(parsed[kind]==expected,'both fiscal cells must share the exact original row and coherent source provenance')
        for cell in cells.values():op.validate_unit_evidence(cell,year)

def verify_source_tables(parsed,pages,year,*,normative_basis=None):
    lines,scope,currency=context(pages,year)
    for kind in STATEMENTS:need(parsed['tables'][kind]==source_table(lines,scope,currency,pages,year,normative_basis,kind),'worker table witness differs from authenticated original pages')

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
