"""Separate corpus conservation and source-cell QA, without production imports.
Shared pypdf; same researcher after run start. Not a blinded grammar replication.
"""
import argparse
from collections import Counter
from datetime import date,datetime,time,timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def need(value,why):
    if not value:raise AssertionError(why)
def read(path):return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def compact(text):return re.sub(r'\s+','',text)
def title(text):return re.sub(r'^\d{1,2}[、.．]','',compact(text))
def inventory(folder):return {str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


SUPPORTED='SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW'
INFERRED='INFERRED_FROM_EXPLICIT_CAS_COMPLIANCE_AND_CAS19_ART4'
INITIAL='gross-profitability-historical394-initial2022-pdfs-20261022'
CACHE='gross-profitability-historical394-initial2022-schema-20261022'
V5='gross-profitability-historical394-initial2022-v5-20261022'
LATER='gross-profitability-historical394-later-annual-pdfs-20261022'
FIXED='gross-profitability-fixed12-source-context-v4-20261022'
CAS19={
    'standard':'CAS19_ART4','publisher':'MINISTRY_OF_FINANCE_CHINA',
    'official_url':'https://kjs.mof.gov.cn/zt/kjzzss/kuaijizhunzeshishi/200806/t20080618_46229.htm',
    'publisher_displayed_day':'2006-03-09',
    'archived_body_sha256':'a31fbfe26c8783fe1657b5730db90cf693bdb7d0dadd5e6858e2a998cfe46bfe',
    'archived_text_sha256':'75371ec30fbccc52cab3c2966815b033498850434772642974b49ad36534a74a',
    'normative_phrase':'编报的财务报表应当折算为人民币'}


def paths_for(req,root,base,membership,request):
    old=base/'cninfo-csi500-reports-20261017'
    fixed=base/'gross-profitability-fixed12-annual-pdfs-20261022'
    docs={d['capture_key']:d for d in read(fixed/'documents.json')}
    special={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':fixed/'documents.json',
        'inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths={'frozen_source_request':request}
    for key in req['input_sha256']:
        prefix,name=key.split('/',1)
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe source binding')
        if prefix=='repo':path=root/name
        elif prefix=='source':path=base/name
        else:
            need(prefix=='catalog','known catalog alias')
            if name in special:path=special[name]
            elif name.startswith('metadata/'):path=old/'codes'/(name.split('/',1)[1]+'.json')
            else:
                need(name.startswith('PDF/') and name[4:] in docs,'known fixed original')
                path=base/docs[name[4:]]['source_path']
        paths[key]=path
    return paths


def page_lines(pages):
    """Join only a separated ordinal and an explicit financial title."""
    titles={'合并资产负债表','母公司资产负债表','合并利润表','母公司利润表'}
    lines=[]
    for page,text in enumerate(pages,1):
        raw=[s.strip() for s in text.splitlines() if s.strip()];i=0
        while i<len(raw):
            block=raw[i]
            if i+1<len(raw):
                a,b=compact(raw[i]),compact(raw[i+1])
                if (re.fullmatch(r'\d{1,2}',a) and b.startswith('、') and b[1:] in titles) or (re.fullmatch(r'\d{1,2}、',a) and b in titles):
                    block+='\n'+raw[i+1];i+=1
            lines.append((page,block));i+=1
    return lines


def annual_title_pattern(year):
    return r'(?<!\d)'+r'\s*'.join(str(year))+r'\s*年?\s*年\s*度\s*报\s*告'


def source_identity(pages,instrument,year):
    """Reconstruct the existing V3 cover-first/issuer-information contract."""
    pattern=r'(?:公司|股票|证券)\s*代码\s*[：:|｜]?\s*(\d{6})(?!\d)'
    cover,company,context=[],[],[]
    for i,text in enumerate(pages[:20]):
        for match in re.finditer(pattern,text):
            evidence={'code':match.group(1),'physical_page':i+1,'literal':match.group(0)}
            context.append(evidence)
            if i<5:cover.append(evidence)
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        for j,line in enumerate(lines):
            if compact(line) in ('一、公司信息','公司信息','公司股票简况','五、公司股票简况'):
                block='\n'.join(lines[j:j+8])
                for match in re.finditer(pattern,block):
                    company.append({'code':match.group(1),'physical_page':i+1,'literal':match.group(0),'context':block})
            if compact(line)=='股票种类股票上市交易所股票简称股票代码变更前股票简称' and j+1<len(lines):
                row=lines[j+1];tokens=re.findall(r'(?<!\d)\d{6}(?!\d)',row)
                if re.match(r'^A\s*股\s+',row) and len(tokens)==1:
                    company.append({'code':tokens[0],'physical_page':i+1,'literal':line+'\n'+row,'context':'ISSUER_STOCK_INFORMATION_TABLE'})
    selected=cover if cover else company
    return {'code_consistent':{m['code'] for m in selected}=={instrument[2:]},
        'annual_year_consistent':bool(re.search(annual_title_pattern(year),'\n'.join(pages[:5]))),
        'literal_code_evidence':selected,'code_selection_scope':'FIRST5_COVER' if cover else 'FIRST20_ISSUER_INFORMATION',
        'other_literal_codes_retained_for_context':context,'code_window_physical_pages':20,'annual_title_window_physical_pages':5}


def verify_source_header(header,page,direct,segment):
    local='\n'.join(t for physical,t in segment if physical==page)
    need(('\n'+header+'\n') in ('\n'+direct(page)+'\n')
         and ('\n'+header+'\n') in ('\n'+local+'\n'),'exact fiscal header on the selected consolidated page')


def currency(cell,direct,pages,context,year):
    unit=cell['unit'];quote=cell['unit_evidence_literal']
    need(quote in direct(cell['unit_evidence_page']),'original unit quote')
    normalized=compact(quote).replace('：',':').replace('（','(').replace('）',')')
    explicit=(normalized.endswith('单位:'+unit+'币种:人民币') or normalized.endswith('单位:人民币'+unit)
              or normalized.endswith('人民币'+unit+')'))
    if explicit:return False
    # Older V2 local-section scopes may combine two literal same-page lines.
    if cell.get('unit_evidence_scope')=='LOCAL_FINANCIAL_SECTION_EXPLICIT_RMB':
        need(all(q in direct(cell['unit_evidence_page']) for q in quote.splitlines())
             and '人民币'+unit in compact(quote),'local explicit section RMB')
        return False
    need(normalized=='单位:'+unit and cell['currency_scope_evidence'],'bare unit needs bounded currency evidence')
    inferred=False
    for e in cell['currency_scope_evidence']:
        literal=e['literal'];plain=compact(literal);text=direct(e['page'])
        need(literal in pages[e['page']-1] or literal in text,'exact currency/declaration source quote')
        scope=e['scope']
        if scope=='EXPLICIT_PRIMARY_FINANCIAL_SECTION_RMB':
            need(e['unit']==unit and re.fullmatch(r'财务附注中报表的单位为[：:]人民币'+unit,plain),'primary-section RMB')
        elif scope=='EXPLICIT_REPORT_PREPARATION_CURRENCY_AND_UNIT':
            need(e['unit']==unit and re.fullmatch(r'本集团记账本位币和编制本财务报表所采用的货币均为人民币[。；;]除有特别说明外[，,]?均以人民币'+unit+r'为单位表示[。]?',plain),'complete preparation/unit declaration')
        elif scope in ('EXPLICIT_REPORT_PRESENTATION_CURRENCY_ONLY','EXPLICIT_REPORT_PREPARATION_CURRENCY_ONLY'):
            need(e['currency']=='CNY' and 'unit' not in e,'currency-only evidence cannot invent unit')
            pattern=(r'本财务报表以人民币列示[。；;]' if scope=='EXPLICIT_REPORT_PRESENTATION_CURRENCY_ONLY' else
                r'(?:(?:本公司|本集团|公司)编制本财务报表时所采用的货币为|本(?:公司|集团)记账本位币和编制本财务报表所采用的货币均为)人民币[。；;]')
            need(re.fullmatch(pattern,plain),'explicit financial report currency')
        else:
            need(scope==INFERRED and e['currency']=='CNY' and 'unit' not in e and
                 e['currency_is_regulatory_inference_not_literal_quote'] is True and e['normative_reference']==CAS19,
                 'labelled exact regulatory basis')
            need(year>=2007 and '遵循企业会计准则的声明' in compact(e['heading_literal'])
                 and e['heading_literal'] in text and 1<=len(literal.splitlines())<=4 and '。' in literal,
                 'bounded same-page affirmative compliance quote')
            need(re.match(r'^(?:本(?:公司|集团)(?:所)?(?:编制的|的)?|公司(?:所)?编制的|本)财务报表符合(?:财政部颁布的)?企业会计准则的(?:要求|规定)[，,。]',plain),
                 'literal Chinese-CAS compliance assertion')
            raw=[s.strip() for s in pages[e['page']-1].splitlines() if s.strip()]
            heading=e['heading_literal'].splitlines()[-1]
            indexes=[i for i,s in enumerate(raw) if s==heading]
            need(len(indexes)==1,'single original heading line')
            nearby=compact('\n'.join(raw[indexes[0]+1:indexes[0]+7]))
            need(not re.search(r'不符合|未遵循|不完全符合|IFRS|香港财务报告准则|国际财务报告准则|但是|但[，,]',nearby,re.I),'no local basis contradiction')
            a=e['statement_scope_anchor'];limit=a['maximum_following_pages']
            need(a['literal'] in direct(a['page']) and a['page']<=e['page']<=a['page']+limit,'direct original post-statement anchor')
            if context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
                need(limit==20 and a['page']==context['end_page_exclusive'] and a['literal']==context['end_literal'],'primary section CAS scope')
            else:need(limit==30 and title(a['literal'])=='母公司利润表','unique parent-income CAS scope')
            if a['page']==e['page']:need(text.index(a['literal'])<text.index(e['heading_literal']),'same-page anchor precedes assertion')
            inferred=True
    return inferred


def main():
    import pypdf
    need(pypdf.__version__=='6.10.0','same registered PDF extractor')
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();root,base,membership,request,run,out=map(lambda x:Path(x).resolve(),
        (a.repo_root,a.source_root,a.membership_file,a.request,a.run_dir,a.output))
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'fresh external audit result')
    need(sha(request)==a.expected_request_sha256,'frozen source request')
    req=read(request)
    need(req['status']=='FROZEN_BEFORE_ALL1236_CAS19_V6_FINANCIAL_SOURCE_INSPECTION' and req['document_count']==1236
         and req['workers']==req['maximum_outstanding_documents']==4 and req['normative_basis']==CAS19
         and req['ranking_or_portfolio_returns_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'source-only full corpus')
    paths=paths_for(req,root,base,membership,request);expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    need(len(paths)==10362,'complete input closure')
    for key,path in paths.items():need(sha(path)==expected[key],'unchanged input before: '+key)
    official=base/'gross-profitability-cas-currency-primary-20261022/cas19'
    need(sha(official/'body.bin')==CAS19['archived_body_sha256'] and sha(official/'text.txt')==CAS19['archived_text_sha256']
         and CAS19['normative_phrase'] in (official/'text.txt').read_text() and '2006年03月09日' in (official/'text.txt').read_text(),'archived official historical statement')
    audits=[('profitability-historical394-v5-source-audit.json','2026-10-22-profitability-v5-source-cells.py',V5),
            ('profitability-fixed12-v4-source-cell-audit.json','2026-10-22-profitability-v4-source-cells.py',FIXED)]
    protected={}
    for filename,code,folder in audits:
        audit=read(root/'experiments/qlib'/filename)
        need(audit['audit_code_sha256']==sha(root/'experiments/qlib/audit_sources'/code),'old separate audit code identity')
        need(inventory(base/folder)==audit['all_output_sha256' if folder==V5 else 'all41_output_sha256'],'unchanged earlier audited results')
        for key,c in read(base/folder/'case_results.json').items():
            if c['source_observations']:
                if key in protected:need(protected[key]['source_observations']==c['source_observations'],'overlap source observation agreement')
                protected[key]=c
    need(len(protected)==182,'all unique old supported originals protected')
    initial=read(base/INITIAL/'documents.json');later=read(base/LATER/'documents.json');cover=read(root/'experiments/qlib/profitability-later-yearless-cover-review.json')
    docs=[]
    for phase,items in (('INITIAL_AUTHENTICATED_PAGE_CACHE',initial),('LATER_ORIGINAL_PDF',later)):
        for raw in items:
            year=raw['fiscal_year']
            if year is None:
                need(raw['capture_key']==cover['capture_key'] and raw['source_sha256']==cover['source_sha256']
                     and cover['manually_viewed_original_cover_render'] is True,'single cover-derived year sidecar')
                year=cover['fiscal_year_from_original_cover'];need(year==2024,'original cover year')
            need(type(year) is int and year<=2024 and raw['day']<='2025-12-31','pre2026 source only')
            docs.append({**raw,'source_phase':phase,'effective_fiscal_year':year,'year_resolved_from_cover_sidecar':raw['fiscal_year'] is None})
    need(docs==req['documents'] and len(initial)==408 and len(later)==828 and len({d['announcement_id'] for d in docs})==1236,'all original editions retained')
    need(set(protected)<={d['capture_key'] for d in docs},'no protected keys silently absent')
    cohort=read(root/'experiments/qlib/profitability-historical394-source-inventory.json')['dated_cohort']
    need(len(cohort)==394 and {d['instrument'] for d in docs}==set(cohort),'same dated394 issuer range')
    outputs=inventory(run)
    cases,summary,terminal=(read(run/name) for name in ('case_results.json','summary.json','terminal.json'))
    need(set(cases)=={d['capture_key'] for d in docs},'complete1236 cases including failures')
    allowed={'input-before.json','input-postcheck.json','terminal.json','case_results.json','summary.json'}
    for start in range(0,len(docs),4):
        name='batch-'+str(start//4).zfill(3)+'.json';allowed.add(name)
        need(read(run/name)=={'capture_keys':[d['capture_key'] for d in docs[start:start+4]]},'original source-order bounded batch')
    counters={'direct_pages':0,'new_cells':0,'observations':0,'new_caches':0,'preserved':0}
    newly_supported=[];regulatory=[];current_only=[]
    money=r'(?<![\d,.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\d,.])'
    for d in docs:
        key=d['capture_key'];case=cases[key];year=d['effective_fiscal_year'];allowed.add(key+'.json')
        need(case==read(run/(key+'.json')) and case['source_sha256']==d['source_sha256'] and case['instrument']==d['instrument']
             and case['fiscal_year']==year and case['raw_capture_fiscal_year']==d['fiscal_year']
             and case['source_phase']==d['source_phase'] and case['year_resolved_from_cover_sidecar']==d['year_resolved_from_cover_sidecar'],'exact source case identity')
        for flag in ('investment_factor_admitted','financial_version_history_complete','historical_arrival_verified',
                     'economic_sector_compatibility_verified','manual_numeric_visual_review_complete'):need(case[flag] is False,'source-only evidence')
        counters['observations']+=len(case['source_observations'])
        if case['status']=='SOURCE_PDF_EXTRACTION_UNSUPPORTED':
            need(case['source_phase']=='LATER_ORIGINAL_PDF' and case['page_count'] is None and case['source_observations']==[]
                 and case['all_extracted_page_text_sha256']=={} and case['error_type'] in ('ValueError','PdfReadError','DependencyError'),'explicit original extraction failure retained')
            continue
        folder=base/CACHE if d['source_phase']=='INITIAL_AUTHENTICATED_PAGE_CACHE' else run
        if folder==run:allowed.add(key+'.pages.json');counters['new_caches']+=1
        cache=read(folder/(key+'.pages.json'));pages=cache['pages']
        hashes={str(i+1):hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(pages)}
        need(cache['source_sha256']==d['source_sha256'] and cache['extractor']=='pypdf6.10.0' and
             case['all_extracted_page_text_sha256']==hashes and case['page_count']==len(pages),'all original/cache page hashes')
        if folder!=run:need(read(folder/(key+'.json'))['all_extracted_page_text_sha256']==hashes,'old authenticated complete cache unchanged')
        identity=source_identity(pages,d['instrument'],year)
        matches=identity['literal_code_evidence'];code_ok=identity['code_consistent'];year_ok=identity['annual_year_consistent']
        need(case['identity_evidence']==identity and case['cover_code_consistent']==code_ok
             and case['cover_annual_year_consistent']==year_ok,'literal token and bounded issuer identity, not guessed year')
        if key in protected:
            old=protected[key]
            need(case['status']==SUPPORTED and case['source_observations']==old['source_observations']
                 and case['source_sha256']==old['source_sha256'] and case['all_extracted_page_text_sha256']==old['all_extracted_page_text_sha256'],'old complete observations/source hashes unchanged')
            counters['preserved']+=1
        if case['status']!=SUPPORTED:
            need(case['status'] in ('SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED') and case['source_observations']==[],'unresolved cases cannot contain values')
            if case['status']=='COVER_IDENTITY_UNVERIFIED':need(not(code_ok and year_ok),'identity failure is explicit')
            continue
        need(code_ok and year_ok and case['source_observations'],'supported source needs both identity guards')
        if any(e['scope']==INFERRED for o in case['source_observations'] for c in o['payload']['cells'].values() for e in c.get('currency_scope_evidence',[])):regulatory.append(key)
        compare=case['source_observations'][0]['payload']['cells']['total_assets']['reported_comparative_balance_date']
        need(compare in (f'{year}-01-01',f'{year-1}-12-31'),'literal opening date')
        periods={f'{year}-12-31'} if compare==f'{year}-01-01' else {f'{year}-12-31',f'{year-1}-12-31'}
        need({o['fiscal_end'] for o in case['source_observations']}==periods and len(case['source_observations'])==len(periods),'no Jan1 to priorDec31 backfill')
        if len(periods)==1:current_only.append(key)
        if key in protected:continue
        newly_supported.append(key)
        reader=pypdf.PdfReader(base/d['source_path']);checked=set()
        need(len(reader.pages)==len(pages),'original physical page count')
        def direct(page):
            need(type(page) is int and 1<=page<=len(pages),'valid physical source page')
            if page not in checked:
                need((reader.pages[page-1].extract_text() or '')==pages[page-1],'direct original PDF page')
                checked.add(page);counters['direct_pages']+=1
            return '\n'.join(t.strip() for t in pages[page-1].splitlines() if t.strip())
        for m in matches:need(m['literal'] in direct(m['physical_page']),'original literal security identity')
        need(any(re.search(annual_title_pattern(year),direct(i+1)) for i in range(min(5,len(pages)))),'direct annual title')
        lines=page_lines(pages)
        for o in case['source_observations']:
            need(o['record_id']==digest({k:v for k,v in o.items() if k!='record_id'}),'complete observation digest')
            need(o['instrument']==d['instrument'] and o['publication_day']==d['day'] and o['observed_at']==d['captured_at_utc']
                 and o['payload']['document_sha256']==d['source_sha256'] and o['payload']['announcement_id']==d['announcement_id'],'source edition and dual timestamps')
            end=datetime.combine(date.fromisoformat(d['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
            need(o['public_day_end_at']==end.isoformat(),'conditional publication-day end, not actual historical arrival')
            need(set(o['payload']['cells'])=={'revenue','cost_of_sales','total_assets'},'exact three fields')
            col=year-int(o['fiscal_end'][:4])
            for field,cell in o['payload']['cells'].items():
                text=direct(cell['page']);row=cell['row_text'];values=re.findall(money,row)
                need(('\n'+text+'\n').count('\n'+row+'\n')==1 and len(row.splitlines())<=4,'exact bounded original monetary row')
                need(len(values)==2 and values[col]==cell['literal'] and cell['column_index']==col and cell['fiscal_end']==o['fiscal_end']
                     and cell['row_text_sha256']==digest(row),'literal current/comparative column')
                labels={'revenue':r'^(?:其中[：:]\s*)?营业收入\s*','cost_of_sales':r'^(?:其中[：:]\s*)?营业成本\s*','total_assets':r'^资产总计\s*'}
                need(re.match(labels[field],row),'literal field, no total-cost/profit proxy')
                statement='合并资产负债表' if field=='total_assets' else '合并利润表'
                following='母公司资产负债表' if field=='total_assets' else '母公司利润表'
                need(cell['statement']==statement,'consolidated statement type')
                context=cell['financial_section_context'];selected=lines
                if context['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
                    need(context['start_literal'] in direct(context['start_page']) and context['end_literal'] in direct(context['end_page_exclusive']),
                         'direct source primary section boundaries')
                    starts=[i for i,(p,t) in enumerate(lines) if p==context['start_page'] and t==context['start_literal']]
                    ends=[i for i,(p,t) in enumerate(lines) if p==context['end_page_exclusive'] and t==context['end_literal']]
                    need(len(starts)==len(ends)==1 and starts[0]<ends[0],'literal ordered primary section')
                    selected=lines[starts[0]:ends[0]]
                else:need(context['kind']=='GLOBAL_UNIQUE_TABLES','known context scope')
                starts=[i for i,(_,t) in enumerate(selected) if title(t)==statement]
                ends=[i for i,(_,t) in enumerate(selected) if title(t)==following]
                need(len(starts)==len(ends)==1 and starts[0]<ends[0],'unique consolidated before parent')
                segment=selected[starts[0]:ends[0]];region='\n'.join(t for _,t in segment)
                need(row in region and segment[0][0]<=cell['page']<=segment[-1][0] and segment[-1][0]-segment[0][0]<=5,'money row within consolidated source table')
                direct(segment[0][0]);direct(selected[ends[0]][0])
                header=cell['header_line'];verify_source_header(header,cell['header_page'],direct,segment)
                suffix=(f'{year}年12月31日'+(f'{year}年1月1日' if compare==f'{year}-01-01' else f'{year-1}年12月31日')) if field=='total_assets' else f'{year}年度{year-1}年度'
                need(compact(header) in ('项目'+suffix,'项目附注'+suffix),'exact explicit two fiscal columns')
                unit=cell['unit'];need(unit in ('元','万元'),'literal monetary unit')
                need(cell['unit_evidence_literal'] in region and segment[0][0]<=cell['unit_evidence_page']<=segment[-1][0],'local unit evidence within consolidated table')
                currency(cell,direct,pages,context,year)
                value=Fraction(cell['literal'].replace(',',''))*(1 if unit=='元' else 10000)
                need(value==Fraction(cell['value_CNY']) and (value>0 if field=='total_assets' else value>=0),'independent rational monetary normalization')
                counters['new_cells']+=1
        print('V6 separate new source cells',len(newly_supported),key,counters['new_cells'],flush=True)
    need(set(outputs)==allowed and len(outputs)==1236+309+5+counters['new_caches'],'complete output file set, no silent extras/missing cases')
    need(summary['status']=='WHOLE1236_V6_SOURCE_INSPECTED_NOT_FACTOR_ADMITTED' and summary['request_sha256']==a.expected_request_sha256
         and summary['document_count']==1236 and summary['source_range_issuer_count']==394
         and summary['input_count']==len(paths) and summary['all_inputs_unchanged'] is True
         and summary['source_gaps_remain_in_full_dated_range'] is True,'complete source summary')
    need(summary['status_counts']==dict(Counter(c['status'] for c in cases.values()))
         and summary['unsupported_error_counts']==dict(Counter(c['error'] for c in cases.values() if 'error' in c))
         and summary['status_counts_by_exchange']=={e:dict(Counter(c['status'] for c in cases.values() if c['instrument'].startswith(e))) for e in ('SH','SZ')}
         and summary['status_counts_by_fiscal_year']=={str(y):dict(Counter(c['status'] for c in cases.values() if c['fiscal_year']==y)) for y in sorted({c['fiscal_year'] for c in cases.values()})},'actual all-source coverage counts')
    complete=sorted({c['instrument'] for c in cases.values() if all(any(other['instrument']==c['instrument'] and other['fiscal_year']==y and other['source_observations'] for other in cases.values()) for y in (2022,2023,2024))})
    need(summary['source_observation_count']==counters['observations'] and summary['old_supported_reports_preserved_identically']==counters['preserved']==182
         and summary['new_page_caches_written']==counters['new_caches'] and summary['regulatory_currency_inference_documents']==regulatory
         and summary['issuers_with_supported_current_reports_2022_2023_2024']==complete
         and summary['supported_source_issuer_count']==len({c['instrument'] for c in cases.values() if c['source_observations']}),'independent source summary reconstruction')
    for flag in ('investment_factor_admitted','financial_version_history_complete','historical_arrival_verified','manual_numeric_visual_review_complete',
                 'economic_sector_compatibility_verified','security_ranking_or_portfolio_returns_computed','2026_financial_or_market_values_read','objective_achieved'):
        need(summary[flag] is False,'unearned evidence/admission flag')
    post={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-before.json')==expected and read(run/'input-postcheck.json')==post and terminal['postcheck']==post
         and terminal['completed_documents']==1236 and terminal['submitted_keys']==[d['capture_key'] for d in docs]
         and terminal['pending']==[] and terminal['original_error'] is None and terminal['persistence_errors']==[],
         'complete original input/terminal journals')
    for key,path in paths.items():need(sha(path)==expected[key],'unchanged input after: '+key)
    need(outputs==inventory(run),'all source outputs unchanged during QA')
    report={'status':'PASS_SEPARATE_ALL1236_V6_CORPUS_AND_SOURCE_CELL_CHECK_NOT_FACTOR_ADMISSION',
        'audit_code_sha256':sha(__file__),'request_sha256':a.expected_request_sha256,'all_input_sha256':expected,'all_output_sha256':outputs,
        'document_count':1236,'dated_source_issuer_count':394,'status_counts':summary['status_counts'],
        'old_supported_reports_preserved_identically':182,'unchanged_old_source_cell_audits_reused':True,
        'newly_supported_documents':newly_supported,'new_literal_monetary_cells_checked':counters['new_cells'],
        'direct_original_PDF_pages_checked':counters['direct_pages'],'new_later_page_caches':counters['new_caches'],
        'regulatory_currency_inference_documents':regulatory,'current_only_Jan1_reports':current_only,
        'three_year_parse_issuer_count_not_investment_universe':len(complete),
        'production_modules_imported':False,'shares_pypdf6100_with_runner':True,'same_researcher_after_run_started_not_blinded':True,
        'full_consolidated_boundary_grammar_independently_reimplemented':False,'every_cached_page_independently_redecoded':False,
        'financial_version_history_complete':False,'historical_arrival_verified':False,'manual_numeric_visual_review_complete':False,
        'economic_sector_compatibility_verified':False,'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_read':False,'objective_achieved':False}
    with out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(report['status'],sha(out),counters,flush=True)


if __name__=='__main__':main()
