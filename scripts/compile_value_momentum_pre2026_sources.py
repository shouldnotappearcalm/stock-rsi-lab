"""Authenticated evaluator projection; no account replay or return calculation."""
import argparse,json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from scripts.fundamental_query_journal import file_sha
from scripts.run_low_risk_raw_share_validation import clean,validate_source_coverage
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.listing_anchor_source import project_primary_listing_anchor

RAW='szse-value-momentum-raw-dev-20261021'
PRIMARY='szse-value-momentum-primary-capture-20261021'
TARGET='szse-value-momentum-formations-pre2026-20261021/targets.json'
COMPILED='szse-value-momentum-account-sources-20261021'
OLD_PROOF='budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json'
OLD_RAW='budgeted-residual-raw-dev-20261021'
CONTENT='experiments/qlib/szse-value-momentum-primary-content-review.json'
CAPITAL_KEYS=('SZ002155|2025-06-13','SZ002837|2024-05-27','SZ002837|2025-05-30','SZ002984|2024-04-19')
METHOD_FILES=('scripts/compile_value_momentum_pre2026_sources.py','scripts/run_value_momentum_raw_development.py',
 'src/stock_rsi/listing_anchor_source.py','scripts/replay_budgeted_stock_distribution_targets.py',
 'src/stock_rsi/budgeted_raw_orders.py','src/stock_rsi/budgeted_lot_orders.py','src/stock_rsi/prior_close_orders.py',
 'src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py','src/stock_rsi/broker.py','src/stock_rsi/execution_cost.py',
 'src/stock_rsi/calendar.py','src/stock_rsi/data.py','src/stock_rsi/models.py','src/stock_rsi/time.py',
 'src/stock_rsi/lifecycle_source_rows.py','scripts/run_low_risk_raw_share_validation.py',
 'scripts/run_low_risk_feedback_cost_stress.py','scripts/capture_low_risk_raw_account_data.py',
 'scripts/prepare_qlib_master_market_pre2026.py','scripts/fundamental_query_journal.py')
PUBLIC_FILES=(CONTENT,'experiments/qlib/szse-value-momentum-raw-source-independent-audit.json',
 'experiments/qlib/szse-value-momentum-primary-source-independent-audit.json',
 'experiments/qlib/szse-value-momentum-pre2026-results.json','experiments/qlib/szse-value-momentum-independent-audit.json',
 'docs/research/szse-value-momentum-raw-account-plan-2026-10-21.md')
LOCAL_FILES=(RAW+'/manifest.json',RAW+'/calendar.json',PRIMARY+'/manifest.json',TARGET,OLD_PROOF,OLD_RAW+'/manifest.json')


def read(path):return json.loads(Path(path).read_text())


