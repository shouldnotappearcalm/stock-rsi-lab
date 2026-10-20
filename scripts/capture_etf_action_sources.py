"""Bounded ETF action/rule originals. Only pre2026 action rows are extracted."""
import argparse,base64,fcntl,json,re,time
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,build_opener
import bs4
from bs4 import BeautifulSoup
from scripts.capture_budgeted_corporate_notices_pre2026 import NoRedirect,MAX_BODY,journaled_bytes
from scripts.fundamental_query_journal import QueryJournal,file_sha,write_packet_once

START='2022-12-01';END='2025-12-31'
SOURCES=tuple([{'id':c,'url':'https://fundf10.eastmoney.com/fhsp_'+c[2:]+'.html','kind':'fund_actions','file':c+'.html'}
    for c in ('SH510300','SH510500','SZ159915')]+[
 {'id':'sse_faq','url':'https://www.sse.com.cn/assortment/fund/etf/question/','kind':'rule_html','file':'sse-etf-faq.html'},
 {'id':'szse_trading','url':'https://www.szse.cn/www/investor/warning/t20210104_584079.html','kind':'rule_html','file':'szse-etf-trading.html'},
 {'id':'growth20','url':'https://docs.static.szse.cn/www/aboutus/trends/conference/W020200821767425488573.pdf','kind':'rule_pdf','file':'szse-growth20-list.pdf'},
 {'id':'tax_open_fund','url':'https://fgk.chinatax.gov.cn/zcfgk/c102416/c5202818/content.html','kind':'rule_html','file':'tax-2002-128.html'},
 {'id':'sse_intro','url':'https://etf.sse.com.cn/fund/learning/download/c/10055613/files/32901abf70d54e999f46975b52ba46de.pdf','kind':'rule_pdf','file':'sse-etf-intro.pdf'}])
METHOD_FILES=('scripts/capture_etf_action_sources.py','scripts/capture_budgeted_corporate_notices_pre2026.py','scripts/fundamental_query_journal.py')


def read_wire(url,allowed):
    if url not in allowed or not url.startswith('https://'):raise ValueError('unregistered source URL')
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://fundf10.eastmoney.com/'})
    try:response=build_opener(NoRedirect()).open(req,timeout=20)
    except HTTPError as exc:response=exc
    chunks=[];remaining=MAX_BODY+1;error_type=error=None
    try:
        with response:
            while remaining:
                chunk=response.read(min(65536,remaining))
                if not chunk:break
                if not isinstance(chunk,bytes):raise TypeError('HTTP byte stream required')
                chunks.append(chunk[:remaining]);remaining-=len(chunk[:remaining])
    except Exception as exc:
        partial=getattr(exc,'partial',b'')
        if isinstance(partial,bytes):chunks.append(partial[:remaining])
        error_type,error=type(exc).__name__,str(exc)
    raw=b''.join(chunks);length=response.headers.get('Content-Length')
    if error_type is None and length is not None:
        try:expected=int(length)
        except ValueError:expected=-1
        if expected<0 or len(raw)!=expected:error_type,error='ContentLengthMismatch','incomplete HTTP bytes'
    return ['http_response'],[{'status':response.code,'final_url':response.geturl(),'content_type':response.headers.get('Content-Type',''),
        'body_base64':base64.b64encode(raw).decode(),'body_truncated':len(raw)>MAX_BODY,
        'body_complete':error_type is None and len(raw)<=MAX_BODY,'read_error_type':error_type,'read_error':error}]


def table_grid(table):
    rows=[];carry={}
    for tr in table.find_all('tr'):
        if tr.find_parent('table') is not table:continue
        values={c:v for c,(n,v) in carry.items()};following={c:(n-1,v) for c,(n,v) in carry.items() if n>1};column=0
        for cell in tr.find_all(['td','th'],recursive=False):
            while column in values:column+=1
            span=int(cell.get('colspan',1));height=int(cell.get('rowspan',1))
            if not 1<=span<=10 or not 1<=height<=1000:raise ValueError('unsupported table span')
            text=re.sub(r'\s+','',cell.get_text())
            for c in range(column,column+span):
                if c in values:raise ValueError('overlapping source table cells')
                values[c]=text
                if height>1:following[c]=(height-1,text)
            column+=span
        carry=following
        if values:rows.append([values.get(c,'') for c in range(max(values)+1)])
    if carry:raise ValueError('incomplete table rowspan')
    return rows


