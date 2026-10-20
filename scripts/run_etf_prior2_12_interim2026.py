"""One frozen ETF candidate, continuous account, conditional interim diagnostic."""
import argparse,json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from stock_rsi.calendar import TradingCalendar
from stock_rsi.etf_relative_replay import CODES
from stock_rsi.etf_prior2_12 import Prior2To12
from stock_rsi.etf_replay_v2 import replay_with_signal
from stock_rsi.raw_share_account import Distribution
from scripts.run_etf_relative_pre2026 import summarize_development
from scripts.run_low_risk_raw_share_validation import clean
from scripts.fundamental_query_journal import file_sha,write_packet_once
from scripts.run_etf_prior2_12_pre2026 import METHOD_FILES as PARENT_METHOD_FILES
METHOD_FILES=(*PARENT_METHOD_FILES,'scripts/run_etf_prior2_12_interim2026.py')
END='2026-10-20'

def summarize_2026(rows,expected):
 subset=[r for r in rows if r['day'].startswith('2026')]
 before=[r for r in rows if r['day']=='2025-12-31']
 if len(before)!=1 or not subset or [r['day'] for r in subset]!=expected:raise ValueError('continuous account and complete explicit2026 calendar required')
 start=D(before[0]['equity']);peak=start;dd=D(0)
 for r in subset:peak=max(peak,D(r['equity']));dd=min(dd,D(r['equity'])/peak-1)
 return {'starting_equity':start,'ending_equity':D(subset[-1]['equity']),'net_return':D(subset[-1]['equity'])/start-1,
  'average_exposure':sum((D(r['exposure']) for r in subset),D(0))/len(subset),'max_drawdown':dd,'sessions':len(subset),'end':subset[-1]['day'],'full_October':False}

def check_prefix(new,old):
 for key,field in [('days','day'),('intents','execution_session'),('fills','execution_at'),('orders','eligible_at'),('funding_intents','confirmation_session'),('corporate_ledger','day')]:
  if [r for r in new[key] if r[field]<'2026']!=old[key]:raise ValueError('pre2026 full ledger prefix changed: '+key)


