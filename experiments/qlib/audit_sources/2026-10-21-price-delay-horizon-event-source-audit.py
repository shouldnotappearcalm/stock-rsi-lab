"""Independent stdlib event/source reconstruction; no project imports or replay.

--self-test-only uses synthetic sources. Actual output reads require the separate
parent notification and an external frozen plan SHA; preparing this file does
not execute the real audit. No factor supplies an entitlement amount.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal as D, ROUND_DOWN
from fractions import Fraction
from pathlib import Path

OLD='price-delay-account-source-events-20261021'
RAW0='price-delay-raw-dev-20261021';RAW='price-delay-raw-horizon-v2-20261021'
PROOF0='price-delay-corporate-reviewed-20261021';PROOF='price-delay-horizon-corporate-reviewed-20261021'
OUT='price-delay-account-horizon-events-20261021'
TARGET0='price-delay-pre2026-formations-20261021/targets.json'
TARGET='price-delay-horizon-formations-20261021/candidate_targets.json'
MIXED='SZ002831|2026-06-04';CASH='SZ000975|2026-04-24'
UNKNOWN={'SH603606|2026-05-26','SZ000937|2026-06-17'}
OLD_UNKNOWN={'SH603596|2024-05-20'}
CAPITAL={'SH601128|2026-06-09','SH603737|2026-06-01','SZ002595|2026-05-11','SH603596|2026-05-11',MIXED}
OLD_AUDIT_SHA='934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201'
RAW_AUDIT_SHA='a7bf3324200deb497ba93327fe41c2d4e6ae7fb5b39d7ed81916aaca91ded753'
RAW_SHA='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490'

def need(value,why):
 if not value:raise ValueError(why)
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def number(s):
 need(isinstance(s,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',s) is not None,'plain nonnegative Decimal source scalar required')
 v=D(s);need(v.is_finite() and v>=0,'invalid scalar');return v

def day(s):
 need(isinstance(s,str) and date.fromisoformat(s).isoformat()==s,'noncanonical source date');return s

def zero(v):return type(v) is int and v==0 or type(v) is list and not v

def path_under(root,name):
 root=Path(root).resolve();p=Path(name)
 need(not p.is_absolute() and '..' not in p.parts,'unsafe source relative path')
 p=(root/p).resolve();need(p.is_relative_to(root),'source symlink escapes root');return p


def reconstruct(packets,proofs,sessions):
 """Construct economics, identity dictionaries and receipts from source rows.

 No account object, production compiler, dataclass or application module used.
 Source ordering is canonical issuer order, vendor row order, supplements last.
 """
 need(not proofs.get('stock_dividend_tax_bases'),'unexpected stock tax proof in this frozen source scope')
 docs={d['file']:d for d in proofs['documents']}
 need(len(docs)==len(proofs['documents']),'duplicate source documents')
 for name,d in docs.items():
  need(Path(name).name==name and re.fullmatch('[0-9a-f]{64}',d['sha256']) and day(d['day'])<=sessions[-1],'bad original PDF identity')
 def bind(p,code,row):
  d=docs[p['source_file']]
  need((d['sha256'],d['instrument'],d['day'])==(p['source_sha256'],code,row['dividPlanDate']),'primary source/PDF/issuer/announcement binding')
  return d['sha256']
 source=[]
 for code,p in sorted(packets.items()):
  need(re.fullmatch('(SH|SZ)[0-9]{6}',code) and p['instrument']==code,'source issuer mismatch')
  source.extend((code,r,'VENDOR_DISTRIBUTION',None) for r in p['distributions'])
 for s in proofs.get('supplementary_distributions',[]):
  need(s['instrument'] in packets,'primary supplement outside source universe')
  source.append((s['instrument'],s['record'],'PRIMARY_NOTICE_SUPPLEMENT',s))
 events=[];receipts=[];seen=set();capital_used=set();v1used=set();v3used=set()
 for code,r,kind,supplement in source:
  need(r['code']==code[:2].lower()+'.'+code[2:],'vendor code mismatch')
  key=code+'|'+day(r['dividOperateDate']);need(key not in seen,'duplicate issuer/ex-date source');seen.add(key)
  primary=[]
  if supplement:primary.append(bind(supplement,code,r))
  cash=number(r['dividCashPsBeforeTax']);stock=number(r['dividStocksPs']);need(stock==0,'unexpected stock dividend without proven tax basis')
  captext=r['dividReserveToStockPs']
  if not captext:
   display=r.get('dividCashStock','')
   need(cash>0 and display.startswith('10派') and '送' not in display and '转' not in display and not r['dividStockMarketDate'],'blank capital is not proven zero')
   captext='0'
  capital=number(captext);verified=False
  if key in proofs.get('capital_tax',{}):
   p=proofs['capital_tax'][key];primary.append(bind(p,code,r));capital_used.add(key)
   need(p.get('verified_exempt') is True and capital>0,'capital tax proof does not match source');verified=True
  announced,recorded,ex=map(day,(r['dividPlanDate'],r['dividRegistDate'],r['dividOperateDate']))
  paid=day(r['dividPayDate']) if r['dividPayDate'] else None
  listed=day(r['dividStockMarketDate']) if r['dividStockMarketDate'] else None
  need(announced<recorded<ex and recorded in sessions and ex in sessions,'source record/ex timing')
  need((cash==0 or paid is not None and paid>=ex) and (capital==0 or listed is not None and listed>=ex),'source pay/list timing')
  identity={'instrument':code,'source_kind':kind,'source_distribution':r,'primary_source_sha256':sorted(set(primary)),
   'effective_stock_taxable_income_per_original_share':'0','capital_tax_exempt_verified':verified,'stock_tax_basis_verified':False}
  eid=digest(identity)
  e={'event_id':eid,'instrument':code,'announced':announced,'recorded':recorded,'ex_date':ex,'pay_date':paid,'listed':listed,
   'cash_per_share':str(cash),'capital_per_share':str(capital),'capital_tax_exempt_verified':verified,
   'stock_per_share':str(stock),'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False}
  receipt={'event_id':eid,'instrument':code,'ex_date':ex,'source_kind':kind,'source_row_sha256':digest(r),
   'primary_source_sha256':sorted(set(primary)),'blank_capital_resolved_as_zero':not bool(r['dividReserveToStockPs']),
   'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not verified)}
  if key in proofs.get('cash_overrides',{}):
   p=proofs['cash_overrides'][key];ph=bind(p,code,r)
   need(proofs['cash_override_contract']=='PRIMARY_NOTICE_CASH_PRECISION_V1' and p.get('verified') is True and
    p.get('kind')=='PRIMARY_NOTICE_CASH_PRECISION' and p['source_row_sha256']==digest(r) and
    kind=='VENDOR_DISTRIBUTION' and stock==capital==0 and listed is None,'V1 source identity/scope')
   expected=number(p['expected_vendor_cash_per_share']);effective=number(p['effective_cash_per_share'])
   quantum=D(1).scaleb(cash.as_tuple().exponent)
   need(cash>0 and expected==cash and effective>cash and effective.quantize(quantum,rounding=ROUND_DOWN)==cash,'V1 primary precision is not source completion')
   correction={'original_event_id':eid,'source_kind':'PRIMARY_CASH_PRECISION_CORRECTION','source_row_sha256':digest(r),
    'primary_source_sha256':ph,'cash_precision_proof_sha256':digest(p),'vendor_cash_per_share':str(cash),'effective_cash_per_share':str(effective)}
   e={**e,'event_id':digest(correction),'cash_per_share':str(effective)}
   receipt={**receipt,'event_id':e['event_id'],'original_event_id':eid,'source_kind':correction['source_kind'],
    'primary_source_sha256':sorted(set(primary+[ph])),'vendor_cash_per_share':str(cash),'effective_cash_per_share':str(effective),'cash_precision_proof_sha256':digest(p)}
   v1used.add(key)
  if key in proofs.get('component_precision_overrides',{}):
   p=proofs['component_precision_overrides'][key];ph=bind(p,code,r)
   need(proofs['component_precision_contract']=='PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1' and key not in proofs.get('cash_overrides',{}) and
    p.get('verified') is True and p.get('kind')=='PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION' and
    p['source_row_sha256']==digest(r) and kind=='VENDOR_DISTRIBUTION' and stock==0 and cash>0 and capital>0 and paid is not None and listed is not None,'V3 source identity/scope')
   for attr,field in {'record_date':'dividRegistDate','ex_date':'dividOperateDate','cash_payment_date':'dividPayDate','stock_listing_date':'dividStockMarketDate'}.items():need(p[attr]==r[field],'V3 date changed')
   need(p['primary_pages'] and all(type(x) is int and x>0 for x in p['primary_pages']) and set(p['components'])=={'cash_per_share','capital_per_share'},'V3 pages/component scope')
   components={};changes={}
   for attr,field in {'cash_per_share':'dividCashPsBeforeTax','capital_per_share':'dividReserveToStockPs'}.items():
    c=p['components'][attr];raw=r[field];effective=number(c['effective_per_share']);per10=number(c['primary_per10_original_shares'])
    need(re.fullmatch(r'[0-9]+\.[0-9]{6}',raw) and raw==c['expected_vendor_per_share'] and D(e[attr])==number(c['expected_vendor_per_share']) and
     effective>0 and per10>0 and effective!=D(raw) and Fraction(effective)==Fraction(per10)/10 and abs(Fraction(effective)-Fraction(D(raw)))<=Fraction(1,2000000),'V3 exact per10/half-unit source precision')
    components[attr]={'vendor_per_share':raw,'effective_per_share':str(effective),'primary_per10_original_shares':str(per10)};changes[attr]=str(effective)
   correction={'original_event_id':eid,'source_kind':'PRIMARY_COMPONENT_PRECISION_CORRECTION','source_row_sha256':digest(r),
    'primary_source_sha256':ph,'component_precision_proof_sha256':digest(p),'components':components}
   e={**e,**changes,'event_id':digest(correction)}
   receipt={**receipt,'event_id':e['event_id'],'original_event_id':eid,'source_kind':correction['source_kind'],
    'component_precision_proof_sha256':digest(p),'precision_components':components,'primary_source_sha256':sorted(set(primary+[ph]))}
   v3used.add(key)
  events.append(e);receipts.append(receipt)
 need(capital_used==set(proofs.get('capital_tax',{})) and v1used==set(proofs.get('cash_overrides',{})) and v3used==set(proofs.get('component_precision_overrides',{})),'orphan source proof')
 return events,receipts


def proof_scope(p):
 need(set(p['capital_tax'])==CAPITAL and set(p['unresolved_tax'])==UNKNOWN and all(p['unresolved_tax'][k]['verified_exempt'] is False for k in UNKNOWN),'unknown tax source guard changed')
 need(set(p['cash_overrides'])=={CASH} and set(p['component_precision_overrides'])=={MIXED} and len(p['supplementary_distributions'])==8 and
  not p['stock_dividend_tax_bases'] and p['strict_statutory_capital_tax_certification'] is False,'frozen precision/proof scope changed')
 for key in (MIXED,'SZ002595|2026-05-11'):need(p['capital_tax'][key]['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE','conditional tax source upgraded')


def same(events,receipts,actual_events,actual_receipts):
 need(events==actual_events and receipts==actual_receipts,'independent economics/dates/IDs/receipts mismatch')


def self_tests():
 code='SZ002831';r={'code':'sz.002831','dividOperateDate':'2026-06-04','dividPlanDate':'2026-05-20','dividRegistDate':'2026-06-03',
  'dividPayDate':'2026-06-04','dividStockMarketDate':'2026-06-04','dividCashPsBeforeTax':'0.803813','dividStocksPs':'0','dividReserveToStockPs':'0.401906','dividCashStock':'10派8.038127转4.019063'}
 doc={'file':'test.pdf','sha256':'a'*64,'instrument':code,'day':'2026-05-20'}
 cp={'source_file':'test.pdf','source_sha256':'a'*64,'verified_exempt':True}
 mixed={'source_file':'test.pdf','source_sha256':'a'*64,'source_row_sha256':digest(r),'verified':True,'kind':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION',
  'record_date':'2026-06-03','ex_date':'2026-06-04','cash_payment_date':'2026-06-04','stock_listing_date':'2026-06-04','primary_pages':[1,2],
  'components':{'cash_per_share':{'expected_vendor_per_share':'0.803813','effective_per_share':'0.8038127','primary_per10_original_shares':'8.038127'},
   'capital_per_share':{'expected_vendor_per_share':'0.401906','effective_per_share':'0.4019063','primary_per10_original_shares':'4.019063'}}}
 p={'documents':[doc],'capital_tax':{MIXED:cp},'component_precision_contract':'PRIMARY_NOTICE_MIXED_COMPONENT_PRECISION_V1','component_precision_overrides':{MIXED:mixed}}
 packets={code:{'instrument':code,'distributions':[r]}};sessions=['2026-06-03','2026-06-04']
 e,rr=reconstruct(packets,p,sessions);need(e[0]['cash_per_share']=='0.8038127' and e[0]['capital_per_share']=='0.4019063' and rr[0]['source_kind']=='PRIMARY_COMPONENT_PRECISION_CORRECTION','synthetic mixed success failed')
 rejected={}
 def reject(label,fn):
  try:fn()
  except (ValueError,KeyError,TypeError):rejected[label]=True
  else:raise AssertionError('negative accepted: '+label)
 q=copy.deepcopy(p);q['documents'][0]['sha256']='b'*64;reject('changed_primary_pdf_hash',lambda:reconstruct(packets,q,sessions))
 q=copy.deepcopy(p);q['supplementary_distributions']=[{'instrument':code,'record':r,**cp}];reject('duplicate_primary_supplement',lambda:reconstruct(packets,q,sessions))
 q=copy.deepcopy(p);q['component_precision_overrides'][MIXED]['components']['cash_per_share']['effective_per_share']='0.7991573';reject('cash_reference_used_as_entitlement',lambda:reconstruct(packets,q,sessions))
 q=copy.deepcopy(p);q['component_precision_overrides'][MIXED]['source_row_sha256']='0'*64;reject('changed_vendor_row_digest',lambda:reconstruct(packets,q,sessions))
 q=copy.deepcopy(e);q[0]['capital_tax_exempt_verified']=False;reject('economics_tax_flag_tampering',lambda:same(e,rr,q,rr))
 scope={'capital_tax':{k:{'evidence_kind':'PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'} for k in CAPITAL},'unresolved_tax':{k:{'verified_exempt':False} for k in UNKNOWN},'cash_overrides':{CASH:{}},'component_precision_overrides':{MIXED:{}},'supplementary_distributions':[{}]*8,'stock_dividend_tax_bases':{},'strict_statutory_capital_tax_certification':False}
 proof_scope(scope);scope['unresolved_tax']['SZ000937|2026-06-17']['verified_exempt']=True;reject('unknown_tax_exemption_upgrade',lambda:proof_scope(scope))
 # Exercise the distinct truncation-completion V1 identity path as well.
 cashrow={**r,'code':'sz.000975','dividOperateDate':'2026-04-24','dividPlanDate':'2026-04-10','dividRegistDate':'2026-04-23','dividPayDate':'2026-04-24','dividStockMarketDate':'','dividCashPsBeforeTax':'0.480402','dividReserveToStockPs':'0','dividCashStock':'10派4.804021'}
 cashdoc={**doc,'instrument':'SZ000975','day':'2026-04-10'}
 cashproof={'source_file':'test.pdf','source_sha256':'a'*64,'source_row_sha256':digest(cashrow),'verified':True,'kind':'PRIMARY_NOTICE_CASH_PRECISION','expected_vendor_cash_per_share':'0.480402','effective_cash_per_share':'0.4804021'}
 cpkt={'SZ000975':{'instrument':'SZ000975','distributions':[cashrow]}}
 cashp={'documents':[cashdoc],'cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1','cash_overrides':{CASH:cashproof}}
 ce,cr=reconstruct(cpkt,cashp,['2026-04-23','2026-04-24'])
 need(ce[0]['cash_per_share']=='0.4804021' and cr[0]['source_kind']=='PRIMARY_CASH_PRECISION_CORRECTION' and cr[0]['original_event_id']!=ce[0]['event_id'],'synthetic V1 success failed')
 q=copy.deepcopy(cashp);q['cash_overrides'][CASH]['effective_cash_per_share']='0.4796827';reject('V1_reference_price_used_as_cash',lambda:reconstruct(cpkt,q,['2026-04-23','2026-04-24']))
 return rejected


def main(argv=None):
 a=argparse.ArgumentParser();a.add_argument('--self-test-only',action='store_true')
 for n in ('source-root','repo-root','plan','expected-plan-sha256','output'):a.add_argument('--'+n)
 args=a.parse_args(argv);neg=self_tests()
 if args.self_test_only:print(json.dumps({'synthetic_negative_controls_rejected':neg,'actual_output_read':False},sort_keys=True));return 0
 need(all(getattr(args,n.replace('-','_')) for n in ('source-root','repo-root','plan','expected-plan-sha256','output')),'actual audit requires explicit frozen inputs/output')
 base=Path(args.source_root).resolve();repo=Path(args.repo_root).resolve();output=Path(args.output);bound={}
 def auth(p,h):
  p=Path(p).resolve();need(re.fullmatch('[0-9a-f]{64}',h) is not None and sha(p)==h,'source bytes changed: '+str(p));bound[str(p)]=h
 auth(args.plan,args.expected_plan_sha256);plan=read(args.plan)
 need(plan['status']=='FROZEN_PRICE_DELAY_HORIZON_APPEND_ONLY_SOURCE_EVENTS_NO_ROI' and plan['window']==['2023-12-29','2026-10-20'] and plan['output_directory']==OUT,'frozen event request scope')
 for field in ('source_queries_allowed','account_replay_to_run','portfolio_returns_to_compute','investment_rule_changes_allowed'):need(plan[field] is False,'frozen no-query/no-replay boundary')
 for field,root in [('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base),('primary_document_sha256',base),('financial_artifact_sha256',base)]:
  for name,h in plan[field].items():auth(path_under(root,name),h)
 need(len(plan['primary_document_sha256'])==32 and len(plan['financial_artifact_sha256'])==48,'all32 primary PDFs and48 original financial artifact bytes')
 raw_request=read(repo/'experiments/qlib/price-delay-horizon-raw-source-request.json')
 need(plan['financial_artifact_sha256']==raw_request['immutable_financial_sha256'],'financial map differs from original frozen request')
 def packets(folder,names,count,last):
  root=base/folder;m=read(root/'manifest.json');cal=read(root/'calendar.json');s=cal['sessions'];auth(root/'calendar.json',m['calendar_sha256'])
  need(len(s)==count and s==sorted(set(s)) and [s[0],s[-1]]==['2023-12-29',last] and len(m['per_code_sha256'])==names,'source scope/calendar changed')
  ps={}
  for code,h in m['per_code_sha256'].items():
   need(re.fullmatch('(SH|SZ)[0-9]{6}',code),'issuer path');p=root/'codes'/(code+'.json');auth(p,h);v=read(p)
   need(v['instrument']==code and v['window']==['2023-12-29',last] and [r['date'] for r in v['bars']]==s,'packet calendar/issuer changed');ps[code]=v
  return m,s,ps
 om,os,old=packets(RAW0,151,486,'2025-12-31');rm,s,full=packets(RAW,203,676,'2026-10-20')
 need(s[:486]==os and set(old)<=set(full) and len(set(full)-set(old))==52,'old/full source universe')
 for code,p in old.items():
  for field,key in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:need([r for r in full[code][field] if r[key]<'2026-01-01']==p[field],'original151 literal source prefix changed')
 auth(base/RAW/'manifest.json',RAW_SHA)
 ra=repo/'experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json';auth(ra,RAW_AUDIT_SHA);r=read(ra)
 need(r['manifest_sha256']==RAW_SHA and r['all203_packets_676_sessions_verified'] is True and r['all151_original_literal_pre2026_prefixes_identical'] is True and zero(r['critical_or_important_findings']) and rm['local_assembly_complete'] is True,'raw independent audit source anchors')
 t=read(base/TARGET);t0=read(base/TARGET0)['price_delay_d1'];idx={d:i for i,d in enumerate(s)}
 need(len(t)==34 and len(t0)==24 and {d:x for d,x in t.items() if d<'2026-01-01'}==t0 and {c for x in t.values() for c in x['weights']}==set(full),'fixed34 targets/old24/203 union')
 need(all(d in idx and idx[d]>0 and x['as_of']==s[idx[d]-1] for d,x in t.items()) and rm['target_sha256']==sha(base/TARGET) and om['target_sha256']==sha(base/TARGET0),'target/calendar snapshot binding')
 olddir=base/OLD;ss=read(olddir/'summary.json');oa=base/'price-delay-event-source-independent-audit-20261021.json';auth(oa,OLD_AUDIT_SHA);old_audit=read(oa)
 need(old_audit['status']=='INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED' and old_audit['events_reconstructed']==378 and old_audit['all378_economics_dates_event_IDs_and_receipts_identical'] is True and old_audit['summary_sha256']==sha(olddir/'summary.json') and old_audit['raw_manifest_sha256']==sha(base/RAW0/'manifest.json') and old_audit['reviewed_manifest_sha256']==sha(base/PROOF0/'reviewed-manifest.json'),'original independent378 audit anchors')
 need(ss['raw_manifest_sha256']==sha(base/RAW0/'manifest.json') and ss['target_sha256']==sha(base/TARGET0) and ss['reviewed_manifest_sha256']==sha(base/PROOF0/'reviewed-manifest.json'),'old source producer provenance')
 for name,h in ss['artifact_sha256'].items():auth(path_under(olddir,name),h)
 oldproof=read(olddir/'effective_proofs.json');oe=read(olddir/'derived_events.json');orr=read(olddir/'event_source_receipts.json')
 old_reconstructed_events,rr=reconstruct(old,oldproof,os);same(old_reconstructed_events,rr,oe,orr);need(len(oe)==len(orr)==378,'original378 length')
 proofdir=base/PROOF;p=read(proofdir/'reviewed-manifest.json');ps=read(proofdir/'summary.json');proof_scope(p)
 pa=read(repo/'experiments/qlib/price-delay-horizon-proof-projection-independent-audit.json')
 need(pa['reviewed_manifest_sha256']==sha(proofdir/'reviewed-manifest.json') and pa['summary_sha256']==sha(proofdir/'summary.json') and pa['all17_PDFs_byte_exact'] is True and pa['all_projected_proof_objects_independently_reconstructed'] is True and zero(pa['critical_or_important_findings']),'independent primary projection anchors')
 need(ps['reviewed_manifest_sha256']==sha(proofdir/'reviewed-manifest.json') and p['raw_manifest_sha256']==ps['raw_manifest_sha256']==RAW_SHA and p['target_sha256']==ps['target_sha256']==sha(base/TARGET) and p['projection_request_sha256']==ps['projection_request_sha256'],'primary projection source links')
 need(set(ps['artifact_sha256'])=={'reviewed-manifest.json'}|{d['file'] for d in p['documents']} and len(ps['artifact_sha256'])==18,'projection artifact completeness')
 for name,h in ps['artifact_sha256'].items():auth(path_under(proofdir,name),h)
 docs={folder+'/'+d['file']:d['sha256'] for folder,q in [(PROOF0,oldproof),(PROOF,p)] for d in q['documents']}
 need(docs==plan['primary_document_sha256'] and len(oldproof['documents'])==15 and len(p['documents'])==17,'complete old15/new17 original PDF map')
 chains=p['source_evidence_chains'];chains=list(chains.values()) if isinstance(chains,dict) else chains;need(len(chains)==17,'source evidence chain coverage')
 for chain in chains:
  need(chain['authenticated_original_files'],'empty original evidence chain')
  for name,h in chain['authenticated_original_files'].items():
   path=Path(name).resolve();need(path.is_relative_to(base) or path.is_relative_to(repo),'original evidence path outside source roots');auth(path,h)
 projected={};ignored=0;vendor=0
 for code,packet in full.items():
  rows=[]
  for r in packet['distributions']:
   ex=day(r['dividOperateDate'])
   if ex<'2026-01-01':ignored+=int(code not in old);continue
   need(ex<=s[-1] and day(r['dividRegistDate'])>='2026-01-01','append event crosses old prefix or cutoff');rows.append(r);vendor+=1
  projected[code]={'instrument':code,'distributions':rows}
 for item in p['supplementary_distributions']:
  r=item['record'];need('2026-01-01'<=day(r['dividRegistDate'])<day(r['dividOperateDate'])<=s[-1],'primary supplement outside append-only dates')
 ne,nr=reconstruct(projected,p,s);events=oe+ne;receipts=orr+nr
 need((vendor,ignored,len(ne),len(events))==(227,131,235,613),'actual source counts differ; no padding')
 unsafe=lambda rows:{r['instrument']+'|'+r['ex_date'] for r in rows if r['requires_zero_record_ownership_if_tax_unverified']}
 need(unsafe(orr)==OLD_UNKNOWN and unsafe(nr)==UNKNOWN and unsafe(receipts)==OLD_UNKNOWN|UNKNOWN,'unknown tax guards changed')
 dest=base/OUT;summary=read(dest/'summary.json');auth(dest/'summary.json',sha(dest/'summary.json'))
 need(summary['plan_sha256']==args.expected_plan_sha256 and summary['raw_manifest_sha256']==RAW_SHA and summary['reviewed_manifest_sha256']==sha(proofdir/'reviewed-manifest.json') and summary['proof_projection_summary_sha256']==sha(proofdir/'summary.json') and summary['target_sha256']==sha(base/TARGET),'compiled source summary links')
 need(set(summary['artifact_sha256'])=={'derived_events.json','event_source_receipts.json','effective_2026_proofs.json','original_derived_events.json','original_event_source_receipts.json'},'compiled artifact set')
 for name,h in summary['artifact_sha256'].items():auth(path_under(dest,name),h)
 same(events,receipts,read(dest/'derived_events.json'),read(dest/'event_source_receipts.json'))
 need(read(dest/'effective_2026_proofs.json')==p and (dest/'original_derived_events.json').read_bytes()==(olddir/'derived_events.json').read_bytes() and (dest/'original_event_source_receipts.json').read_bytes()==(olddir/'event_source_receipts.json').read_bytes(),'effective proof/original378 literal files changed')
 counts=dict(Counter(r['source_kind'] for r in receipts))
 need(summary['source_kind_counts']==counts and summary['compiled_events']==613 and summary['original_events']==378 and summary['vendor_2026_rows']==227 and summary['primary_supplements']==8 and summary['earlier_rows_of_future_only_names_ignored']==131,'compiled source derived summary counts')
 need(summary['source_queries']==0 and summary['account_replay_run'] is False and summary['portfolio_returns_computed'] is False and summary['account_replay_admitted'] is False and summary['actual_zero_record_ownership_verified'] is False and summary['strict_statutory_tax_certification'] is False,'source event output cannot imply financial/tax admission')
 for path,h in bound.items():need(sha(path)==h,'authenticated input/output changed during audit')
 report={'status':'INDEPENDENT_PRICE_DELAY_HORIZON_EVENTS_AND_SOURCE_RECEIPTS_RECONSTRUCTED','plan_sha256':args.expected_plan_sha256,'summary_sha256':sha(dest/'summary.json'),'audit_code_sha256':sha(__file__),
  'raw_manifest_sha256':RAW_SHA,'reviewed_manifest_sha256':sha(proofdir/'reviewed-manifest.json'),
  'derived_events_sha256':sha(dest/'derived_events.json'),'event_source_receipts_sha256':sha(dest/'event_source_receipts.json'),'effective_2026_proofs_sha256':sha(dest/'effective_2026_proofs.json'),
  'events_reconstructed':len(events),'original378_events_and_receipts_identical':True,'all_source_receipts_reconstructed':True,'all_original151_source_prefixes_identical':True,'unknown_tax_guards_preserved':True,
  'all48_original_financial_files_unchanged':True,'all32_original_primary_PDFs_authenticated':True,'vendor_2026_rows':vendor,'primary_supplements':len(p['supplementary_distributions']),'future_only_pre2026_rows_excluded':ignored,
  'source_kind_counts':counts,'all_unverified_tax_event_keys':sorted(unsafe(receipts)),'negative_controls_rejected':neg,'critical_or_important_findings':[],
  'imports_project_code':False,'production_compiler_called':False,'account_replay_run':False,'source_queries':0,'portfolio_returns_computed':False,'source_admitted_for_account_replay':False,
  'limitations':['Source entitlement/identity reconstruction only; no market truth, historical arrival, strict statutory or actual FIFO tax certification.','Conditional premium-source and explicit tax arithmetic evidence remains conditional.','Actual record-date ownership and fractional registry allocation must be checked in the separately gated account phase.','Adjustment factors supply no cash amount; future-only historical rows are excluded.']}
 need(not output.exists(),'preserve prior independent report')
 with output.open('x') as f:json.dump(report,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
 print('independent613 event economics/IDs/receipts match; no account/ROI');return 0

if __name__=='__main__':raise SystemExit(main())
