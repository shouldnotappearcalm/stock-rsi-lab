"""Original five-column classification tables with explicit vintage/availability.
Merged-cell context never supplies a current business-sector certification.
"""
import copy
from datetime import datetime,timezone
import math
import re
from stock_rsi.data import digest

CONTRACT='ARCHIVED2021Q3_ORIGINAL_GEOMETRY_INDUSTRY_CATALOG_V1'
PERIOD='2021Q3'
OBSERVED='OBSERVED'
ARCHIVE_RECONSTRUCTED='ARCHIVE_PUBLIC_CONTENT_RECONSTRUCTION'
HEADER=('门类名称及代码','行业大类代码','行业大类名称','上市公司代码','上市公司简称')
FIELDS=('sector','industry_code','industry_name','stock_code','stock_name')


def need(value,why):
    if not value:raise ValueError(why)
def compact(text):return re.sub(r'\s+','',text)
def aware(value):
    need(type(value) is str,'timestamp string required');result=datetime.fromisoformat(value)
    need(result.tzinfo is not None and result.utcoffset() is not None,'timezone-aware timestamp required')
    return result.astimezone(timezone.utc)
def number(value):return type(value) in (float,int) and math.isfinite(value)


def box(value,width,height):
    need(type(value) in (list,tuple) and len(value)==4 and all(number(x) for x in value),'finite four-coordinate source cell required')
    x0,y0,x1,y1=value
    need(0<=x0<x1<=width+.1 and 0<=y0<y1<=height+.1,'source cell inside original physical page')
    return list(value)


def point(packet,table,row,column):
    cell=row['cells'][column];literal=cell['literal']
    need(type(literal) is str and literal.strip(),'literal source cell required')
    return {'physical_page':packet['physical_page'],'table_index':table['table_index'],'row_index':row['row_index'],
            'column_index':column,'bbox':box(cell['bbox'],packet['width'],packet['height']),'literal':literal}


def parse_catalog(packets,*,source_sha256,public_by,observed_at,expected_pages):
    need(re.fullmatch('[a-f0-9]{64}',source_sha256 or '') is not None,'original PDF hash required')
    public,observed=aware(public_by),aware(observed_at);need(public<=observed,'source capture cannot precede archival public-content proof')
    need(type(expected_pages) is int and expected_pages>0 and type(packets) is list and len(packets)==expected_pages
         and [p['physical_page'] for p in packets]==list(range(1,expected_pages+1)),'complete unique consecutive original pages required')
    major,minor_code,minor_name=None,None,None
    major_names,minor_names,records,seen={},{},[],set()
    for packet in packets:
        need(packet['source_sha256']==source_sha256,'one original PDF only; no cross-document context carry')
        width,height=packet['width'],packet['height']
        need(number(width) and number(height) and width>0 and height>0,'original physical dimensions required')
        need(type(packet['tables']) is list and len(packet['tables'])==1,'exactly one source classification table per page required')
        table=packet['tables'][0];rows=table['rows'];need(table['table_index']==0 and len(rows)>=2,'header and source rows required')
        box(table['bbox'],width,height)
        need([r['row_index'] for r in rows]==list(range(len(rows))) and all(len(r['cells'])==5 for r in rows),'complete five-column source row order required')
        header=rows[0]['cells'];need(all(type(c['literal']) is str for c in header) and tuple(compact(c['literal']) for c in header)==HEADER,'exact original five-column header required')
        columns=[box(c['bbox'],width,height) for c in header]
        need(all(abs(columns[i][2]-columns[i+1][0])<=.5 for i in range(4)),'contiguous original column geometry required')
        for row in rows[1:]:
            cells=row['cells'];page=packet['physical_page']
            for j,cell in enumerate(cells):
                need(cell['literal'] is None or type(cell['literal']) is str,'source cell literals may not be coerced from numbers')
                if cell['bbox'] is not None:
                    b=box(cell['bbox'],width,height)
                    need(abs(b[0]-columns[j][0])<=.5 and abs(b[2]-columns[j][2])<=.5,'source cell must stay in its original column')
            code_source,name_source=point(packet,table,row,3),point(packet,table,row,4)
            code,name=compact(code_source['literal']),compact(name_source['literal'])
            need(re.fullmatch('[0-9]{6}',code) is not None and code not in seen and name,'one literal unique six-digit stock code and name required')
            need(abs(code_source['bbox'][1]-name_source['bbox'][1])<=.5 and abs(code_source['bbox'][3]-name_source['bbox'][3])<=.5,'stock identity cells must share the original row')
            y=(code_source['bbox'][1]+code_source['bbox'][3])/2
            def inherit(state,column):
                need(state is not None,'missing original classification context')
                # An explicitly empty new cell inside a page is not a merge of
                # the previously labelled cell. Only a page-start continuation
                # may carry an empty repeated-page cell from an earlier page.
                if cells[column]['bbox'] is not None:
                    need(row['row_index']==1 and state['source']['physical_page']<page,'ambiguous empty classification cell inside source page')
                if state['source']['physical_page']==page:
                    b=state['source']['bbox'];need(b[1]-.5<=y<=b[3]+.5,'inherited merged label must cover the stock row')
                return state
            if cells[0]['literal'] is not None and cells[0]['literal'].strip():
                origin=point(packet,table,row,0);text=compact(origin['literal'])
                match=re.fullmatch(r'(.{1,64}?)(?:\(([A-Z])\)|（([A-Z])）)',text)
                need(match is not None,'explicit original sector name and parenthesized letter required')
                sector_name,sector_code=match.group(1),match.group(2) or match.group(3)
                need((sector_code=='J')==(sector_name=='金融业'),'financial sector code/name mismatch')
                need(sector_code not in major_names or major_names[sector_code]==sector_name,'conflicting source name for sector code')
                if major is None or major['code']!=sector_code:minor_code,minor_name=None,None
                major_names[sector_code]=sector_name;major={'code':sector_code,'name':sector_name,'source':origin}
            else:major=inherit(major,0)
            supplied=[cells[j]['literal'] is not None and bool(cells[j]['literal'].strip()) for j in (1,2)]
            need(supplied[0]==supplied[1],'minor code/name must change together')
            if supplied[0]:
                code_origin,name_origin=point(packet,table,row,1),point(packet,table,row,2)
                industry_code,industry_name=compact(code_origin['literal']),compact(name_origin['literal'])
                need(re.fullmatch('[0-9]{2}',industry_code) is not None and industry_name,'literal two-digit industry code and name required')
                key=(major['code'],industry_code)
                need(key not in minor_names or minor_names[key]==industry_name,'conflicting industry name within source sector')
                minor_names[key]=industry_name;minor_code={'value':industry_code,'source':code_origin};minor_name={'value':industry_name,'source':name_origin}
            else:minor_code,minor_name=inherit(minor_code,1),inherit(minor_name,2)
            sources={'sector':major['source'],'industry_code':minor_code['source'],'industry_name':minor_name['source'],
                     'stock_code':code_source,'stock_name':name_source}
            inherited=[field for field in FIELDS if sources[field]['physical_page']!=page or sources[field]['row_index']!=row['row_index']]
            record={'classification_period':PERIOD,'source_sha256':source_sha256,'stock_code':code,'stock_name':name,
                'sector_code':major['code'],'sector_name':major['name'],'industry_code':minor_code['value'],'industry_name':minor_name['value'],
                'physical_page':page,'table_index':0,'row_index':row['row_index'],'field_sources':copy.deepcopy(sources),
                'inherited_fields':inherited,'classification_context_carried_across_pages':any(e['physical_page']<page for e in sources.values()),
                'source_vintage_not_actual_current_business':True}
            record['record_id']=digest(record);records.append(record);seen.add(code)
    return {'contract':CONTRACT,'classification_period':PERIOD,'source_sha256':source_sha256,
        'public_content_available_by':public.isoformat(),'observed_at':observed.isoformat(),'physical_pages':expected_pages,
        'record_count':len(records),'records':records,'current_business_identity_verified':False,
        'classification_history_complete':False,'investment_factor_admitted':False}


