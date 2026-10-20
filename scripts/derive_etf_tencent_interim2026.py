"""Offline Tencent raw ETF validation, with immutable Eastmoney overlap; no ROI."""
import argparse,base64,json,re
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from bs4 import BeautifulSoup
from scripts.capture_etf_tencent_interim2026 import CODES,START,END,history_url
from scripts.fundamental_query_journal import file_sha,write_packet_once


def parse_wire(raw,code):
 text=raw.decode('utf-8')
 if not text.startswith('kline_day2025='):raise ValueError('registered JSONP assignment required')
 body=json.loads(text[len('kline_day2025='):]);data=body.get('data')
 if body.get('code')!=0 or not isinstance(data,dict) or set(data)!={code.lower()}:
  raise ValueError('Tencent identity or response code changed')
 node=data[code.lower()]
 if not isinstance(node.get('day'),list) or not node['day']:raise ValueError('raw day required; adjusted fallback forbidden')
 dates=[];bars=[];excluded=0
 for fields in node['day']:
  if not isinstance(fields,list) or len(fields)!=11:raise ValueError('Tencent day field layout changed')
  day=fields[0]
  if date.fromisoformat(day).isoformat()!=day or day>END:raise ValueError('invalid or future date')
  dates.append(day)
  if day<START:excluded+=1;continue  # preserve original bytes; do not admit extra earlier prices
  op,close,high,low=(D(x) for x in fields[1:5]);volume=D(fields[5])
  if (any(not x.is_finite() or x<=0 or x!=x.quantize(D('.001')) for x in (op,close,high,low))
   or low>min(op,close) or high<max(op,close) or high<low or not volume.is_finite() or volume<=0):
   raise ValueError('invalid raw OHLC, tick or provider volume')
  bars.append({'date':day,'open':str(op),'close':str(close),'high':str(high),'low':str(low),
   'volume_provider_raw':fields[5],'original_fields':fields})
 if dates!=sorted(set(dates)) or not bars:raise ValueError('duplicate, unordered or absent dates')
 return bars,excluded


def derive_prices(originals,old,prefix):
 if set(originals)!=set(CODES) or set(old)!=set(CODES) or not prefix or prefix!=sorted(set(prefix)):
  raise ValueError('three originals and explicit ordered calendar required')
 packets={};excluded={};common=None;old_common=None
 for c in CODES:
  bars,excluded[c]=parse_wire(originals[c],c);before=[b for b in bars if b['date']<'2026'];after=[b for b in bars if b['date']>='2026']
  expected=old[c];old_dates=[b['date'] for b in expected]
  if not expected or old_dates!=sorted(set(old_dates)) or [b['date'] for b in before]!=old_dates:
   raise ValueError('complete pre2026 overlap date sequence required')
  for x,y in zip(before,expected):
   if any(D(x[k])!=D(y[k]) for k in ('open','close','high','low')):raise ValueError('cross-provider raw OHLC contradiction')
  if old_common is not None and old_dates!=old_common:raise ValueError('old asset calendars disagree')
  old_common=old_dates;days=[b['date'] for b in after]
  if days[:len(prefix)]!=prefix or days[len(prefix):]!=['2026-10-19','2026-10-20']:
   raise ValueError('actual source dates must extend frozen reference by Oct19/20 only')
  if common is not None and days!=common:raise ValueError('three actual source calendars disagree')
  common=days
  packets[c]={'instrument':c,'mode':'raw','window':['2026-01-01',END],'bars':after,
   'evidence_level':'CURRENT_VINTAGE_ETF_PRICE_ENGINEERING_ONLY','volume_unit_verified':False,
   'historical_arrival_certified':False,'corporate_actions_or_adjustment_method_certified':False}
 return packets,common,{'overlap_sessions_each':len(old_common),'all_overlap_raw_OHLC_equal':True,'excluded_pre2025_rows':excluded}


