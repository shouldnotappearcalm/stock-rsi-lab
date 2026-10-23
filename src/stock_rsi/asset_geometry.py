"""Bounded original-word year/adjustment mapping, never a trading signal."""
import copy
from datetime import date
from decimal import Decimal,localcontext
import math
import re

from stock_rsi import annual_operating as op
from stock_rsi.data import digest

CONTRACT='CN_ANNUAL_SUMMARY_PRIOR_YEAR_END_ASSET_WORDS_V1'
MONEY=re.compile(r'(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}')
YEAR=re.compile(r'(20\d\d)年末')
MAX_CENTER_DISTANCE=12.0
MAX_HEADER_HEIGHT=24.0
MAX_TABLE_EDGE_DISTANCE=2.0


def basis():
    return {'standard':'CSRC_ANNUAL_FORMAT_2021_ART10_19_20',
            'body_sha256':'b727419bdab8b137224cea1c9c8b7d20e8a8f1e3714c6ef2e3a6242cd4767615',
            'effective_from':'2021-06-28','effective_before':'2025-07-01',
            'currency_default':'CNY_UNLESS_OTHERWISE_SPECIFIED','consolidated_scope':'REGULATORY_INFERENCE_NOT_ISSUER_QUOTE'}


NORMATIVE_BASIS=basis()
need,compact=op.need,op.compact


def center(word):return (word['x0']+word['x1'])/2

def position(word):return word['page'],word['top'],word['x0']


def box(value,width,height):
    need(type(value) in (list,tuple) and len(value)==4,'four original coordinates required')
    need(all(type(v) in (int,float) and math.isfinite(v) for v in value),'finite numeric original coordinates')
    x0,top,x1,bottom=map(float,value)
    need(0<=x0<x1<=width and 0<=top<bottom<=height,'original box must lie within its physical page')
    return [x0,top,x1,bottom]


def canonical_pages(pages,source_sha256):
    need(type(pages) in (list,tuple) and pages,'ordered original geometry pages')
    result={}
    for p in pages:
        number=p['physical_page'];width,height=p['width'],p['height']
        need(type(number) is int and number>0 and number not in result,'unique physical pages')
        need(type(width) in (int,float) and type(height) in (int,float) and math.isfinite(width) and math.isfinite(height)
             and width>0 and height>0 and p['source_sha256']==source_sha256,'one original PDF and finite page dimensions')
        words=[];seen=set();tables=[]
        for w in p['words']:
            coords=box([w['x0'],w['top'],w['x1'],w['bottom']],width,height)
            need(type(w['text']) is str and compact(w['text']),'nonempty original word')
            token=tuple(coords);need(token not in seen,'ambiguous duplicate original word box');seen.add(token)
            words.append(dict(page=number,text=w['text'],x0=coords[0],top=coords[1],x1=coords[2],bottom=coords[3]))
        for t in p['tables']:
            bounds=box(t['bbox'],width,height);need(bounds not in tables,'duplicate original table scope');tables.append(bounds)
        result[number]={'width':width,'height':height,'words':sorted(words,key=position),'tables':sorted(tables)}
    return result


def inside(word,bounds):
    x0,top,x1,bottom=bounds
    return x0-1<=word['x0'] and word['x1']<=x1+1 and top-1<=word['top'] and word['bottom']<=bottom+1


def band(words,label):
    return sorted((w for w in words if w['bottom']>=label['top']-1 and w['top']<=label['bottom']+1),key=lambda w:w['x0'])


def normalized(literal,unit):
    with localcontext() as context:
        context.prec=60;value=Decimal(literal.replace(',',''))*(1 if unit=='元' else 10000)
    need(value.is_finite() and value>0,'positive finite asset amount')
    return format(value,'f')


