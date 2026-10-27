"""Bounded whitespace-only total-NI caption extension; immutable V1 preserved."""
from copy import deepcopy
import re
from stock_rsi import annual_cash_accruals as v1
from stock_rsi.data import digest

CONTRACT='CN_TOTAL_NI_CFO_SOURCE_V2_WRAPPED_CAPTION_ONLY'
MAX_ROW_LINES=12
OBSERVED,RECONSTRUCTED=v1.OBSERVED,v1.RECONSTRUCTED
metadata,aware,need,compact=v1.metadata,v1.aware,v1.need,v1.compact
STATEMENTS=v1.STATEMENTS
START=re.compile(r'^(?:[一二三四五六七八九十]+[、.]\s*)?净利润')
CAPTION=re.compile(r'^(?:[一二三四五六七八九十]+[、.])?净利润（净亏损以[“"‘]?[-－][”"’]?号填列）')

def source_table(*args,**kwargs):
    table=v1.source_table(*args,**kwargs);table['metadata']['parser_contract']=CONTRACT;return table

def net_profit_cells(table,year):
    need(table['metadata']['parser_contract']==CONTRACT,'registered wrapped caption table contract')
    try:return v1.table_cells(table,year,'income')
    except ValueError:pass
    rows=table['lines'];meta=table['metadata'];headers=v1.grammar.headers(rows,year,True);first=headers[0];body_start=first['start_index']+len(first['literal'].splitlines());found=[]
    for start in range(body_start,len(rows)):
        page,line=rows[start]
        if not START.match(line):continue
        parsed=None
        for width in range(1,MAX_ROW_LINES+1):
            block=rows[start:start+width]
            if len(block)!=width or any(p!=page for p,_ in block):break
            raw='\n'.join(t for _,t in block);close=raw.find('）')
            if close<0:continue
            end=close+1;label=''.join(c for c in raw[:end] if not c.isspace());match=CAPTION.fullmatch(label)
            if match is None:continue
            try:values=v1.op.row_values(raw,'^'+re.escape(raw[:end]),meta['header_line'])
            except ValueError:continue
            after=start+width;need(after==len(rows) or not re.fullmatch(r'(?:'+v1.grammar.original.MONEY+r'|[—–－-])(?:\s+(?:'+v1.grammar.original.MONEY+r'|[—–－-]))*',rows[after][1]),'extra monetary continuation unsupported')
            on_page=[h for h in headers if h['page']==page];need(not on_page or start>=on_page[0]['start_index']+len(on_page[0]['literal'].splitlines()),'source row cannot precede its same-page fiscal header')
            preceding=max(h['start_index'] for h in headers if h['start_index']<start);parsed={}
            for column,literal in enumerate(values):
                amount=v1.op.amount_CNY(literal,meta['unit']);need(amount.is_finite(),'finite signed total net profit required');period=f'{year-column}-12-31'
                parsed[period]={'value_CNY':format(amount,'f'),'literal':literal,'page':page,'row_text':raw,'row_text_sha256':digest(raw),'column_index':column,'fiscal_end':period,**meta,'row_source_start_index':start,'row_source_end_index':start+width,'preceding_header_source_start_index':preceding,'caption_end_offset':end,'normalized_caption':match.group(),'normalization_rule':'APPROVED_CAPTION_WHITESPACE_ONLY'}
            break
        need(parsed is not None,'bounded12same-page wrapped total-net-profit caption and unchanged two-cell tail required');found.append(parsed)
    need(len(found)==1,'unique wrapped consolidated total-net-profit row required');return found[0]

def table_cells(table,year,kind):return net_profit_cells(table,year) if kind=='income' else v1.table_cells(table,year,kind)
def contracts(parsed):
    need(type(parsed) is dict and set(parsed)=={*STATEMENTS,'tables'} and type(parsed['tables']) is dict and set(parsed['tables'])==set(STATEMENTS),'complete registered source table witnesses')
    return {t['metadata']['parser_contract'] for t in parsed['tables'].values()}

