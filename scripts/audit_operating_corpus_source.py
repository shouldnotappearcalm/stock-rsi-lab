"""Independent stdlib original-cell/latest-source witness check; no producer imports."""
import argparse
from collections import Counter
from datetime import datetime, time
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

OUTPUT='operating-corpus-source-v1-20261023'
PARENT='gross-profitability-all1236-header-v7-20261022'
INITIAL='gross-profitability-historical394-initial2022-schema-20261022'
LATER='gross-profitability-all1236-source-v6-20261022'
SUPPORTED='OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA'
FIELDS=('revenue','cost_of_sales','selling_expenses','administrative_expenses','research_expenses')
LABELS=dict(zip(FIELDS,('营业收入','营业成本','销售费用','管理费用','研发费用')))
TITLES=('合并资产负债表','母公司资产负债表','合并利润表','母公司利润表')
MONEY=r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
SH=ZoneInfo('Asia/Shanghai')


def need(ok,why):
    if not ok:raise ValueError(why)
def compact(text):return re.sub(r'\s+','',text)
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def aware(value):
    result=datetime.fromisoformat(value);need(result.tzinfo is not None and result.utcoffset() is not None,'aware source clock');return result
def public(document):
    day=datetime.strptime(document['day'],'%Y-%m-%d').date()
    need(day.isoformat()==document['day'],'canonical source publication day')
    return datetime.combine(day,time.max,SH)


def scoped_lines(pages):
    lines=[(i+1,line.strip()) for i,page in enumerate(pages) for line in page.splitlines() if line.strip()]
    starts=[i for i,(_,t) in enumerate(lines) if compact(t)=='二、财务报表']
    if starts:
        need(len(starts)==1,'unique original primary statement section')
        start=starts[0];ends=[i for i,(_,t) in enumerate(lines) if i>start and compact(t) in ('三、公司基本情况','三、财务报表附注','财务报表附注')]
        need(ends,'original primary statement end');lines=lines[start:min(ends)]
    positions={t:[] for t in TITLES};consumed_title_lines=set()
    for i,(_,line) in enumerate(lines):
        if i in consumed_title_lines:continue
        token=re.sub(r'^\d{1,2}[、.．]','',compact(line))
        if re.fullmatch(r'\d{1,2}[、]?',compact(line)) and i+1<len(lines) and lines[i+1][0]==lines[i][0]:
            token=compact(line)+compact(lines[i+1][1]);token=re.sub(r'^\d{1,2}[、.．]','',token)
            if token in positions:consumed_title_lines.add(i+1)
        if token in positions:positions[token].append(i)
    need(all(len(v)==1 for v in positions.values()),'unique original consolidated/parent table titles')
    indexes=[positions[t][0] for t in TITLES];need(indexes==sorted(indexes),'ordered original statement scopes')
    return lines,{'合并资产负债表':(indexes[0],indexes[1]),'合并利润表':(indexes[2],indexes[3])}


def original_block(lines,page,text,start,end):
    wanted=text.splitlines();found=[]
    for i in range(start,end):
        block=lines[i:i+len(wanted)]
        if len(block)==len(wanted) and i+len(wanted)<=end and all(p==page for p,_ in block) and [t for _,t in block]==wanted:
            found.append(i)
    need(len(found)==1,'one literal original same-page block in consolidated scope')
    return found[0]


