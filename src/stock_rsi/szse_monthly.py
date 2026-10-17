"""Data-only reader for original SZSE monthly transaction tables.

The report period, filename build date and assumed usable time are distinct.
This reader does not assert a measured historical arrival timestamp.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, DecimalException
from html.parser import HTMLParser
from pathlib import Path
import unicodedata
from urllib.parse import urljoin, urlsplit, urlunsplit


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def month_shift(month, offset):
    if not re.fullmatch(r'\d{4}-\d{2}', month): raise ValueError('canonical month required')
    year, m = map(int, month.split('-')); date(year,m,1)
    year, m = divmod(year*12+m-1+offset,12)
    return f'{year:04d}-{m+1:02d}'


def decode_source(raw):
    try: return raw.decode('utf-8-sig'), 'utf-8-sig'
    except UnicodeDecodeError: return raw.decode('gb18030'), 'gb18030'


def url_build_day(url):
    p = urlsplit(url)
    if p.query or p.fragment: raise ValueError('unexpected report URL suffix')
    match = re.search(r'(?:/t|/W0)(\d{8})\d*(?:_\d+)?\.html$',p.path)
    if not match: raise ValueError('report filename has no explicit build day')
    d = match[1]; return date(int(d[:4]),int(d[4:6]),int(d[6:8])).isoformat()


class _Links(HTMLParser):
    def __init__(self): super().__init__(); self.active=None; self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.active=[dict(attrs).get('href',''),[]]
    def handle_data(self, value):
        if self.active is not None:self.active[1].append(value)
    def handle_endtag(self, tag):
        if tag=='a' and self.active is not None:
            self.links.append((self.active[0],''.join(self.active[1])));self.active=None


def discover_transaction_url(html, parent_url):
    p = urlsplit(parent_url)
    if p.hostname!='www.szse.cn' or not re.fullmatch(r'/(?:www/)?market/periodical/month/t\d{8}_\d+\.html',p.path):
        raise ValueError('official monthly parent URL required')
    parser=_Links();parser.feed(html)
    links={urljoin(parent_url,href) for href,text in parser.links if re.sub(r'\s','',text)=='证券成交统计'}
    if len(links)!=1: raise ValueError('one explicitly labeled transaction link required')
    p=urlsplit(links.pop())
    if p.hostname!='docs.static.szse.cn' or not re.fullmatch(r'/www/market/periodical/month/W0\d+\.html',p.path):
        raise ValueError('official static transaction table required')
    return urlunsplit(('https',p.netloc,p.path,p.query,p.fragment))


class _Rows(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[[],dict(attrs).get('class','').split()]
    def handle_startendtag(self,tag,attrs):
        if tag in ('td','th') and self.row is not None:self.row.append(('',dict(attrs).get('class','').split()))
    def handle_data(self,data):
        if self.cell is not None:self.cell[0].append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append((''.join(self.cell[0]).strip(),self.cell[1]));self.cell=None
        elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None


def number(value, *, nonnegative=False):
    value=unicodedata.normalize('NFKC',value).replace(',','').strip()
    if value in ('','-','--','—'):return None
    try:n=Decimal(value)
    except DecimalException as exc:raise ValueError('source field is not numeric') from exc
    if not n.is_finite() or nonnegative and n<0:raise ValueError('invalid finite source quantity')
    return str(n)


def parse_transactions(raw, expected_month, *, minimum_mainboard_rows=1000):
    html,encoding=decode_source(raw)
    text=re.sub(r'<[^>]+>',' ',html)
    match=re.search(r'TRANSACTIONS?\s+OF\s+SECURITIES\s*[-—]?\s*[（(]\s*(\d{4})[./-](\d{1,2})',text,re.I)
    if not match or f'{int(match[1]):04d}-{int(match[2]):02d}'!=expected_month:
        raise ValueError('transaction table period differs from registered source month')
    parser=_Rows();parser.feed(html);stocks={};all_rows=0
    expected_classes=[f'c{i}' for i in range(1,9)]+['separator']+[f'c{i}' for i in range(9,16)]
    for row in parser.rows:
        if not row or not re.fullmatch(r'\d{6}',row[0][0]):continue
        all_rows+=1;code=row[0][0]
        if not code.startswith(('000','001','002','003')):continue
        if len(row)!=16 or any(c not in tags for c,(_,tags) in zip(expected_classes,row)):
            raise ValueError('monthly transaction column layout changed')
        r=[value for value,_ in row];instrument='SZ'+code
        if instrument in stocks:raise ValueError('duplicate main-board security in original table')
        name=unicodedata.normalize('NFKC',re.sub(r'\s','',r[1])).upper()
        close=number(r[11],nonnegative=True);pe=number(r[15])
        if pe is not None and Decimal(pe)>0 and (close is None or Decimal(close)<=0):
            raise ValueError('positive published PE without positive reported close')
        stocks[instrument]={'name':r[1],'close':close,'pe':pe,'issued_10k_shares':number(r[2],nonnegative=True),
            'listed_10k_shares':number(r[3],nonnegative=True),'reported_special_name':('ST' in name or '退' in name)}
    if len(stocks)<minimum_mainboard_rows:raise ValueError('full main-board table coverage too small')
    return {'month':expected_month,'encoding':encoding,'all_security_rows':all_rows,'stocks':stocks}


def load_capture(directory, expected_manifest_sha):
    root=Path(directory)
    if sha(root/'manifest.json')!=expected_manifest_sha:raise ValueError('monthly source manifest changed')
    manifest=json.loads((root/'manifest.json').read_text())
    if manifest['status']!='PRE2026_SZSE_MONTHLY_ORIGINAL_TABLES_CAPTURED' or manifest['source_reader_sha256']!=sha(__file__):
        raise ValueError('monthly data reader or capture status changed')
    if sha(root/'request.json')!=manifest['request_sha256']:raise ValueError('monthly source request changed')
    for name,h in manifest['journal_artifact_sha256'].items():
        if sha(root/name)!=h:raise ValueError('source query journal changed')
    result={}
    for month,record in manifest['months'].items():
        for key in ('article','table','normalized'):
            if sha(root/record[key+'_file'])!=record[key+'_sha256']:raise ValueError('monthly source artifact changed')
        packet=json.loads((root/record['normalized_file']).read_text())
        parsed=parse_transactions((root/record['table_file']).read_bytes(),month)
        if any(packet[k]!=v for k,v in parsed.items()):raise ValueError('monthly source parsing differs from saved view')
        if packet['article_build_day']!=url_build_day(record['article_url']) or packet['table_build_day']!=url_build_day(record['table_url']):
            raise ValueError('source filename dates changed')
        result[month]={**packet,'table_sha256':record['table_sha256']}
    return result