def load_inputs(base,repo,planfile,expected_sha):
 if file_sha(planfile)!=expected_sha:raise ValueError('fixed source/account plan changed')
 p=read(planfile)
 if (p['status']!='FROZEN_VALUE_MOMENTUM_PRE2026_PHYSICAL_DAILY_DEVELOPMENT'
     or p['candidate']!='szse_value_momentum_equal' or p['initial_CNY']!='1000000'
     or p['extra_cost_bps']!=[20,40] or p['window']!=['2023-12-29','2025-12-31']
     or set(p['method_code_sha256'])!=set(METHOD_FILES)
     or set(p['public_evidence_sha256'])!=set(PUBLIC_FILES) or set(p['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('fixed composite development method/profile scope required')
 for root,mapping in ((repo,p['method_code_sha256']),(repo,p['public_evidence_sha256']),(base,p['local_source_sha256'])):
  for name,h in mapping.items():
   if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root/name)!=h:raise ValueError('frozen source/method bytes changed: '+name)
 audit=read(repo/'experiments/qlib/szse-value-momentum-raw-source-independent-audit.json')
 content=read(repo/CONTENT);m=read(base/RAW/'manifest.json');pm=read(base/PRIMARY/'manifest.json')
 if (audit['capture_complete'] is not True or audit['capture_manifest_sha256']!=file_sha(base/RAW/'manifest.json')
     or content['all_six_originals_byte_authenticated'] is not True
     or content['capture_manifest_sha256']!=file_sha(base/PRIMARY/'manifest.json')
     or content['capture_audit_sha256']!=file_sha(repo/'experiments/qlib/szse-value-momentum-primary-source-independent-audit.json')
     or m['window']!=p['window'] or m['names']!=103 or m['errors_sha256'] or m['pending_codes']
     or pm['errors'] or pm['pending_files'] or len(pm['documents'])!=6
     or file_sha(base/TARGET)!=m['target_sha256'] or file_sha(base/RAW/'calendar.json')!=m['calendar_sha256']):
  raise ValueError('complete independently reviewed source and unchanged target identities required')
 sessions=read(base/RAW/'calendar.json')['sessions']
 if len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=p['window']:
  raise ValueError('complete explicit pre2026 exchange calendar required')
 calendar=TradingCalendar(sessions);packets={}
 for code,h in m['per_code_sha256'].items():
  f=base/RAW/'codes'/(code+'.json')
  if file_sha(f)!=h:raise ValueError('original raw packet changed')
  v=read(f)
  if v['instrument']!=code or v['window']!=p['window']:raise ValueError('raw packet issuer/window changed')
  if code!='SZ001389' and [r['date'] for r in v['bars']]!=sessions:raise ValueError('unexplained nonlisting source calendar gap')
  packets[code]=v
 targets=read(base/TARGET)['szse_value_momentum_equal']
 if len(targets)!=24 or {c for t in targets.values() for c in t['weights']}!=set(packets):raise ValueError('complete fixed24target103name universe required')
 docs=[]
 for d in pm['documents'].values():
  if Path(d['file']).name!=d['file'] or d['day']>'2025-12-31' or file_sha(base/PRIMARY/d['file'])!=d['sha256']:
   raise ValueError('original primary PDF changed')
  docs.append(deepcopy(d))
 reviewed={d['file']:d for d in content['documents']}
 if {d['file']:d['sha256'] for d in docs}!={k:d['sha256'] for k,d in reviewed.items()}:raise ValueError('content review does not bind every original')
 return p,calendar,packets,targets,docs,content


def build_projection(base,calendar,packets,docs,content):
 old=read(base/OLD_PROOF);old_m=read(base/OLD_RAW/'manifest.json')
 if old['raw_manifest_sha256']!=file_sha(base/OLD_RAW/'manifest.json'):raise ValueError('inherited proof raw-source identity changed')
 components={r['case_id']:r for r in old['distribution_component_reviews']}
 inferences={r['event']:r for r in content['four_original_noncash_inferences_preserved']}
 if set(inferences)!=set(CAPITAL_KEYS):raise ValueError('all four inherited interpretations required')
 byfile={d['file']:d for d in docs};capital={}
 for key in CAPITAL_KEYS:
  code,ex=key.split('|');f=base/OLD_RAW/'codes'/(code+'.json')
  if file_sha(f)!=old_m['per_code_sha256'][code] or file_sha(f)!=components[key]['original_source_packet_sha256']:
   raise ValueError('original reviewed distribution packet changed')
  original=[r for r in read(f)['distributions'] if r['dividOperateDate']==ex]
  current=[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
  proof=old['capital_tax'][key];review=inferences[key]
  if (len(original)!=1 or current!=original or proof['source_file']!=review['file']
      or proof['source_sha256']!=review['sha256'] or byfile[proof['source_file']]['sha256']!=review['sha256']
      or proof.get('evidence_kind')!='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'
      or review['classification_retained']!=proof['evidence_kind']
      or proof['verified_exempt'] is not True or review['new_strict_statutory_tax_certification'] is not False):
   raise ValueError('original event rows and inference limits must remain identical')
  capital[key]=deepcopy(proof)
 cash=content['SZ002508_special_cash'];listing=content['SZ001389_listing']
 if (cash['cash_per_original_share_CNY']!='0.50' or cash['price_reference_cash_per_share_CNY']!='0.497403'
     or [cash[k] for k in ('announcement_and_signature_day','record_date','ex_date','cash_payment_date')]
       !=['2024-01-03','2024-01-09','2024-01-10','2024-01-10']
     or listing['listing_date_verified_from_original_primary_text'] is not True
     or listing['primary_stated_listing_date']!='2024-04-02' or listing['issue_price_CNY_per_share']!='17.43'):
  raise ValueError('fixed independently reviewed supplementary cash/listing facts required')
 document=byfile['SZ002508-2024-01-03.pdf']
 supplement={'instrument':'SZ002508','source_file':document['file'],'source_sha256':document['sha256'],
  'record':{'code':'sz.002508','dividPreNoticeDate':'','dividAgmPumDate':'','dividPlanAnnounceDate':'',
   'dividPlanDate':'2024-01-03','dividRegistDate':'2024-01-09','dividOperateDate':'2024-01-10','dividPayDate':'2024-01-10',
   'dividStockMarketDate':'','dividCashPsBeforeTax':'0.50','dividCashPsAfterTax':'','dividStocksPs':'0',
   'dividCashStock':'PRIMARY_NOTICE_CASH_ONLY_10派5元（含税）','dividReserveToStockPs':'0'},
  'source_role':'PRIMARY_NOTICE_SUPPLEMENT_NOT_VENDOR_REWRITE','primary_pages_one_based':[1,2,3,4],
  'price_reference_per_share_not_entitlement':'0.497403'}
 document=byfile['SZ001389-2024-04-01.pdf'];packet=packets['SZ001389']
 anchor={'kind':'PRIMARY_LISTING_UNIT_ADJUSTMENT_ANCHOR','instrument':'SZ001389','listed_on':'2024-04-02',
  'issue_price':'17.43','verified_primary_listing':True,'source_file':document['file'],
  'primary_document_sha256':document['sha256'],'primary_listing_page':13,'primary_issue_price_page':29,
  'source_packet_digest':digest(packet),'initial_adjustment_row_sha256':digest(packet['adjustments'][0])}
 view,anchor_receipt=project_primary_listing_anchor(packet,anchor,[d.isoformat() for d in calendar.days])
 validation=deepcopy(packets);validation['SZ001389']=view
 validation['SZ002508']['distributions'].append(deepcopy(supplement['record']))
 validate_source_coverage(validation)
 lifecycle={'SZ001389':{'kind':'LISTING_BEGIN','effective_date':'2024-04-02','verified_primary_boundary':True,
  'primary_document_sha256':document['sha256'],'source_file':document['file'],'primary_page_one_based':13}}
 proof={'status':'EVALUATOR_ONLY_COMPOSITE_SOURCE_PROJECTION','documents':docs,'capital_tax':capital,
  'cash_overrides':{},'stock_dividend_tax_bases':{},'supplementary_distributions':[supplement],'lifecycles':lifecycle,
  'listing_anchor':anchor,'tax_inferences_unchanged':content['four_original_noncash_inferences_preserved'],
  'historical_arrival_verified':False,'strict_statutory_capital_tax_certification':False,'source_packets_modified':False}
 events,receipts=compile_distribution_events(packets,proof,calendar)
 if len(events)!=255 or sum(r['source_kind']=='PRIMARY_NOTICE_SUPPLEMENT' for r in receipts)!=1:
  raise ValueError('complete254vendor plus1primary event projection required')
 if any(r['requires_zero_record_ownership_if_tax_unverified'] for r in receipts):raise ValueError('unexpected unverified noncash event')
 return proof,events,receipts,anchor_receipt


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 a=p.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('source projection output already exists')
 plan,cal,packets,targets,docs,content=load_inputs(base,repo,a.plan,a.expected_plan_sha256)
 before={c:digest(v) for c,v in packets.items()}
 proof,events,receipts,anchor=build_projection(base,cal,packets,docs,content)
 out.mkdir(parents=True)
 artifacts={'reviewed-manifest.json':proof,'derived_events.json':clean([asdict(e) for e in events]),
  'event_source_receipts.json':list(receipts),'listing_anchor_receipt.json':anchor,'lifecycles.json':proof['lifecycles']}
 for n,v in artifacts.items():(out/n).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
 if before!={c:digest(v) for c,v in packets.items()}:raise ValueError('source projection mutated original packet')
 summary={'status':'FIXED_COMPOSITE_EVALUATOR_PROJECTION_COMPILED_NO_RETURNS','plan_sha256':a.expected_plan_sha256,
  'raw_manifest_sha256':file_sha(base/RAW/'manifest.json'),'primary_capture_manifest_sha256':file_sha(base/PRIMARY/'manifest.json'),
  'target_sha256':file_sha(base/TARGET),'events':len(events),'vendor_events':254,'primary_supplements':1,
  'inherited_capital_tax_inferences':4,'listing_anchors':1,'prelisting_absent_sessions':60,
  'blank_capital_cash_only_receipts':sum(r['blank_capital_resolved_as_zero'] for r in receipts),
  'artifact_sha256':{n:file_sha(out/n) for n in artifacts},'original_packet_digests':before,
  'original_packets_modified':False,'account_replay_performed':False,'portfolio_returns_computed':False,
  'new_source_queries':0,'new_2026_market_queries':False,'full_PIT_or_minute_admission':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('Compiled255 source events and1primary listing anchor; no returns',flush=True)
 return 0

if __name__=='__main__':raise SystemExit(main())