def snapshot_catalog(catalog,cohort,as_of,*,mode=OBSERVED):
    need(mode in (OBSERVED,ARCHIVE_RECONSTRUCTED),'explicit observed or archive reconstruction mode required')
    clock=aware(as_of);public,observed=aware(catalog['public_content_available_by']),aware(catalog['observed_at'])
    need(public<=observed,'invalid source availability chronology')
    need(type(cohort) in (list,tuple) and len(set(cohort))==len(cohort)
         and all(type(c) is str and re.fullmatch(r'(SH|SZ)[0-9]{6}',c) for c in cohort),'unique canonical cohort instruments required')
    visible=clock>=(max(public,observed) if mode==OBSERVED else public)
    base={'as_of':clock.isoformat(),'visibility_mode':mode,'public_content_available_by':public.isoformat(),
        'classification_visible':visible,'current_business_identity_verified':False,'classification_history_complete':False,
        'historical_research_system_arrival_verified':False,'investment_factor_admitted':False}
    if not visible:
        # Do not iterate/hash/validate any future classification payload.
        return {**base,'classifications':[{'instrument':c,'status':'NOT_AVAILABLE_AT_CLOCK'} for c in sorted(cohort)]}
    need(catalog['contract']==CONTRACT and catalog['classification_period']==PERIOD and type(catalog['records']) is list
         and len(catalog['records'])==catalog['record_count'],'visible catalog contract/records required')
    indexed={}
    for r in catalog['records']:
        need(r['record_id']==digest({k:v for k,v in r.items() if k!='record_id'}) and r['source_sha256']==catalog['source_sha256']
             and r['classification_period']==PERIOD and r['stock_code'] not in indexed,'visible source classification record changed or duplicated')
        indexed[r['stock_code']]=r
    rows=[]
    for code in sorted(cohort):
        source=indexed.get(code[2:])
        if source is None:rows.append({'instrument':code,'status':'NOT_IN_SOURCE_VINTAGE'});continue
        rows.append({'instrument':code,'status':'FINANCIAL_IN_SOURCE_VINTAGE' if source['sector_code']=='J' else 'NONFINANCIAL_IN_SOURCE_VINTAGE',
            'classification_period':PERIOD,'record_id':source['record_id'],'source_record':copy.deepcopy(source),
            'vintage_carryforward_is_not_current_business_verification':True})
    return {**base,'classifications':rows}