def unit_quote(pages,cell,lines,start,end):
    quoted=cell['unit_evidence_literal'];page=cell['unit_evidence_page'];unit=cell['unit']
    need(type(page) is int and 1<=page<=len(pages) and compact(quoted) in compact(pages[page-1]),'original monetary unit quote')
    plain=compact(quoted);prefix=r'(?:编制单位[：:][^：:]{1,100}?)?'
    patterns=(prefix+r'单位[：:](元|万元)币种[：:]人民币',prefix+r'单位[：:]人民币(元|万元)',
              r'[（(](?:除特别(?:注明|说明)外[，,])?金额单位(?:[：:]|(?:均)?为)人民币(元|万元)[）)]',r'单位[：:](元|万元)')
    original_block(lines,page,quoted,start,end)
    # Establish the governing declaration from original consolidated scope,
    # independently of the producer's claimed unit pointer or report hash.
    for _,line in lines[start:end]:
        text=compact(line)
        if re.search(r'(?<!编制)单位[：:]|金额单位',text):
            declarations=[m.group(1) for pattern in patterns if (m:=re.fullmatch(pattern,text))]
            need(len(declarations)==1 and declarations[0]==unit,'consistent original consolidated monetary declarations')
    matched=[m.group(1) for pattern in patterns if (m:=re.fullmatch(pattern,plain))]
    need(len(matched)==1 and matched[0]==unit,'unit agrees with original declaration')
    if re.fullmatch(patterns[-1],plain):
        evidence=cell['currency_scope_evidence'];need(type(evidence) is list and evidence,'bare unit currency evidence')
        for item in evidence:
            p=item['page'];literal=compact(item['literal'])
            need(type(p) is int and 1<=p<=len(pages) and literal in compact(pages[p-1]),'original scoped currency evidence')
            need(item.get('currency','CNY')=='CNY' and not re.search(r'美元|港币|IFRS|未遵循|不符合|但是|但[，,]',literal,re.I),'unqualified CNY source evidence')
            if 'unit' in item:need(item['unit']==unit and '人民币'+unit in literal,'section/report unit evidence')
            if item.get('currency_is_regulatory_inference_not_literal_quote'):
                reference=item['normative_reference']
                need(reference['standard']=='CAS19_ART4' and reference['archived_body_sha256']=='a31fbfe26c8783fe1657b5730db90cf693bdb7d0dadd5e6858e2a998cfe46bfe'
                     and '财务报表符合' in literal and '企业会计准则' in literal,'pinned literal CAS compliance inference')
    return Decimal(1 if unit=='元' else 10000)


def check_case(pages,document,case):
    need(case['capture_key']==document['capture_key'] and case['instrument']==document['instrument']
         and case['source_sha256']==document['source_sha256'] and case['fiscal_year']==document['effective_fiscal_year'],'case/source identity')
    if case['status']!=SUPPORTED:
        need(case['status'] in ('OPERATING_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED') and case['operating_report'] is None,'failed case retained without numeric report')
        return 0
    report=case['operating_report'];payload=report['payload'];year=document['effective_fiscal_year']
    need(report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'}) and report['instrument']==document['instrument']
         and report['report_year']==year and report['publication_day']==document['day']
         and aware(report['observed_at'])==aware(document['captured_at_utc']) and aware(report['public_day_end_at'])==public(document)
         and payload['scope']=='CONSOLIDATED' and payload['document_sha256']==document['source_sha256']
         and payload['announcement_id']==document['announcement_id'],'complete original report provenance')
    parsed=payload['parsed'];periods={f'{year}-12-31',f'{year-1}-12-31'}
    need(set(parsed)=={'income','balances'} and set(parsed['income'])==set(parsed['balances'])==periods,'coherent same-edition annual periods')
    lines,bounds=scoped_lines(pages);count=0
    for kind in ('income','balances'):
        statement='合并利润表' if kind=='income' else '合并资产负债表';start,end=bounds[statement]
        for period in periods:
            fields=parsed[kind][period] if kind=='income' else {'total_assets':parsed[kind][period]}
            need(set(fields)==(set(FIELDS) if kind=='income' else {'total_assets'}),'exact original source fields')
            for field,cell in fields.items():
                column=year-int(period[:4]);need(cell['statement']==statement and cell['fiscal_end']==period
                    and type(cell['column_index']) is int and cell['column_index']==column,'source statement/fiscal column')
                original_block(lines,cell['page'],cell['row_text'],start,end)
                original_block(lines,cell['header_page'],cell['header_line'],start,end)
                suffix=(f'{year}年度{year-1}年度' if kind=='income' else f'{year}年12月31日{year-1}年12月31日')
                need(compact(cell['header_line']).endswith(suffix),'literal two-period header')
                if kind=='balances':need(cell['reported_comparative_balance_date']==f'{year-1}-12-31' and cell['comparative_date_is_unresolved'] is False,'explicit priorDecember31 assets')
                label=LABELS.get(field,'资产总计');plain=compact(cell['row_text'])
                need(re.match(r'^(?:其中[：:])?'+label,plain) and cell['row_text_sha256']==digest(cell['row_text']),'literal field label and row identity')
                tokens=re.findall(MONEY,cell['row_text']);need(len(tokens)==2 and tokens[column]==cell['literal'],'two literal original amount columns')
                multiplier=unit_quote(pages,cell,lines,start,end)
                with localcontext() as context:
                    context.prec=60;value=Decimal(tokens[column].replace(',',''))*multiplier
                need(value.is_finite() and (field!='total_assets' or value>0) and format(value,'f')==cell['value_CNY']
                     and str(multiplier)==cell['multiplier_CNY'],'independent normalized original monetary amount')
                count+=1
    need(count==12,'all twelve source cells checked')
    return count


