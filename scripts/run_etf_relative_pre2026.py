"""One fixed 2024/2025 ETF candidate, two cost profiles; no network or 2026."""
import argparse,json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from stock_rsi.calendar import TradingCalendar
from stock_rsi.etf_relative_replay import CODES,replay
from stock_rsi.raw_share_account import Distribution
from scripts.fundamental_query_journal import file_sha,write_packet_once
from scripts.run_low_risk_raw_share_validation import clean

METHOD_FILES=('scripts/run_etf_relative_pre2026.py','src/stock_rsi/etf_relative_replay.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/broker.py','src/stock_rsi/execution_cost.py',
 'src/stock_rsi/calendar.py','src/stock_rsi/models.py','src/stock_rsi/data.py','src/stock_rsi/time.py',
 'scripts/run_low_risk_raw_share_validation.py','scripts/fundamental_query_journal.py')

def summarize_development(calendar,rows,initial_cash):
 expected=[d.isoformat() for d in calendar.days if 2024<=d.year<=2025]
 if [x['day'] for x in rows]!=expected:raise ValueError('outcome dates differ from authenticated development calendar')
 previous=D(initial_cash);annual={}
 for year in (2024,2025):
  subset=[x for x in rows if x['day'].startswith(str(year))]
  if not subset:raise ValueError('both calendar years required')
  ending=subset[-1]['equity'];peak=previous;maxdd=D(0)
  for x in subset:peak=max(peak,x['equity']);maxdd=min(maxdd,x['equity']/peak-1)
  annual[str(year)]={'net_return':ending/previous-1,'ending_equity':ending,'max_drawdown':maxdd,
   'average_exposure':sum((x['exposure'] for x in subset),D(0))/len(subset),'sessions':len(subset)}
  previous=ending
 return annual


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve prior real-price outputs')
 r=json.loads(Path(a.request).read_text())
 if (file_sha(a.request)!=a.sha256 or r['status']!='FROZEN_ONE_ETF_RELATIVE12M_PRE2026_REPLAY'
  or r['initial_cash_CNY']!='1000000' or r['extra_cost_bps']!=[20,40] or r['candidate_budget']!=1
  or r['research_window']!=['2024-01-01','2025-12-31'] or r['instruments']!=list(CODES)
  or set(r['method_code_sha256'])!=set(METHOD_FILES)
  or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):raise ValueError('frozen replay method or objective changed')
 for field,root in [('local_source_sha256',base),('public_evidence_sha256',repo)]:
  for n,h in r[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(root/n)!=h:raise ValueError('source or evidence bytes changed')
 pricebase=base/'etf-relative-eastmoney-development-20261021';m=json.loads((pricebase/'manifest.json').read_text())
 for n,h in m['artifact_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(pricebase/n)!=h:raise ValueError('captured price artifact changed')
 days=[s.strip() for s in (base/'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines() if '2022-12-01'<=s.strip()<='2025-12-31'];calendar=TradingCalendar(days)
 if len(days)!=749 or days[-1]!='2025-12-31':raise ValueError('frozen749 sessions required')
 bars={d:{} for d in days}
 for code in CODES:
  source=json.loads((pricebase/(code+'-raw.json')).read_text())
  if source['instrument']!=code or source['mode']!='raw' or source['window']!=['2022-12-01','2025-12-31'] or [b['date'] for b in source['bars']]!=days:
   raise ValueError('raw price identity or calendar changed')
  for b in source['bars']:bars[b['date']][code]=b
 review=json.loads((repo/'experiments/qlib/etf-five-cashflows-primary-review.json').read_text());events=[]
 if review['status']!='FIVE_CASH_EVENTS_MATCH_PRIMARY_NOTICES' or len(review['events'])!=5:raise ValueError('five reviewed original events required')
 notices=base/'etf-five-distribution-notices-20261021'
 for e in review['events']:
  if e['instrument'] not in CODES or not '2022-12-01'<=e['ex_date']<='2025-12-31' or file_sha(notices/e['file'])!=e['pdf_sha256']:
   raise ValueError('primary event source identity changed')
  events.append(Distribution(e['event_id'],e['instrument'],date.fromisoformat(e['announced']),date.fromisoformat(e['recorded']),
   date.fromisoformat(e['ex_date']),date.fromisoformat(e['pay_date']),None,D(e['cash_per_unit']),D(0),True))
 out.mkdir(parents=True);summaries={}
 for extra in r['extra_cost_bps']:
  result=replay(calendar,bars,events,extra_cost_bps=extra,initial_cash=r['initial_cash_CNY'])
  if len(result['intents'])!=24:raise ValueError('expected24 monthly formation intents')
  annual=summarize_development(calendar,result['days'],r['initial_cash_CNY'])
  summary={'extra_cost_bps':extra,'base_buy_sell_bps':[5,5],'min_commission_CNY':'5','annual':annual,
    'average_exposure':sum((x['exposure'] for x in result['days']),D(0))/len(result['days']),
    'fills':len(result['fills']),'fees_CNY':sum((D(f['cost']) for f in result['fills']),D(0)),
    'gross_dividends_CNY':sum((x['cash_gross'] for x in result['corporate_ledger'] if x['kind']=='EX_DATE_ENTITLEMENT'),D(0)),
    'numerical_development_screen_passed':all(x['net_return']>0 for x in annual.values()) and all(x['average_exposure']>=D('.9') for x in annual.values()),
    'source_or_execution_admission':False,'candidate_promoted':False,'new_2026_queries':False,'objective_achieved':False}
  write_packet_once(out/('extra'+str(extra)+'-ledger.json'),clean(result));summaries[str(extra)]=clean(summary)
  print('ETF relative12m extra',extra,'bp',json.dumps(clean(annual),ensure_ascii=False),flush=True)
 final={'status':'ETF_RELATIVE12M_PRE2026_DAILY_PROXY_COMPLETE_ADMISSION_SEPARATE','request_sha256':a.sha256,'summaries':summaries,
  'artifact_sha256':{p.name:file_sha(p) for p in out.iterdir() if p.is_file()},'candidate_budget':1,'new_2026_queries':False,
  'historical_arrival_certified':False,'primary_action_completeness_certified':False,'opening_execution_certified':False,'candidate_promoted':False,'objective_achieved':False}
 write_packet_once(out/'summary.json',final);return 0

if __name__=='__main__':raise SystemExit(main())