def authenticate(base,name,expected,request=None):
 folder=base/name
 if file_sha(folder/'manifest.json')!=expected:raise ValueError('original manifest changed')
 m=json.loads((folder/'manifest.json').read_text())
 if request and m['request_sha256']!=request:raise ValueError('original request changed')
 for n,h in m['artifact_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(folder/n)!=h:raise ValueError('original artifact changed')
 return folder,m


def closure_endpoints(text):
 match=re.search(r'(\d{1,2})月(\d{1,2})日(?:（[^）]*）)?至(\d{1,2})月(\d{1,2})日(?:（[^）]*）)?休市',re.sub(r'\s+','',text))
 if not match:raise ValueError('complete official closure endpoints missing')
 m1,d1,m2,d2=map(int,match.groups())
 return (date(2026,m1,d1).strftime('%m-%d'),date(2026,m2,d2).strftime('%m-%d'))


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','capture-manifest-sha256','closure-manifest-sha256','old-price-manifest-sha256','reference-calendar-sha256','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);base=Path(a.source_root);out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve previous derivations')
 src,m=authenticate(base,'etf-tencent-interim2026-originals-20261021',a.capture_manifest_sha256,'c415826f21c3a23bf0553cb5df05b48975d58f09f811545a81bc377fc3491ea9')
 closure,cm=authenticate(base,'etf-interim2026-originals-20261021',a.closure_manifest_sha256)
 oldbase,om=authenticate(base,'etf-relative-eastmoney-development-20261021',a.old_price_manifest_sha256)
 if m['captured_documents']!=3 or m['errors'] or set(m['documents'])!=set(CODES):raise ValueError('three complete originals required')
 originals={}
 for c in CODES:
  d=m['documents'][c]
  if d['url']!=history_url(c) or file_sha(src/d['file'])!=d['sha256']:raise ValueError('document identity changed')
  response=json.loads((src/d['HTTP_receipt']['response_file']).read_text());wire=response['payload']['rows'][0]
  if (wire['status']!=200 or not wire['body_complete'] or wire['body_truncated'] or wire['final_url']!=d['url']
   or base64.b64decode(wire['body_base64'])!=(src/d['file']).read_bytes()):raise ValueError('HTTP body provenance differs')
  originals[c]=(src/d['file']).read_bytes()
 ref=base/'low-risk-raw-account-data-20261017/calendar.json'
 if file_sha(ref)!=a.reference_calendar_sha256:raise ValueError('reference calendar changed')
 prefix=[d for d in json.loads(ref.read_text())['sessions'] if d.startswith('2026')]
 if len(prefix)!=188 or prefix[0]!='2026-01-05' or prefix[-1]!='2026-10-16':raise ValueError('188 explicit sessions required')
 old={}
 for c in CODES:
  packet=json.loads((oldbase/(c+'-raw.json')).read_text())
  if packet['instrument']!=c or packet['mode']!='raw':raise ValueError('old raw identity changed')
  old[c]=[b for b in packet['bars'] if b['date'].startswith('2025')]
 packets,days,audit=derive_prices(originals,old,prefix)
 if len(days)!=190 or audit['overlap_sessions_each']!=243:raise ValueError('required243 overlap and190 new observed sessions')
 cd=cm['documents']['sse2026closures'];html=(closure/cd['file']).read_text()
 if cd['url']!='https://www.sse.com.cn/disclosure/dealinstruc/closed/':raise ValueError('wrong closure source')
 soup=BeautifulSoup(html,'html.parser');tables=[t for t in soup.find_all('table') if '元旦' in t.get_text() and '国庆节' in t.get_text()]
 if len(tables)!=1 or '2026年休市安排' not in soup.get_text():raise ValueError('2026 annual closure source missing')
 rows=tables[0].find_all('tr');ranges=[('01-01','01-03','元旦'),('02-15','02-23','春节'),('04-04','04-06','清明节'),('05-01','05-05','劳动节'),('06-19','06-21','端午节'),('09-25','09-27','中秋节'),('10-01','10-07','国庆节')]
 if len(rows)!=7:raise ValueError('closure table layout changed')
 for row,(start,end,label) in zip(rows,ranges):
  text=row.get_text()
  if label not in text or closure_endpoints(text)!=(start,end):raise ValueError('closure facts changed')
  if any('2026-'+start<=d<='2026-'+end for d in days):raise ValueError('observed date contradicts official closure')
 if any(date.fromisoformat(d).weekday()>4 for d in days):raise ValueError('weekend in observed sessions')
 out.mkdir(parents=True)
 for c,packet in packets.items():write_packet_once(out/(c+'-raw.json'),packet)
 write_packet_once(out/'calendar.json',{'sessions':days,'reference_prefix_sha256':a.reference_calendar_sha256,'calendar_inferred_from_weekdays':False,'all_three_actual_price_date_sequences_agree':True,'official_seven_closure_ranges_crosschecked':True})
 result={'status':'TENCENT_RAW_INTERIM2026_DERIVED_OFFLINE_PRICE_REVIEW_PENDING',**audit,'sessions_each':190,'series':3,'window':['2026-01-01',END],
  'capture_manifest_sha256':a.capture_manifest_sha256,'closure_manifest_sha256':a.closure_manifest_sha256,'old_price_manifest_sha256':a.old_price_manifest_sha256,'reference_calendar_sha256':a.reference_calendar_sha256,
  'derivation_method_sha256':file_sha(__file__),'network_queries':0,'portfolio_returns_computed':False,'source_admitted_for_account_replay':False,'historical_arrival_certified':False,'opening_execution_certified':False,'candidate_promoted':False,'objective_achieved':False,
  'artifact_sha256':{q.name:file_sha(q) for q in out.iterdir() if q.is_file()}}
 write_packet_once(out/'summary.json',result);print('190 observed sessions each; 243 raw OHLC overlap sessions equal; no ROI',flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