def check_selection(documents,cases,view,cohort,as_of,mode):
    clock=aware(as_of);need(aware(view['as_of'])==clock and view['visibility_mode']==mode and view['cohort_count']==len(cohort),'query clock/cohort')
    rows=view['classifications'];need([r['instrument'] for r in rows]==sorted(cohort),'every original issuer once')
    for row in rows:
        code=row['instrument'];visible=[]
        for doc in documents:
            stamp=public(doc) if mode=='RECONSTRUCTED_PUBLICATION_DAY_END' else max(public(doc),aware(doc['captured_at_utc']))
            if stamp<=clock and doc['instrument']==code:visible.append(doc)
        need(row['investment_factor_admitted'] is False,'no source-only investment admission')
        if not visible:
            need(row['annual_status']=='NO_VISIBLE_ANNUAL_REPORT' and 'selected_capture_key' not in row,'empty historical source view')
            continue
        latest=max((d['effective_fiscal_year'],d['day']) for d in visible)
        choices=sorted((d for d in visible if (d['effective_fiscal_year'],d['day'])==latest),key=lambda d:(int(d['announcement_id']),d['capture_key']))
        need(row['latest_fiscal_year']==latest[0] and row['latest_publication_day']==latest[1]
             and row['selected_edition_capture_keys']==[d['capture_key'] for d in choices],'latest fiscal/publication edition witnesses')
        if len({d['source_sha256'] for d in choices})>1:
            need(row['annual_status']=='AMBIGUOUS_LATEST_SAME_DAY_EDITIONS' and 'selected_capture_key' not in row,'all conflicting latest editions block values')
            continue
        doc=choices[0];selected=cases[doc['capture_key']]
        need(row['selected_capture_key']==doc['capture_key'] and row['selected_source_sha256']==doc['source_sha256']
             and row['selected_source_status']==selected['status'],'independently selected source witness')
        expected='LATEST_OPERATING_SOURCE_SUPPORTED_NOT_INVESTMENT_ADMITTED' if selected['status']==SUPPORTED else 'LATEST_'+selected['status']
        need(row['annual_status']==expected,'unsupported newer source never falls back')
        if selected['status']==SUPPORTED:
            need(row['operating_record_id']==selected['operating_report']['record_id']
                 and row['current_fiscal_end']==f'{latest[0]}-12-31' and row['lagged_asset_fiscal_end']==f'{latest[0]-1}-12-31','source pointer and dated denominator')
        else:need('operating_record_id' not in row,'failed source supplies no monetary record')
    need('value_CNY' not in str(view) and 'operating_profit_to_lagged_assets' not in str(view),'metadata-only source coverage')
    return len(rows)


