"""Separate original-source position, arithmetic and coverage checks; no new producer imports."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal,localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from scripts import audit_operating_corpus_source as original

OUTPUT='operating-asset-recovery-source-v1-20261023'
LEGACY='operating-corpus-source-v1-20261023'
GP='gross-profitability-all1236-header-v7-20261022'
INITIAL='gross-profitability-historical394-initial2022-schema-20261022'
LATER='gross-profitability-all1236-source-v6-20261022'
NEW='SUMMARY_SOURCE_RECOVERED_NOT_INVESTMENT_ADMITTED'
OLD='UNCHANGED_LEGACY_OPERATING_SOURCE_SUPPORTED'
FAILED='STILL_UNSUPPORTED'
RULE_SHA='b727419bdab8b137224cea1c9c8b7d20e8a8f1e3714c6ef2e3a6242cd4767615'
RECORD_CONTRACT='CN_OPERATING_INCOME_AND_SUMMARY_PRIOR_ASSETS_SOURCE_V1'
ASSET_CONTRACT='CN_ANNUAL_SUMMARY_PRIOR_YEAR_END_ASSET_WORDS_V1'
need,read,sha,digest,compact=original.need,original.read,original.sha,original.digest,original.compact
MONEY=re.compile(r'(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}')


def regulatory_basis():
    return {'standard':'CSRC_ANNUAL_FORMAT_2021_ART10_19_20','body_sha256':RULE_SHA,
        'effective_from':'2021-06-28','effective_before':'2025-07-01','currency_default':'CNY_UNLESS_OTHERWISE_SPECIFIED',
        'consolidated_scope':'REGULATORY_INFERENCE_NOT_ISSUER_QUOTE'}


def check_scope(req,old,originals,inventory):
    need(req['status']=='FROZEN_BEFORE_COMPLETE_OPERATING_ASSET_SOURCE_RECOVERY' and req['output_subdir']==OUTPUT
        and req['document_count']==1236 and req['cohort_count']==394 and req['target_count']==339
        and req['runtime_python']=='3.12.14' and req['pdfplumber_version']=='0.11.9'
        and req['workers']==req['maximum_outstanding_documents']==4 and req['geometry_pages_per_target']==5
        and req['geometry_pages_per_pass']==1695 and req['cached_search_first_pages']==20 and req['maximum_nonoverlapping_two_page_windows']==2
        and req['network_permitted'] is False and req['factor_ratio_rank_or_return_permitted'] is False
        and req['2026_financial_or_market_values_permitted'] is False and req['normative_basis']==regulatory_basis(),
        'independent complete source-only request scope and budgets')
    for field in ('documents','cohort','formations','modes'):need(req[field]==old[field],'entire original '+field+' retained')
    keys={k for k,c in originals.items() if c.get('error')=='same-edition explicitly dated prior December31 assets required'}
    need(len(keys)==339 and keys=={r['capture_key'] for r in inventory['rows']}
        and req['targets']==[d['capture_key'] for d in old['documents'] if d['capture_key'] in keys],'every original date-failure target, never a supported subset')


def point(w,number):return {'page':number,'text':w['text'],'x0':float(w['x0']),'x1':float(w['x1']),'top':float(w['top']),'bottom':float(w['bottom'])}
def center(w):return (w['x0']+w['x1'])/2
def where(w):return w['page'],w['top'],w['x0']
def inside(w,b):return b[0]-1<=w['x0'] and w['x1']<=b[2]+1 and b[1]-1<=w['top'] and w['bottom']<=b[3]+1


def exact_word(pages,claimed):
    need(type(claimed) is dict and type(claimed.get('page')) is int,'claimed original physical word')
    for field in ('x0','x1','top','bottom'):need(type(claimed.get(field)) in (int,float) and math.isfinite(claimed[field]),'finite claimed source position')
    page=pages.get(claimed['page']);need(page is not None,'claimed physical page present')
    matches=[point(w,claimed['page']) for w in page['words'] if point(w,claimed['page'])==claimed]
    need(len(matches)==1,'exact original source word text and position')
    return matches[0]


def check_asset(texts,geometry,doc,gp,asset):
    year=doc['effective_fiscal_year'];pages={p['physical_page']:p for p in geometry}
    need(len(pages)==len(geometry) and all(p['source_sha256']==doc['source_sha256'] for p in pages.values()),'unique same-PDF geometry pages')
    need(asset['record_id']==digest({k:v for k,v in asset.items() if k!='record_id'}) and asset['contract']==ASSET_CONTRACT
         and asset['source_sha256']==doc['source_sha256'] and asset['report_year']==year and asset['publication_day']==doc['day'],'asset source identity and contract')
    rule=asset['normative_basis'];need(rule==regulatory_basis() and '2021-06-28'<=doc['day']<'2025-07-01','bound original regulatory inference')
    need(asset['currency_is_regulatory_inference'] is True and asset['consolidated_scope_is_regulatory_inference'] is True
        and asset['investment_factor_admitted'] is False,'source inference remains explicit')
    label=exact_word(pages,asset['row_label_word']);match=re.fullmatch(r'总资产[（(](元|万元)[）)]',compact(label['text']));need(match is not None,'literal original asset row unit')
    unit=match.group(1);multiplier=Decimal(1 if unit=='元' else 10000)
    labels=[w for p in pages.values() for w in p['words'] if re.fullmatch(r'总资产[（(].+[）)]',compact(w['text']))]
    need(len(labels)==1,'unique original main-summary asset row')
    scope=asset['summary_table'];need(scope['page']==label['page'] and scope['bbox'] in [t['bbox'] for t in pages[label['page']]['tables']]
         and inside(label,scope['bbox']),'original summary table boundary')
    governing=[]
    for table in asset['header_tables']:
        p=pages.get(table['page']);need(p is not None and table['bbox'] in [t['bbox'] for t in p['tables']],'original year-header table boundary')
        need(table['page'] in (label['page'],label['page']-1),'adjacent year-header table only')
        if table['page']!=label['page']:
            need(abs(p['width']-pages[label['page']]['width'])<=1 and abs(table['bbox'][0]-scope['bbox'][0])<=2
                 and abs(table['bbox'][2]-scope['bbox'][2])<=2,'original adjacent header page alignment')
        governing.extend(point(w,table['page']) for w in p['words'] if inside(w,table['bbox']))
    need(not any(re.search(r'美元|港币|港元|日元|欧元|\b(?:USD|HKD|EUR)\b',compact(w['text']),re.I) for w in governing),'no conflicting source currency')
    anchors=[w for w in governing if re.fullmatch(r'20\d\d年末',compact(w['text'])) and where(w)<where(label)]
    by_year={}
    for word in anchors:
        y=int(compact(word['text'])[:4]);need(y not in by_year,'one original year-end parent per year');by_year[y]=word
    need({year,year-1}<=set(by_year)<=set(range(year-2,year+1)) and len({w['page'] for w in anchors})==1
        and max(w['top'] for w in anchors)-min(w['top'] for w in anchors)<=24,'coherent original annual year-end header group')
    need(sorted(by_year,key=lambda y:center(by_year[y]))==sorted(by_year,reverse=True),'original fiscal columns ordered')
    first=min(where(w) for w in anchors);adjustments=[w for w in governing if compact(w['text']) in ('调整前','调整后') and first<=where(w)<where(label)]
    raw_row=[point(w,label['page']) for w in pages[label['page']]['words'] if inside(w,scope['bbox']) and w['bottom']>=label['top']-1 and w['top']<=label['bottom']+1]
    source_money=sorted([w for w in raw_row if MONEY.fullmatch(compact(w['text']))],key=center);claimed_money=[];count=0
    groups=asset['columns_by_year'];need(set(groups)=={str(y) for y in by_year},'all original fiscal asset groups retained')
    for y in sorted(by_year,reverse=True):
        columns=groups[str(y)];need(len(columns) in (1,2),'one reported or before/after source asset group')
        positions=[];children=[]
        for cell in columns:
            amount=exact_word(pages,cell['amount_word']);parent=exact_word(pages,cell['year_word']);positions.append(center(amount));claimed_money.append(amount)
            need(parent==by_year[y] and amount in source_money and cell['fiscal_end']==f'{y}-12-31' and cell['literal']==compact(amount['text'])
                and cell['unit']==unit,'claimed fiscal asset is the original labelled source column')
            distances=sorted((abs(center(amount)-center(w)),yy) for yy,w in by_year.items())
            need(distances[0][1]==y and (len(distances)==1 or distances[1][0]-distances[0][0]>1),'unambiguous original monetary year alignment')
            child=cell['adjustment_word']
            if len(columns)==1:
                need(child is None and cell['adjustment']=='AS_REPORTED' and abs(center(amount)-center(parent))<=12
                    and not any(abs(center(h)-center(amount))<=12 for h in adjustments),'original singleton without hidden adjustment')
            else:
                child=exact_word(pages,child);children.append(child)
                need(child in adjustments and abs(center(child)-center(amount))<=12
                    and cell['adjustment']==('BEFORE_ADJUSTMENT' if compact(child['text'])=='调整前' else 'AFTER_ADJUSTMENT'),
                    'original adjustment child label and source amount alignment')
            with localcontext() as context:
                context.prec=60;value=Decimal(cell['literal'].replace(',',''))*multiplier
            need(value.is_finite() and value>0 and format(value,'f')==cell['value_CNY'],'independent normalized asset amount')
            need(1<=amount['page']<=len(texts) and compact(amount['text']) in compact(texts[amount['page']-1]),'original cached asset amount literal')
            count+=1
        need(positions==sorted(positions),'original amount order within year')
        if children:need([compact(c['text']) for c in children]==['调整前','调整后']
            and abs(sum(center(c) for c in children)/2-center(by_year[y]))<=12,'ordered original before/after group and parent')
    need(sorted(claimed_money,key=center)==source_money,'all original asset-money columns exactly once; percentages excluded')
    need(len(groups[str(year)])==1 and asset['current']==groups[str(year)][0] and asset['prior']==groups[str(year-1)][-1],
         'current singleton and correct prior-year adjusted source selection')
    observations=[o for o in gp['source_observations'] if o['fiscal_end']==f'{year}-12-31'];need(len(observations)==1,'one protected GP current observation')
    primary=observations[0]['payload']['cells']['total_assets'];need(asset['primary']=={'source_sha256':doc['source_sha256'],'report_year':year,'cell':primary},'protected same-edition consolidated control')
    lines,bounds=original.scoped_lines(texts);start,end=bounds['合并资产负债表'];original.original_block(lines,primary['page'],primary['row_text'],start,end)
    primary_multiplier=original.unit_quote(texts,primary,lines,start,end);tokens=re.findall(original.MONEY,primary['row_text']);need(len(tokens)==2,'two original consolidated asset amounts')
    with localcontext() as context:
        context.prec=60;values=[format(Decimal(t.replace(',',''))*primary_multiplier,'f') for t in tokens]
    need(asset['current']['value_CNY']==values[0]==primary['value_CNY'] and asset['prior']['value_CNY']==values[1]
        and asset['primary_comparative_date_as_reported']==primary.get('reported_comparative_balance_date'),'exact primary reconciliation without redating opening')
    primary_words=[exact_word(pages,w) for w in asset['primary_row_words']];primary_literals=[compact(w['text']) for w in primary_words if MONEY.fullmatch(compact(w['text']))]
    need(primary_literals==tokens,'original primary source row geometry matches literal controls')
    return count+2


def check_case(original_texts,geometry,document,original_case,new_case):
    old,gp=original_case['operating'],original_case['GP'];need(new_case['capture_key']==document['capture_key']==old['capture_key']
        and new_case['instrument']==document['instrument']==old['instrument'] and new_case['source_sha256']==document['source_sha256']==old['source_sha256']
        and new_case['fiscal_year']==document['effective_fiscal_year']==old['fiscal_year'] and new_case['original_status']==old['status']
        and new_case['original_error']==old.get('error'),
        'same original source case and fiscal identity')
    if old['status']=='OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA':
        need(new_case['effective_source_status']==OLD and new_case['effective_record_id']==old['operating_report']['record_id']
            and new_case['source_record'] is None,'legacy source unchanged');return 0
    asset=new_case['asset_bridge'];record=new_case['source_record'];count=0
    if asset is not None:count=check_asset(original_texts,geometry,document,gp,asset)
    if record is None:
        need(new_case['effective_source_status']==FAILED and new_case['effective_record_id'] is None,'failed source has no operating record');return count
    need(new_case['effective_source_status']==NEW and new_case['effective_record_id']==record['record_id']
        and record['record_id']==digest({k:v for k,v in record.items() if k!='record_id'}) and record['contract']==RECORD_CONTRACT
        and record['instrument']==document['instrument'] and record['report_year']==document['effective_fiscal_year']
        and record['publication_day']==document['day'] and original.aware(record['observed_at'])==original.aware(document['captured_at_utc'])
        and original.aware(record['public_day_end_at'])==original.public(document),'coherent recovered record identity and clocks')
    payload=record['payload'];year=document['effective_fiscal_year']
    need(payload['document_sha256']==document['source_sha256'] and payload['announcement_id']==document['announcement_id']
        and payload['asset_bridge']==asset and record['investment_factor_admitted'] is False
        and payload['income_origin']=='CONSOLIDATED_INCOME_STATEMENT' and payload['asset_origin']=='MAIN_ACCOUNTING_DATA_SUMMARY_YEAR_END',
        'same source payload, original table origins and explicit nonadmission')
    income=payload['income'];need(set(income)=={f'{year}-12-31',f'{year-1}-12-31'},'both original annual income periods')
    lines,bounds=original.scoped_lines(original_texts);start,end=bounds['合并利润表']
    for period,fields in income.items():
        column=year-int(period[:4]);need(set(fields)==set(original.FIELDS),'all five explicit income source fields')
        for field,cell in fields.items():
            need(cell['statement']=='合并利润表' and cell['fiscal_end']==period and type(cell['column_index']) is int and cell['column_index']==column
                and cell['row_text_sha256']==digest(cell['row_text']),'coherent original income statement, period and column')
            original.original_block(lines,cell['page'],cell['row_text'],start,end);original.original_block(lines,cell['header_page'],cell['header_line'],start,end)
            need(compact(cell['header_line']).endswith(f'{year}年度{year-1}年度') and re.match(r'^(?:其中[：:])?'+original.LABELS[field],compact(cell['row_text'])),'literal original annual header and income label')
            values=re.findall(original.MONEY,cell['row_text']);need(len(values)==2 and values[column]==cell['literal'],'two original signed monetary income columns')
            multiplier=original.unit_quote(original_texts,cell,lines,start,end)
            with localcontext() as context:
                context.prec=60;value=Decimal(values[column].replace(',',''))*multiplier
            need(value.is_finite() and format(value,'f')==cell['value_CNY'] and str(multiplier)==cell['multiplier_CNY'],'independent signed income normalization')
            count+=1
    return count


def check_coverage(original_view,new_view,cases):
    need(len(new_view['classifications'])==len(original_view['classifications']),'complete original cohort rows')
    for key,value in original_view.items():
        if key!='classifications':need(new_view[key]==value,'original metadata query identity and flags')
    for old,row in zip(original_view['classifications'],new_view['classifications']):
        need({k:v for k,v in row.items() if k not in ('effective_source_status','effective_record_id')}==old,'original filing selection witness unchanged')
        key=old.get('selected_capture_key')
        if key is None:
            need(row['effective_source_status']==old['annual_status'] and 'effective_record_id' not in row,'no future/unselected record pointer');continue
        case=cases[key];need(case['capture_key']==key and case['instrument']==old['instrument'] and case['source_sha256']==old['selected_source_sha256']
            and row['effective_source_status']==case['effective_source_status'] and row['effective_record_id']==case['effective_record_id'],'same visible selected source and validated result')
    need('value_CNY' not in str(new_view) and 'operating_profit_to_lagged_assets' not in str(new_view),'source coverage exposes no amounts or ratios')
    return len(new_view['classifications'])


def locate_pages(texts,year,primary):
    selected=set();count=0;clean=[compact(t) for t in texts[:20]]
    for i in range(len(clean)-1):
        pair=''.join(clean[i:i+2]);heading=''.join(clean[max(0,i-1):i+2]);candidate={i+1,i+2}
        if '总资产' in pair and (f'{year-1}年末' in pair or f'{year-1}年12月31日' in pair) and '主要会计数据' in heading and not candidate&selected:
            selected|=candidate;count+=1
            if count==2:break
    return sorted(selected|{primary}) if count else []


def audit(base,root,membership,request_file,expected_sha):
    need(sha(request_file)==expected_sha,'frozen independent recovery request');req=read(request_file);out=base/OUTPUT
    need(sys.version.split()[0]=='3.12.14','frozen actual source audit runtime')
    import pdfplumber
    need(pdfplumber.__version__=='0.11.9','frozen audit geometry reader')
    paths={k:original.resolve(k,root,base,membership) for k in req['input_sha256']};paths['frozen_request']=request_file
    expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,p in paths.items():need(sha(p)==expected[key],'original recovery audit input '+key)
    parent_file=root/'experiments/qlib/operating-corpus-source-request.json'
    proof_file=root/'experiments/qlib/operating-corpus-source-independent-check.json'
    need(sha(parent_file)=='f0302c00af7e312055aaf5a41f74a547de2bf2aaf9465a65d38aa9bf92da3710'
        and sha(proof_file)=='292aceb7322fe8dd6b15b67a3be4d45ea285ddbbe60876bdde1358d603893581','original source authority identities')
    parent=read(parent_file);proof=read(proof_file)
    check_scope(req,parent,read(base/LEGACY/'case_results.json'),read(root/'experiments/qlib/operating-lagged-asset-date-inventory.json'))
    for key,h in parent['input_sha256'].items():need(req['input_sha256'].get(key)==h,'entire original source input closure')
    need(proof['all_output_sha256']=={str(p.relative_to(base/LEGACY)):sha(p) for p in sorted((base/LEGACY).rglob('*')) if p.is_file()},
         'entire original source output inventory unchanged')
    for name,h in proof['all_output_sha256'].items():need(req['input_sha256'].get('source/'+LEGACY+'/'+name)==h,'original output bound as recovery input')
    expected_methods=set(parent['method_sha256'])|{'src/stock_rsi/asset_geometry.py','src/stock_rsi/operating_source_bridge.py',
        'scripts/recover_operating_assets.py','scripts/audit_operating_asset_recovery.py'}
    need(set(req['method_sha256'])==expected_methods and all(h==req['input_sha256'].get('repo/'+name) for name,h in req['method_sha256'].items()),
         'all source methods explicitly bound')
    before={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    wanted={d['capture_key']+'.json' for d in req['documents']}|{key+'.geometry.json' for key in req['targets']}|{
        f['execution_session']+'-'+mode+'.json' for f in req['formations'] for mode in req['modes']}|{
        'input-before.json','case_results.json','input-postcheck.json','terminal.json','summary.json'}
    need(set(before)==wanted and read(out/'terminal.json')['completed'] is True and read(out/'input-before.json')==expected
        and read(out/'input-postcheck.json')['all_inputs_unchanged'] is True,'complete exact immutable recovery output inventory')
    cases=read(out/'case_results.json');need(set(cases)=={d['capture_key'] for d in req['documents']},'all original source cases retained')
    targets=set(req['targets']);checked=0;word_pages=0
    for i,doc in enumerate(req['documents']):
        key=doc['capture_key'];case=cases[key];old=read(base/LEGACY/(key+'.json'));need(case==read(out/(key+'.json'))
            and case['original_case_sha256']==sha(base/LEGACY/(key+'.json')),'original individual/aggregate source witness')
        if key not in targets:
            need(case['recovery_state']=='NOT_TARGETED' and case['source_record'] is None and case['asset_bridge'] is None,'non-target source unchanged')
            if old['status']=='OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA':need(case['effective_source_status']==OLD and case['effective_record_id']==old['operating_report']['record_id'],'all legacy positive IDs preserved')
            else:need(case['effective_source_status']==FAILED and case['effective_record_id'] is None,'all other original failures preserved')
            continue
        need(old.get('error')=='same-edition explicitly dated prior December31 assets required' and case['recovery_state']=='ATTEMPT_COMPLETE','every original date failure attempted')
        gp=read(base/GP/(key+'.json'));folder=INITIAL if doc['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER
        cache=read(base/folder/(key+'.pages.json'));texts=cache['pages'];geometry=read(out/(key+'.geometry.json'))
        need(sha(base/doc['source_path'])==doc['source_sha256']==gp['source_sha256']==cache['source_sha256']
            and cache['extractor']=='pypdf6.10.0' and len(texts)==gp['page_count']
            and {str(j+1):hashlib.sha256(t.encode()).hexdigest() for j,t in enumerate(texts)}==gp['all_extracted_page_text_sha256'],'original PDF/cache and every page text')
        current=[o for o in gp['source_observations'] if o['fiscal_end']==f'{doc["effective_fiscal_year"]}-12-31'];need(len(current)==1,'one protected current GP source')
        selected=[] if not '2021-06-28'<=doc['day']<'2025-07-01' else locate_pages(texts,doc['effective_fiscal_year'],current[0]['payload']['cells']['total_assets']['page'])
        need(selected==case['selected_geometry_pages'] and len(selected)<=5,'independently bounded original source page locations')
        regenerated=[];reader_error=None
        if selected:
            try:
                with pdfplumber.open(base/doc['source_path']) as pdf:
                    need(len(pdf.pages)==len(texts),'same original physical source page count')
                    for number in selected:
                        p=pdf.pages[number-1];regenerated.append({'physical_page':number,'width':p.width,'height':p.height,'source_sha256':doc['source_sha256'],
                            'tables':[{'bbox':list(t.bbox)} for t in p.find_tables(table_settings={})],
                            'words':p.extract_words(x_tolerance=3,y_tolerance=3,keep_blank_chars=False)})
            except Exception as exc:reader_error=exc
        need(regenerated==geometry,'original raw word/table positions independently re-extracted')
        if reader_error is not None:need(case.get('failure_stage')=='GEOMETRY_READ' and case['source_record'] is None,'source decoder failure never supplies operating record')
        elif selected:need(len(geometry)==len(selected),'all registered geometry pages retained')
        word_pages+=len(geometry);checked+=check_case(texts,geometry,doc,{'operating':old,'GP':gp},case)
        if (i+1)%100==0:print('independent asset source audit',i+1,'/',len(req['documents']),flush=True)
    rows=0
    for formation in req['formations']:
        for mode in req['modes']:
            name=formation['execution_session']+'-'+mode+'.json';rows+=check_coverage(read(base/LEGACY/name),read(out/name),cases)
    summary=read(out/'summary.json');need(summary['document_count']==1236 and summary['target_documents_completed']==339
        and summary['effective_source_status_counts']==dict(Counter(c['effective_source_status'] for c in cases.values()))
        and summary['observed_visible_annual_rows']==0,'complete source summary agrees')
    for key,p in paths.items():need(sha(p)==expected[key],'recovery audit source/request changed '+key)
    need(before=={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},'recovery outputs unchanged during audit')
    return {'status':'PASS_SEPARATE_OPERATING_RECOVERY_ORIGINAL_CELLS_AND_POSITIONS','request_sha256':expected_sha,
        'audit_code_sha256':sha(Path(__file__)),'all_input_sha256':expected,'all_output_sha256':before,
        'document_count':len(cases),'target_count':len(targets),'source_cells_checked':checked,'original_geometry_pages_reextracted':word_pages,
        'original_coverage_rows_checked':rows,'all_inputs_outputs_unchanged':True,'shared_pdfminer_and_researcher_provenance':True,
        'manual_all_source_visual_QA_complete':False,'investment_factor_admitted':False,'ratios_or_returns_computed':False,'objective_achieved':False}


def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256','output'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();target=Path(a.output);need(not target.exists(),'fresh separate source audit output')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with target.open('x') as f:json.dump({'status':'FAILED_INDEPENDENT_RECOVERY_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'investment_factor_admitted':False},f,ensure_ascii=False,indent=2)
        raise
    with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],result['source_cells_checked'],result['original_coverage_rows_checked'],flush=True)


if __name__=='__main__':main()