def parse_report(pages,year,*,normative_basis=None):
    try:return v1.parse_report(pages,year,normative_basis=normative_basis)
    except (ValueError,KeyError,ArithmeticError):pass
    lines,scope,currency=v1.context(pages,year);result={'tables':{}}
    for kind in STATEMENTS:
        table=source_table(lines,scope,currency,pages,year,normative_basis,kind);result['tables'][kind]=table;cells=table_cells(table,year,kind);result[kind]=cells if kind=='balances' else {period:{STATEMENTS[kind][2]:cell} for period,cell in cells.items()}
    validate_parsed(result,year);return result

def validate_parsed(parsed,year):
    kinds=contracts(parsed)
    if kinds=={v1.CONTRACT}:v1.validate_parsed(parsed,year);return
    need(kinds=={CONTRACT},'one registered source parser contract required')
    for kind,(_,following,field,_) in STATEMENTS.items():
        table=parsed['tables'][kind];need(type(table) is dict and set(table)=={'lines','metadata'},'complete source table witness');rows=table['lines'];meta=table['metadata']
        need(type(rows) is list and rows and all(type(v) is list and len(v)==2 and type(v[0]) is int and v[0]>0 and type(v[1]) is str and v[1] and v[1]==v[1].strip() for v in rows) and [v[0] for v in rows]==sorted(v[0] for v in rows),'ordered physical source lines')
        scope=meta['financial_section_context'];evidence=meta['currency_scope_evidence'];declarations=scope['currency_declarations']
        if v1.grammar.forms.explicit_local_unit(meta['unit_evidence_literal']) is not None:currency=[]
        else:need(evidence[:len(declarations)]==declarations,'scoped currency evidence prefix must agree');currency=evidence[len(declarations):]
        need(source_table(rows+[[rows[-1][0],following]],scope,currency,[],year,None,kind)==table,'complete supported fiscal/header/unit/source provenance required')
        cells=table_cells(table,year,kind);expected=cells if kind=='balances' else {period:{field:cell} for period,cell in cells.items()};need(parsed[kind]==expected,'both fiscal cells and raw caption offsets must match source witness')
        for cell in cells.values():v1.op.validate_unit_evidence(cell,year)

def make_report(document,parsed):
    if contracts(parsed)=={v1.CONTRACT}:return v1.make_report(document,parsed)
    year,public,observed=metadata(document);validate_parsed(parsed,year)
    result={'contract':CONTRACT,'instrument':document['instrument'],'capture_key':document['capture_key'],'report_year':year,'publication_day':document['day'],'public_day_end_at':public.isoformat(),'observed_at':observed.isoformat(),'source_sha256':document['source_sha256'],'announcement_id':document['announcement_id'],'parsed':deepcopy(parsed),'historical_arrival_verified':False,'financial_version_history_complete':False,'financial_cross_issuer_comparability_verified':False,'investment_factor_admitted':False,'ratios_or_rankings_computed':False,'row_format_extension_only':True};result['record_id']=digest(result);return result

def visible_report(document,as_of,loader,mode):
    need(mode in (OBSERVED,RECONSTRUCTED),'explicit source visibility mode');clock=aware(as_of);_,public,observed=metadata(document)
    if clock<(max(public,observed) if mode==OBSERVED else public):return None
    report=loader();need(type(report) is dict and report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'}),'visible report digest required');need(make_report(document,report['parsed'])==report,'one coherent visible registered source edition');return report

def verify_source_tables(parsed,pages,year,*,normative_basis=None):
    if contracts(parsed)=={v1.CONTRACT}:return v1.verify_source_tables(parsed,pages,year,normative_basis=normative_basis)
    need(contracts(parsed)=={CONTRACT},'one registered source parser contract required');lines,scope,currency=v1.context(pages,year)
    for kind in STATEMENTS:need(parsed['tables'][kind]==source_table(lines,scope,currency,pages,year,normative_basis,kind),'worker wrapped table witness differs from authenticated original pages')