def resolve(key,root,base,membership):
    if key=='membership':return membership
    if key.startswith('catalog/'):
        name=key[8:];old=base/'cninfo-csi500-reports-20261017';fixed=base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
        special={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
                 'PDF_document_records':fixed,'inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
        if name in special:return special[name]
        if name.startswith('metadata/'):
            need(len(Path(name).parts)==2 and '..' not in Path(name).parts,'safe metadata source alias');return old/'codes'/(name[9:]+'.json')
        docs={d['capture_key']:d for d in read(fixed)};need(name.startswith('PDF/') and name[4:] in docs,'known source PDF alias')
        rel=Path(docs[name[4:]]['source_path']);need(not rel.is_absolute() and '..' not in rel.parts,'safe source PDF alias');return base/rel
    prefix,relative=key.split('/',1);rel=Path(relative)
    need(prefix in ('source','repo') and not rel.is_absolute() and '..' not in rel.parts,'safe frozen source namespace')
    return (base if prefix=='source' else root)/rel


def audit(base,root,membership,request_file,expected_sha):
    need(sha(request_file)==expected_sha,'frozen request identity');req=read(request_file);out=base/OUTPUT
    paths={k:resolve(k,root,base,membership) for k in req['input_sha256']};paths['frozen_request']=request_file
    expected={**req['input_sha256'],'frozen_request':expected_sha}
    for key,path in paths.items():need(sha(path)==expected[key],'audit bound source input '+key)
    before={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    wanted={d['capture_key']+'.json' for d in req['documents']}|{
        f['execution_session']+'-'+mode+'.json' for f in req['formations'] for mode in req['modes']}|{
        'input-before.json','case_results.json','input-postcheck.json','terminal.json','summary.json'}
    need(set(before)==wanted,'complete exact source output inventory; no failed/pending files')
    cases=read(out/'case_results.json');need(set(cases)=={d['capture_key'] for d in req['documents']},'all source cases retained')
    need(read(out/'input-before.json')==expected and read(out/'input-postcheck.json')['all_inputs_unchanged'] is True
         and read(out/'terminal.json')['completed'] is True,'source run before/after and completed terminal')
    checked=0
    for doc in req['documents']:
        key=doc['capture_key'];case=cases[key];need(case==read(out/(key+'.json')),'individual/aggregate source agreement')
        need(sha(base/doc['source_path'])==doc['source_sha256'],'original PDF bytes')
        folder=INITIAL if doc['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else LATER
        cache_file=base/folder/(key+'.pages.json');cache=read(cache_file);parent_case=read(base/PARENT/(key+'.json'));pages=cache['pages']
        need(cache['source_sha256']==doc['source_sha256'] and cache['extractor']=='pypdf6.10.0'
             and case['source_page_cache_sha256']==sha(cache_file) and case['parent_case_sha256']==sha(base/PARENT/(key+'.json'))
             and len(pages)==parent_case['page_count'] and {str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}
             ==parent_case['all_extracted_page_text_sha256'],'authenticated original physical pages')
        if not(parent_case['cover_code_consistent'] and parent_case['cover_annual_year_consistent']):need(case['status']=='COVER_IDENTITY_UNVERIFIED','cover identity failures stay unverified')
        checked+=check_case(pages,doc,case)
    selected=0
    for formation in req['formations']:
        for mode in req['modes']:
            view=read(out/(formation['execution_session']+'-'+mode+'.json'))
            selected+=check_selection(req['documents'],cases,view,req['cohort'],formation['as_of'],mode)
    for key,path in paths.items():need(sha(path)==expected[key],'audit source/request changed '+key)
    need(before=={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},'source outputs changed during audit')
    summary=read(out/'summary.json');need(summary['document_count']==len(cases) and summary['raw_monetary_cells']==checked
        and summary['status_counts']==dict(Counter(c['status'] for c in cases.values())),'source summary independently agrees')
    return {'status':'PASS_SEPARATE_OPERATING_ORIGINAL_CELLS_AND_LATEST_SOURCE_WITNESSES','request_sha256':expected_sha,
        'audit_code_sha256':sha(Path(__file__)),'all_input_sha256':expected,'all_output_sha256':before,
        'document_count':len(cases),'supported_source_cells_checked':checked,'latest_source_rows_checked':selected,
        'all_inputs_outputs_unchanged':True,'shared_authenticated_PDF_text_and_researcher_provenance':True,
        'manual_visual_QA_complete':False,'investment_factor_admitted':False,'ratios_rankings_or_returns_computed':False,'objective_achieved':False}


def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();target=Path(args.output);need(not target.exists(),'fresh independent audit output')
    try:
        result=audit(Path(args.source_root).resolve(),Path(__file__).resolve().parents[1],Path(args.membership_file).resolve(),
                     Path(args.request).resolve(),args.expected_request_sha256)
    except BaseException as exc:
        with target.open('x') as stream:json.dump({'status':'FAILED_INDEPENDENT_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'investment_factor_admitted':False},stream,ensure_ascii=False,indent=2)
        raise
    with target.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(result['status'],result['supported_source_cells_checked'],result['latest_source_rows_checked'])


if __name__=='__main__':main()
