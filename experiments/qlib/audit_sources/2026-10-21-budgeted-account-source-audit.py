"""Authenticate all frozen source bytes, then use the unchanged event compiler.

No portfolio simulation or source correction is performed. Unverified capital
income still requires actual zero record ownership or additional primary proof.
"""
import argparse,hashlib,json
from dataclasses import asdict
from pathlib import Path
from scripts.run_low_risk_raw_share_validation import clean,validate_source_coverage
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler import compile_distribution_events

p=argparse.ArgumentParser()
for n in ('source-root','output-dir'):p.add_argument('--'+n,required=True)
a=p.parse_args();base=Path(a.source_root);repo=Path(__file__).resolve().parents[3];public=repo/'experiments/qlib';out=Path(a.output_dir)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
raw=base/'budgeted-residual-raw-dev-20261021';primary=base/'budgeted-residual-corporate-notices-20261021';proofdir=base/'budgeted-residual-corporate-reviewed-20261021';target=base/'budgeted-residual-development-targets-20261021.json'
for local,name in ((raw/'manifest.json','budgeted-residual-raw-source-capture-manifest.json'),
 (base/'budgeted-residual-raw-source-audit-20261021.json','budgeted-residual-raw-source-audit.json'),
 (primary/'manifest.json','budgeted-residual-corporate-capture-manifest.json'),
 (base/'budgeted-residual-corporate-capture-audit-20261021.json','budgeted-residual-corporate-capture-audit.json'),
 (proofdir/'reviewed-manifest.json','budgeted-residual-corporate-reviewed-manifest.json')):
 assert sha(local)==sha(public/name)
m=read(raw/'manifest.json');proof=read(proofdir/'reviewed-manifest.json');capture=read(primary/'manifest.json');audit=read(base/'budgeted-residual-corporate-capture-audit-20261021.json')
assert m['window']==['2023-12-29','2025-12-31'] and len(m['per_code_sha256'])==210
assert sha(target)==m['target_sha256']==proof['target_sha256']=='df77b351b783f8ef1668f52b94d389999a89ed0cf61ad5ded7e6c21321f10cfc'
assert sha(raw/'calendar.json')==m['calendar_sha256'];sessions=read(raw/'calendar.json')['sessions']
assert sessions==sorted(set(sessions)) and len(sessions)==486 and sessions[0]=='2023-12-29' and sessions[-1]=='2025-12-31'
assert proof['raw_manifest_sha256']==sha(raw/'manifest.json') and proof['capture_manifest_sha256']==sha(primary/'manifest.json')
assert proof['capture_audit_sha256']==sha(base/'budgeted-residual-corporate-capture-audit-20261021.json')
assert audit['capture_manifest_sha256']==sha(primary/'manifest.json') and audit['source_errors']==0 and len(audit['documents'])==13
assert audit['audit_code_sha256']==sha(public/'audit_sources/2026-10-21-budgeted-corporate-capture-audit.py')
assert not capture['errors'] and not capture['pending_cases'] and len(capture['documents'])==13
assert proof['documents']==list(capture['documents'].values()) and len(proof['documents'])==13
for d in proof['documents']:
 assert Path(d['file']).name==d['file'] and sha(proofdir/d['file'])==d['sha256']==sha(primary/d['file'])
 assert '2024-01-01'<=d['day']<='2025-12-31'
assert not proof['cash_overrides'] and not proof['supplementary_distributions'] and not proof['lifecycles'] and not proof['stock_dividend_tax_bases']
assert len(proof['capital_tax'])==10 and len(proof['distribution_component_reviews'])==13
packets={}
for code,h in m['per_code_sha256'].items():
 path=raw/'codes'/(code+'.json');assert sha(path)==h;v=read(path)
 assert v['instrument']==code and v['window']==m['window'] and [r['date'] for r in v['bars']]==sessions
 assert all(r['code']==code[:2].lower()+'.'+code[2:] for r in v['bars'])
 packets[code]=v
assert set(packets)=={c for t in read(target).values() for c in t['weights']}
noncash={c+'|'+r['dividOperateDate']:(c,r) for c,v in packets.items() for r in v['distributions'] if r['dividReserveToStockPs'] and float(r['dividReserveToStockPs'])>0 or r['dividStocksPs'] and float(r['dividStocksPs'])>0}
assert len(noncash)==13 and set(noncash)=={r['case_id'] for r in proof['distribution_component_reviews']}
for item in proof['distribution_component_reviews']:
 code,row=noncash[item['case_id']]
 for k,s in (('cash_per_original_share','dividCashPsBeforeTax'),('stock_per_original_share','dividStocksPs'),('capital_per_original_share','dividReserveToStockPs'),('record_date','dividRegistDate'),('ex_date','dividOperateDate'),('cash_payment_date','dividPayDate'),('capital_listing_date','dividStockMarketDate')):assert item[k]==row[s]
 assert item['original_source_packet_sha256']==m['per_code_sha256'][code]
validate_source_coverage(packets)
events,receipts=compile_distribution_events(packets,proof,TradingCalendar(sessions))
assert len(events)==len(receipts)==sum(len(v['distributions']) for v in packets.values())==510
assert sum(e.capital_per_share>0 for e in events)==13 and sum(e.stock_per_share>0 for e in events)==0
unverified=[r for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']];assert len(unverified)==3
assert {r['instrument'] for r in unverified}=={'SH600161','SH600580','SH603596'}
assert not out.exists();out.mkdir(parents=True)
for name,value in (('derived_events.json',clean([asdict(e) for e in events])),('event_source_receipts.json',receipts)):
 (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
methods=('src/stock_rsi/distribution_event_compiler.py','src/stock_rsi/stock_distribution_account.py','src/stock_rsi/calendar.py','src/stock_rsi/raw_share_account.py','src/stock_rsi/broker.py','src/stock_rsi/data.py','src/stock_rsi/time.py','scripts/run_low_risk_raw_share_validation.py')
result={'status':'ALL210_AUTHENTICATED_510_EVENTS_COMPILED_THREE_TAX_CASES_REQUIRE_ZERO_ENTITLEMENT_OR_PROOF',
 'audit_code_sha256':sha(__file__),'method_code_sha256':{n:sha(repo/n) for n in methods},
 'raw_manifest_sha256':sha(raw/'manifest.json'),'reviewed_manifest_sha256':sha(proofdir/'reviewed-manifest.json'),'target_sha256':sha(target),
 'compiled_events':510,'cash_and_capital_events':13,'verified_capital_tax_exemptions':10,'unverified_capital_tax_events':unverified,
 'verified_stock_dividend_events':0,'source_distribution_rows_modified':False,'adjustment_factors_used_to_infer_income':False,
 'artifact_sha256':{f.name:sha(f) for f in out.iterdir()},'portfolio_returns_computed':False,
 'actual_record_date_entitlements_verified':False,'raw_account_replay_admitted':False,'new_2026_queries':False,'objective_achieved':False}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print('210 sources /510 original distributions compiled; 3 require actual zero entitlement or additional evidence; no ROI')