def extract_actions(raw,code):
    if code not in ('SH510300','SH510500','SZ159915'):raise ValueError('unregistered ETF')
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    soup=BeautifulSoup(text,'html.parser')
    if soup.title is None or code[2:] not in soup.title.get_text():raise ValueError('fund identity missing from page title')
    divheader=['年份','权益登记日','除息日','每份分红','分红发放日'];splitheader=['年份','拆分折算日','拆分类型','拆分折算比例']
    grids=[table_grid(t) for t in soup.find_all('table')];selected={}
    for kind,header in [('dividends',divheader),('share_changes',splitheader)]:
        matches=[g for g in grids if g and g[0]==header]
        if len(matches)!=1:raise ValueError('unique source '+kind+' table missing')
        selected[kind]=matches[0][1:]
        if not selected[kind]:raise ValueError('empty source action table has unknown history')
    result={'instrument':code,'window':[START,END],'dividends':[],'share_changes':[],
      'provider_asserts_no_dividends':False,'provider_asserts_no_share_changes':False,'outside_window_rows_excluded':0,
      'primary_event_truth_certified':False,'historical_arrival_certified':False,'tax_treatment_certified':False,
      'auxiliary_page_data_excluded_from_decisions':True}
    for kind,rows in selected.items():
        marker='暂无分红信息' if kind=='dividends' else '暂无拆分信息'
        if len(rows)==1 and any(marker in cell for cell in rows[0]):
            result['provider_asserts_no_'+kind]=True;continue
        for row in rows:
            if len(row)!=(5 if kind=='dividends' else 4):raise ValueError('source action row layout changed')
            at=row[2] if kind=='dividends' else row[1]
            date.fromisoformat(at)
            if not START<=at<=END:result['outside_window_rows_excluded']+=1;continue
            if kind=='dividends':
                recorded,pay=row[1],row[4];date.fromisoformat(recorded);date.fromisoformat(pay)
                match=re.fullmatch(r'每份派现金([0-9]+(?:\.[0-9]+)?)元',row[3])
                if not match or not recorded<=at<=pay or D(match[1])<=0:raise ValueError('cash distribution unit or timing unknown')
                result[kind].append({'recorded':recorded,'ex_date':at,'pay_date':pay,'cash_per_unit':match[1]})
            else:result[kind].append({'day':at,'kind_provider_raw':row[2],'ratio_provider_raw':row[3]})
        result[kind].sort(key=lambda r:r['ex_date'] if kind=='dividends' else r['day'])
        ids=[r['ex_date'] if kind=='dividends' else r['day'] for r in result[kind]]
        if len(ids)!=len(set(ids)):raise ValueError('ambiguous duplicate event date')
    return result


def capture_sources(out,sources,request_sha,*,fetch=read_wire,minimum_interval=.3):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():
        m=json.loads((out/'manifest.json').read_text())
        if m['request_sha256']!=request_sha:raise ValueError('terminal request differs')
        for n,h in m['artifact_sha256'].items():
            if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(out/n)!=h:raise ValueError('terminal bytes changed')
        return m
    journal=QueryJournal(out,max_queries=len(sources),max_attempts=1);allowed=tuple(s['url'] for s in sources);docs={};actions={};errors={};next_query=0.
    for s in sources:
        def wire():
            nonlocal next_query
            pause=next_query-time.monotonic()
            if pause>0:time.sleep(pause)
            try:return fetch(s['url'],allowed)
            finally:next_query=time.monotonic()+minimum_interval
        try:
            raw,receipt=journaled_bytes(journal,{'source':'ETF_ACTION_OR_RULE_HTTP','url':s['url'],'scope_sha256':request_sha},wire)
            path=out/s['file']
            if path.exists() and path.read_bytes()!=raw:raise ValueError('original bytes changed')
            if not path.exists():path.write_bytes(raw)
            if s['kind']=='rule_pdf' and not raw.startswith(b'%PDF'):raise ValueError('not an original PDF response')
            docs[s['id']]={**s,'sha256':file_sha(path),'HTTP_receipt':receipt}
            if s['kind']=='fund_actions':
                value=extract_actions(raw,s['id']);write_packet_once(out/(s['id']+'-actions.json'),value);actions[s['id']]=value
        except Exception as exc:errors[s['id']]={'error_type':type(exc).__name__,'error':str(exc)}
    write_packet_once(out/'errors.json',errors)
    m={'status':'ETF_ACTION_AND_RULE_ORIGINALS_CAPTURE_FINISHED_REVIEW_SEPARATE','request_sha256':request_sha,'documents':docs,'actions':actions,
      'errors':errors,'captured_documents':len(docs),'extracted_fund_pages':len(actions),'HTTP_query_reservations':len(list(out.rglob('reserved-*.json'))),
      'artifact_sha256':{str(f.relative_to(out)):file_sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name not in ('capture.lock','manifest.json')},
      'full_pages_may_contain_current_or_2026_auxiliary_content':True,'auxiliary_content_admitted_into_decisions':False,
      'primary_event_truth_certified':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'candidate_promoted':False,'objective_achieved':False}
    write_packet_once(out/'manifest.json',m);return m


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);r=json.loads(Path(a.request).read_text());out=Path(a.output_dir)
    if (file_sha(a.request)!=a.expected_request_sha256 or r['status']!='FROZEN_EIGHT_ETF_ACTION_AND_RULE_SOURCES'
        or r['sources']!=list(SOURCES) or r['maximum_http_queries']!=8 or r['max_attempts_per_identity']!=1
        or r['minimum_interval_seconds']!=.3 or r['maximum_body_bytes']!=MAX_BODY
        or r['extracted_action_window']!=[START,END] or r['bs4_version']!=bs4.__version__
        or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):
        raise ValueError('frozen ETF action source scope/method changed')
    for field,root in [('local_source_sha256',base),('public_evidence_sha256',repo)]:
        for n,h in r[field].items():
            if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(root/n)!=h:raise ValueError('frozen source input changed')
    out.mkdir(parents=True,exist_ok=True);lock=(out/'capture.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        path=out/'request.json'
        if path.exists() and path.read_bytes()!=Path(a.request).read_bytes():raise ValueError('checkpoint request differs')
        if not path.exists():path.write_bytes(Path(a.request).read_bytes())
        m=capture_sources(out,r['sources'],a.expected_request_sha256)
        print('Original ETF source documents',m['captured_documents'],'/8; fundpages',m['extracted_fund_pages'],'/3; errors',list(m['errors']),flush=True)
        return 0 if not m['errors'] else 2
    finally:lock.close()


if __name__=='__main__':raise SystemExit(main())
