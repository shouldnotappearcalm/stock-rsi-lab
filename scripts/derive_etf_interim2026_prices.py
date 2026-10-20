"""Offline raw interim2026 price derivation; no returns, network or new sessions."""
import argparse,json
from decimal import Decimal as D
from pathlib import Path
from scripts.capture_etf_interim2026_sources import START,END,CODES,history_url
from scripts.fundamental_query_journal import file_sha,write_packet_once

def parse_history(body,code,mode,sessions):
    history_url(code,mode)
    data=body.get('data')
    if (body.get('rc')!=0 or not isinstance(data,dict) or data.get('code')!=code[2:]
            or data.get('market')!=(1 if code.startswith('SH') else 0) or not data.get('klines')):
        raise ValueError('historical ETF identity or series missing')
    output=[]
    for line in data['klines']:
        fields=line.split(',')
        if len(fields) not in (11,12):raise ValueError('historical field layout changed')
        day=fields[0];op,close,high,low=(D(x) for x in fields[1:5]);volume=D(fields[5]);amount=D(fields[6])
        if (not START<=day<=END or any(not x.is_finite() or x<=0 for x in (op,close,high,low))
                or low>min(op,close) or high<max(op,close) or high<low
                or not volume.is_finite() or volume<=0 or volume!=volume.to_integral_value()
                or not amount.is_finite() or amount<=0
                or mode=='raw' and any(x!=x.quantize(D('.001')) for x in (op,close,high,low))):
            raise ValueError('invalid date,OHLC,tick,volume or amount')
        output.append({'date':day,'open':str(op),'close':str(close),'high':str(high),'low':str(low),
                       'volume_provider_raw':fields[5],'amount_provider_raw':fields[6],'original_fields':fields})
    if [r['date'] for r in output]!=sessions:raise ValueError('complete explicit calendar coverage required; duplicates/future/gaps forbidden')
    return {'instrument':code,'mode':mode,'window':[START,END],'bars':output,
            'evidence_level':'CURRENT_VINTAGE_ETF_PRICE_ENGINEERING_ONLY','volume_unit_verified':False,
            'corporate_actions_or_adjustment_method_certified':False,'historical_arrival_certified':False}



def derive_prices(originals,reference_prefix):
 if set(originals)!=set(CODES) or reference_prefix!=sorted(set(reference_prefix)) or not reference_prefix:
  raise ValueError('three fixed originals and ordered explicit calendar prefix required')
 first=json.loads(originals[CODES[0]])
 if not isinstance(first.get('data'),dict) or not isinstance(first['data'].get('klines'),list):raise ValueError('calendar source missing')
 sessions=[line.split(',')[0] for line in first['data']['klines']]
 if (sessions!=sorted(set(sessions)) or not sessions or sessions[0]!='2026-01-05' or sessions[-1]!=END
  or sessions[:len(reference_prefix)]!=reference_prefix or sessions[len(reference_prefix):]!=['2026-10-19','2026-10-20']):
  raise ValueError('observed ETF dates do not extend frozen explicit prefix')
 packets={c:parse_history(json.loads(originals[c]),c,'raw',sessions) for c in CODES}
 return packets,sessions

def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','capture-manifest-sha256','reference-calendar-sha256','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);base=Path(a.source_root);source=base/'etf-interim2026-originals-20261021';ref=base/'low-risk-raw-account-data-20261017/calendar.json';out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve previous offline derivation')
 if file_sha(source/'manifest.json')!=a.capture_manifest_sha256 or file_sha(ref)!=a.reference_calendar_sha256:raise ValueError('source identity changed')
 m=json.loads((source/'manifest.json').read_text())
 if m['captured_documents']!=4 or m['errors']:raise ValueError('all four bounded sources must first be captured')
 for n,h in m['artifact_sha256'].items():
  if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(source/n)!=h:raise ValueError('captured original bytes changed')
 old=json.loads(ref.read_text());prefix=[d for d in old['sessions'] if d.startswith('2026')]
 if len(prefix)!=188 or prefix[-1]!='2026-10-16':raise ValueError('authenticated188-session reference required')
 raw={c:(source/m['documents'][c]['file']).read_bytes() for c in CODES}
 packets,sessions=derive_prices(raw,prefix)
 if len(sessions)!=190:raise ValueError('expected190 actual source sessions')
 out.mkdir(parents=True)
 for c,packet in packets.items():write_packet_once(out/(c+'-raw.json'),packet)
 write_packet_once(out/'calendar.json',{'sessions':sessions,'reference_prefix_sha256':a.reference_calendar_sha256,
  'calendar_inferred_from_weekdays':False,'all_three_actual_price_date_sequences_agree':True,'official_closure_crosscheck_pending':True})
 result={'status':'THREE_RAW_ETF_INTERIM2026_SERIES_DERIVED_OFFLINE_CLOSURE_AND_ACTION_REVIEW_PENDING',
  'capture_manifest_sha256':a.capture_manifest_sha256,'reference_calendar_sha256':a.reference_calendar_sha256,
  'derivation_method_sha256':file_sha(__file__),'imported_scope_method_sha256':file_sha(Path(__file__).with_name('capture_etf_interim2026_sources.py')),
  'series':3,'sessions_each':len(sessions),'window':[START,END],'calendar_inferred_from_weekdays':False,'network_queries':0,
  'artifact_sha256':{p.name:file_sha(p) for p in out.iterdir() if p.is_file()},'portfolio_returns_computed':False,
  'source_admitted_for_account_replay':False,'historical_arrival_certified':False,'opening_execution_certified':False,
  'candidate_promoted':False,'objective_achieved':False}
 write_packet_once(out/'summary.json',result)
 print('Three raw ETF series',len(sessions),'observed sessions each; offline only, no portfolio ROI',flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