def require_development_controls(reproduce,load):
 for extra in (20,40):
  if clean(reproduce(extra))!=load(extra):raise ValueError('development control ledger differs before any2026 replay')


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir);r=json.loads(Path(a.request).read_text())
 if out.exists():raise ValueError('preserve prior diagnostics')
 if (file_sha(a.request)!=a.sha256 or r['status']!='FROZEN_ONE_PRIOR2_12_CONTINUOUS_INTERIM2026_DIAGNOSTIC'
  or r['candidate_id']!='three_domestic_broad_ETF_prior2_12' or r['candidate_budget']!=1 or r['instruments']!=list(CODES)
  or r['end']!=END or r['initial_cash_CNY']!='1000000' or r['extra_cost_bps']!=[20,40] or r['reference_extra_cost_bps']!=40
  or r['reset_account_at_2026'] is not False or r['full_October'] is not False
  or set(r['method_code_sha256'])!=set(METHOD_FILES) or any(file_sha(repo/n)!=h for n,h in r['method_code_sha256'].items())):raise ValueError('frozen method, account or scope changed')
 for field,root in [('local_source_sha256',base),('public_evidence_sha256',repo)]:
  for n,h in r[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(root/n)!=h:raise ValueError('source or evidence changed')
 price=base/'etf-relative-eastmoney-development-20261021';newprice=base/r['new_price_directory']
 for folder,filename in [(price,'manifest.json'),(newprice,'summary.json')]:
  m=json.loads((folder/filename).read_text())
  for n,h in m['artifact_sha256'].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(folder/n)!=h:raise ValueError('price artifact changed')
 ns=json.loads((newprice/'summary.json').read_text())
 if ns['sessions_each']!=190 or ns['overlap_sessions_each']!=243 or ns['all_overlap_raw_OHLC_equal'] is not True:raise ValueError('price overlap not certified')
 olddays=[s.strip() for s in (base/'qlib-enhanced-dev/calendars/day.txt').read_text().splitlines() if '2022-12-01'<=s.strip()<='2025-12-31']
 newdays=json.loads((newprice/'calendar.json').read_text())['sessions'];days=olddays+newdays
 if len(olddays)!=749 or len(newdays)!=190 or days!=sorted(set(days)) or days[-1]!=END:raise ValueError('939 explicit sessions required')
 calendar=TradingCalendar(days);bars={d:{} for d in days}
 for c in CODES:
  for folder,expected in [(price,olddays),(newprice,newdays)]:
   packet=json.loads((folder/(c+'-raw.json')).read_text())
   if packet['instrument']!=c or packet['mode']!='raw' or [b['date'] for b in packet['bars']]!=expected:raise ValueError('price identity/calendar changed')
   for b in packet['bars']:bars[b['date']][c]=b
 events=[]
 for reviewfile,folder,status,count in [('etf-five-cashflows-primary-review.json','etf-five-distribution-notices-20261021','FIVE_CASH_EVENTS_MATCH_PRIMARY_NOTICES',5),
  ('etf-three-2026-cashflows-review.json','etf-2026-cash-notices-rules-20261021','THREE_2026_CASH_EVENTS_MATCH_READ_ORIGINAL_DOCUMENTS_INDEPENDENTLY_REVIEWED',3)]:
  review=json.loads((repo/'experiments/qlib'/reviewfile).read_text())
  if review['status']!=status or len(review['events'])!=count:raise ValueError('reviewed cash facts required')
  for e in review['events']:
   if e['instrument'] not in CODES or file_sha(base/folder/e['file'])!=e['pdf_sha256']:raise ValueError('cash original changed')
   events.append(Distribution(e['event_id'],e['instrument'],date.fromisoformat(e['announced']),date.fromisoformat(e['recorded']),date.fromisoformat(e['ex_date']),date.fromisoformat(e['pay_date']),None,D(e['cash_per_unit']),D(0),True))
 actions=json.loads((base/'etf-interim2026-actions-derived-20261021/summary.json').read_text())
 for c in CODES:
  packet=actions['funds'][c]
  if packet['share_changes']:raise ValueError('unmodelled2026 share change')
 oldcalendar=TradingCalendar(olddays);oldbars={d:bars[d] for d in olddays}
 require_development_controls(lambda extra:replay_with_signal(oldcalendar,oldbars,events,signal_factory=Prior2To12,
  decision_reason='fixed three domestic ETF prior2-12 excluding recent month, prior-close 95% target',extra_cost_bps=extra,initial_cash=r['initial_cash_CNY']),
  lambda extra:json.loads((base/'etf-prior2-12-physical-development-20261021'/('extra'+str(extra)+'-ledger.json')).read_text()))
 out.mkdir(parents=True);summaries={}
 for extra in r['extra_cost_bps']:
  result=replay_with_signal(calendar,bars,events,signal_factory=Prior2To12,decision_reason='fixed three domestic ETF prior2-12 excluding recent month, prior-close 95% target',extra_cost_bps=extra,initial_cash=r['initial_cash_CNY'])
  data=clean(result);old=json.loads((base/'etf-prior2-12-physical-development-20261021'/('extra'+str(extra)+'-ledger.json')).read_text());check_prefix(data,old)
  if len(result['days'])!=675 or len(result['intents'])!=34:raise ValueError('675 outcome sessions and34 monthly intents required')
  dev=summarize_development(TradingCalendar(olddays),[x for x in result['days'] if x['day']<'2026'],r['initial_cash_CNY']);year=summarize_2026(result['days'],newdays)
  passed=all(x['net_return']>0 for x in dev.values()) and year['net_return']>=D('.10')
  summary={'extra_cost_bps':extra,'base_buy_sell_bps':[5,5],'min_commission_CNY':'5','annual':{**dev,'2026_interim':year},
   'pre2026_full_ledger_prefix_reproduced':True,'fills':len(result['fills']),'fees_CNY':sum((D(f['cost']) for f in result['fills']),D(0)),
   'conditional_interim_three_period_numeric_screen_passed':passed,'source_or_execution_admission':False,'full_October':False,'candidate_promoted':False,'objective_achieved':False}
  write_packet_once(out/('extra'+str(extra)+'-ledger.json'),data);summaries[str(extra)]=clean(summary)
  print('Frozen prior2-12 continuous extra',extra,'bp',json.dumps(clean(summary['annual']),ensure_ascii=False),flush=True)
 final={'status':'ONE_PRIOR2_12_CONDITIONAL_DAILY_INTERIM2026_DIAGNOSTIC_COMPLETE_AUDIT_PENDING','request_sha256':a.sha256,
  'candidate_id':r['candidate_id'],'summaries':summaries,'reference_extra_cost_bps':40,'account_reset_at_2026':False,'full_October':False,'historical_arrival_certified':False,'primary_action_completeness_certified':False,'opening_execution_certified':False,'candidate_promoted':False,'objective_achieved':False,
  'artifact_sha256':{q.name:file_sha(q) for q in out.iterdir() if q.is_file()}}
 write_packet_once(out/'summary.json',final);return 0
if __name__=='__main__':raise SystemExit(main())