def parse_summary_assets(pages,report_year,publication_day,source_sha256,primary,*,normative_basis):
    need(normative_basis==basis(),'bound original regulatory currency/scope basis required')
    need(type(report_year) is int and 2022<=report_year<=2024,'supported historical annual source year')
    public=date.fromisoformat(publication_day)
    need(public.isoformat()==publication_day and date(report_year,12,31)<public and '2021-06-28'<=publication_day<'2025-07-01',
         'applicable original regulatory publication version required')
    need(type(source_sha256) is str and re.fullmatch('[a-f0-9]{64}',source_sha256)
         and primary['source_sha256']==source_sha256 and primary['report_year']==report_year,'same original source and fiscal year')
    canonical=canonical_pages(pages,source_sha256);all_words=[w for p in canonical.values() for w in p['words']]
    labels=[w for w in all_words if re.fullmatch(r'总资产[（(].+[）)]',compact(w['text']))]
    need(len(labels)==1,'one literal main-accounting total-assets row')
    label=labels[0];unit_match=re.fullmatch(r'总资产[（(](元|万元)[）)]',compact(label['text']))
    need(unit_match is not None,'explicit supported monetary asset-row unit required');unit=unit_match.group(1)
    page=canonical[label['page']];tables=[t for t in page['tables'] if inside(label,t)]
    need(len(tables)==1,'unique original summary table scope');table=tables[0]
    governed=[w for w in page['words'] if inside(w,table)]
    header_words=[w for w in governed if w['bottom']<=label['top']+1]
    header_tables=[{'page':label['page'],'bbox':table}]
    previous=canonical.get(label['page']-1)
    if previous:
        possible=[t for t in previous['tables'] if abs(t[0]-table[0])<=MAX_TABLE_EDGE_DISTANCE and abs(t[2]-table[2])<=MAX_TABLE_EDGE_DISTANCE
                  and any(YEAR.fullmatch(compact(w['text'])) and inside(w,t) for w in previous['words'])]
        for t in possible:
            need(abs(previous['width']-page['width'])<=1,'cross-page source width changed')
            previous_words=[w for w in previous['words'] if inside(w,t)]
            governed+=previous_words;header_words+=previous_words;header_tables.append({'page':label['page']-1,'bbox':t})
    need(not any(re.search(r'美元|港币|港元|日元|欧元|\b(?:USD|HKD|EUR)\b',compact(w['text']),re.I) for w in governed),
         'foreign-currency summary context cannot use CNY default')
    anchors={}
    for w in header_words:
        match=YEAR.fullmatch(compact(w['text']))
        if match:
            year=int(match.group(1));need(year not in anchors,'unique original year-end parent header');anchors[year]=w
    need({report_year,report_year-1}<=set(anchors)<=set(range(report_year-2,report_year+1)),'current/prior original year-end labels required')
    need(len({w['page'] for w in anchors.values()})==1 and max(w['top'] for w in anchors.values())-min(w['top'] for w in anchors.values())<=MAX_HEADER_HEIGHT,
         'one bounded physical year-end header group')
    need([y for y in sorted(anchors,key=lambda y:center(anchors[y]))]==sorted(anchors,reverse=True),'source year-end columns ordered current to prior')
    first=min(position(w) for w in anchors.values())
    adjustments=[w for w in header_words if compact(w['text']) in ('调整前','调整后') and position(w)>=first]
    row=band([w for w in page['words'] if inside(w,table)],label);amounts=[w for w in row if MONEY.fullmatch(compact(w['text']))]
    by_year={y:[] for y in anchors}
    for amount in amounts:
        distances=sorted((abs(center(amount)-center(anchor)),year) for year,anchor in anchors.items())
        need(len(distances)==1 or distances[1][0]-distances[0][0]>1,'ambiguous monetary year geometry')
        by_year[distances[0][1]].append(amount)
    columns={}
    for year in sorted(anchors,reverse=True):
        money=sorted(by_year[year],key=center);need(len(money) in (1,2),'one reported or two adjustment asset columns per year')
        children=[]
        if len(money)==1:
            need(abs(center(money[0])-center(anchors[year]))<=MAX_CENTER_DISTANCE,'singleton source amount aligned with its year')
            need(not any(abs(center(h)-center(money[0]))<=MAX_CENTER_DISTANCE for h in adjustments),'singleton cannot hide an adjustment column')
            children=[None]
        else:
            for amount in money:
                matches=[h for h in adjustments if abs(center(h)-center(amount))<=MAX_CENTER_DISTANCE]
                need(len(matches)==1,'one original adjustment child for each amount');children.append(matches[0])
            need([compact(h['text']) for h in children]==['调整前','调整后']
                 and abs(sum(center(h) for h in children)/2-center(anchors[year]))<=MAX_CENTER_DISTANCE,
                 'ordered before/after children governed by this year-end parent')
        columns[str(year)]=[{'fiscal_end':f'{year}-12-31','literal':compact(w['text']),'unit':unit,'value_CNY':normalized(compact(w['text']),unit),
            'adjustment':('AS_REPORTED' if child is None else 'BEFORE_ADJUSTMENT' if compact(child['text'])=='调整前' else 'AFTER_ADJUSTMENT'),
            'amount_word':copy.deepcopy(w),'year_word':copy.deepcopy(anchors[year]),'adjustment_word':copy.deepcopy(child)} for w,child in zip(money,children)]
    need(len(columns[str(report_year)])==1,'single current-year source column required')
    current=columns[str(report_year)][0];prior=columns[str(report_year-1)][-1]
    cell=primary['cell'];need(cell['statement']=='合并资产负债表' and cell['fiscal_end']==f'{report_year}-12-31'
        and type(cell['column_index']) is int and cell['column_index']==0 and cell['row_text_sha256']==digest(cell['row_text']),
        'protected original consolidated current asset control')
    values=op.row_values(cell['row_text'],r'^资产总计\s*',cell['header_line'])
    explicit=op.grammar.forms.explicit_local_unit(cell['unit_evidence_literal'])
    bare=re.fullmatch(r'单位[：:](元|万元)',compact(cell['unit_evidence_literal']))
    need(cell['unit'] in ('元','万元') and ((explicit is not None and explicit==cell['unit']) or (bare is not None and bare.group(1)==cell['unit'])),
         'protected primary unit matches its original declaration')
    need(cell['literal']==values[0] and cell['value_CNY']==normalized(values[0],cell['unit']),'protected primary value agrees with literal/unit')
    control_page=canonical.get(cell['page']);need(control_page is not None,'original consolidated asset control page required')
    control_labels=[w for w in control_page['words'] if compact(w['text'])=='资产总计'];need(len(control_labels)==1,'unique original consolidated asset row')
    control_row=band(control_page['words'],control_labels[0]);control_amounts=[w for w in control_row if MONEY.fullmatch(compact(w['text']))]
    need(len(control_amounts)==2 and all(Decimal(compact(w['text']).replace(',',''))==Decimal(v.replace(',','')) for w,v in zip(control_amounts,values)),
         'original geometry matches both protected consolidated row amounts')
    need(current['value_CNY']==cell['value_CNY'] and prior['value_CNY']==normalized(values[1],cell['unit']),
         'dated summary current/prior must reconcile; never choose a column by its value')
    result={'contract':CONTRACT,'source_sha256':source_sha256,'report_year':report_year,'publication_day':publication_day,
        'columns_by_year':columns,'current':copy.deepcopy(current),'prior':copy.deepcopy(prior),'row_label_word':copy.deepcopy(label),
        'summary_table':{'page':label['page'],'bbox':table},'header_tables':sorted(header_tables,key=lambda x:(x['page'],x['bbox'])),
        'primary':copy.deepcopy(primary),'primary_row_words':copy.deepcopy(control_row),
        'primary_comparative_date_as_reported':cell.get('reported_comparative_balance_date'),
        'normative_basis':basis(),'currency_is_regulatory_inference':True,'consolidated_scope_is_regulatory_inference':True,
        'same_edition_primary_reconciliation':True,'historical_arrival_verified':False,'investment_factor_admitted':False}
    result['record_id']=digest(result);return result
