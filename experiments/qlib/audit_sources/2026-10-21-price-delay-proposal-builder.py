"""Source-bound proposal only; does not grant account or tax admission."""
from pathlib import Path
from copy import deepcopy
from decimal import Decimal
import json,hashlib,shutil
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REPO=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
primary=BASE/'price-delay-corporate-primary-20261021';capture=read(primary/'manifest.json');docs=capture['documents']
noncash=read('/tmp/price-delay-primary-noncash-content-review-20261021.json');adjust=read('/tmp/price-delay-primary-adjustment-content-review-20261021.json')
assert noncash['request_sha256']==adjust['request_sha256']==capture['request_sha256']
assert adjust['capture_manifest_sha256']==sha(primary/'manifest.json')
assert len(noncash['cases'])==5 and adjust['case_count']==10 and len(docs)==15
for c in noncash['cases']:
 assert c['sha256']==docs[c['case_id']]['sha256'] and c['economic_fields_match_vendor_numerically'] and not c['cash_precision_override_needed']
for key,c in adjust['cases'].items():
 assert c['source_pdf']['sha256']==docs[key]['sha256'] and not c['needs_real_cash_precision_completion'] and not c['second_distribution_at_factor_day_supported']
assert set(c['case_id'] for c in noncash['cases'])|set(adjust['cases'])==set(docs)
for d in docs.values():assert sha(primary/d['file'])==d['sha256'] and d['day']<='2025-12-31'
raw=BASE/'price-delay-raw-dev-20261021';rawm=read(raw/'manifest.json');packets={c:read(raw/'codes'/(c+'.json')) for c in rawm['per_code_sha256']}
oldtaxdir='budgeted-residual-corporate-reviewed-20261021';oldtax=read(BASE/oldtaxdir/'reviewed-manifest.json');capital={}
for c in noncash['cases']:
 key=c['case_id'];code,day=key.split('|');r=next(r for r in packets[code]['distributions'] if r['dividOperateDate']==day)
 assert Decimal(r['dividCashPsBeforeTax'])==Decimal(c['cash_per_original_entitled_share_CNY'])
 assert Decimal(r['dividReserveToStockPs'])==Decimal(c['capital_per_original_entitled_share'])
 if code=='SH603596':assert key not in oldtax['capital_tax'];continue
 proof=deepcopy(oldtax['capital_tax'][key]);assert proof['source_sha256']==docs[key]['sha256']
 if code=='SZ002155':assert proof['evidence_kind']=='PREMIUM_SOURCE_AND_EXPLICIT_TAX_AMOUNT_INFERENCE'
 else:assert c['issuer_explicit_capital_transfer_no_tax_statement']
 capital[key]=proof
routes={'SH600167|2024-12-27':'illiquidity-corporate-reviewed-20261020','SH600482|2024-11-22':'return-family-corporate-notices-20261017','SZ002508|2024-01-10':'szse-value-corporate-notices-20261017'}
supplements=[]
for key,directory in routes.items():
 code,day=key.split('|');source=read(BASE/directory/'reviewed-manifest.json')
 candidates=[s for s in source['supplementary_distributions'] if s['instrument']==code and s['record']['dividOperateDate']==day];assert len(candidates)==1;s=deepcopy(candidates[0]);f=adjust['cases'][key]['primary_economic_facts'];r=s['record']
 assert s['source_file']==docs[key]['file'] and s['source_sha256']==docs[key]['sha256']
 assert Decimal(r['dividCashPsBeforeTax'])==Decimal(f['cash_per_eligible_original_share_gross'])
 assert [r[k] for k in ('dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate')]==[docs[key]['day'],f['record_day'],f['ex_day'],f['cash_payment_day']]
 assert Decimal(r['dividStocksPs'])==Decimal(r['dividReserveToStockPs'])==0
 assert not any(v['dividOperateDate']==day for v in packets[code]['distributions'])
 supplements.append(s)
relationships=[]
for key,c in adjust['cases'].items():
 if c['needs_new_primary_cash_event_because_vendor_row_missing']:continue
 f=c['primary_economic_facts'];relationships.append({'instrument':key.split('|')[0],'adjustment_source_day':key.split('|')[1],'notice_confirmed_ex_date':f['ex_day'],'notice_confirmed_pay_date':f['cash_payment_day'],'source_file':docs[key]['file'],'source_sha256':docs[key]['sha256'],'vendor_dividend_record':c['related_existing_vendor_distribution'],'adjustment_date_semantics_verified':False,'additional_entitlement_inferred_from_adjustment':False,'classification':'NOTICE_SUPPORTS_EXISTING_EARLIER_DIVIDEND_DOES_NOT_EXPLAIN_VENDOR_LATER_FACTOR_LABEL'})
assert len(relationships)==7 and len(capital)==4 and len(supplements)==3
proposal={'status':'PRICE_DELAY_SOURCE_REVIEW_PROPOSAL_NOT_ACCOUNT_ADMISSION','raw_manifest_sha256':sha(raw/'manifest.json'),'target_sha256':rawm['target_sha256'],'capture_manifest_sha256':sha(primary/'manifest.json'),'capture_audit_sha256':sha(REPO/'experiments/qlib/price-delay-primary-capture-independent-audit.json'),'proposal_builder_sha256':sha(Path(__file__)),'documents':list(docs.values()),'capital_tax':capital,'unknown_capital_tax':['SH603596|2024-05-20'],'strict_statutory_capital_tax_certification':False,'direct_primary_capital_tax_statements':3,'conditional_capital_tax_inferences':1,'stock_dividend_tax_bases':{},'supplementary_distributions':supplements,'cash_overrides':{},'cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1','adjustment_relationships':relationships,'inherited_source_manifests':{n+'/reviewed-manifest.json':sha(BASE/n/'reviewed-manifest.json') for n in sorted({oldtaxdir,*routes.values()})},'lifecycles':{},'tax_model':'FIXED20PCT_CASH_STRESS_NOT_FIFO; retain4original event flags; unproved noncash requires zero record inventory','fractional_allocation_supported':False,'source_provider_packets_modified':False,'documents_are_point_in_time_arrival_certification':False,'corporate_action_completeness_certified':False,'all375_vendor_distributions_independently_primary_verified':False,'event_compilation_admitted':False,'admitted_for_account_replay':False,'portfolio_returns_computed':False,'new_2026_market_queries':False,'objective_achieved':False}
review={'status':'FIFTEEN_PRIMARY_CONTENT_REVIEWS_BOUND_TO_CAPTURE_NOT_ACCOUNT_ADMISSION','capture_manifest_sha256':sha(primary/'manifest.json'),'scoped_primary_content_review_completed':True,'documents_read':15,'pages_read':noncash['complete_pages_text_and_visual_reviewed']+adjust['complete_text_pages_read'],'visually_reviewed_full_pages':noncash['complete_pages_text_and_visual_reviewed']+adjust['visually_reviewed_full_page_count'],'noncash_review_file':'experiments/qlib/price-delay-primary-noncash-content-review.json','noncash_review_sha256':sha('/tmp/price-delay-primary-noncash-content-review-20261021.json'),'adjustment_review_file':'experiments/qlib/price-delay-primary-adjustment-content-review.json','adjustment_review_sha256':sha('/tmp/price-delay-primary-adjustment-content-review-20261021.json'),'all15_PDF_sha256':{k:d['sha256'] for k,d in docs.items()},'unsupported_tax_exemption_added':False,'new_cash_precision_overrides':0,'supplementary_cash_events':3,'unexplained_factor_date_labels':7,'formal_account_admission':False}
assert review['pages_read']==54 and review['visually_reviewed_full_pages']==41
out=BASE/'price-delay-corporate-reviewed-20261021';assert not out.exists();out.mkdir()
for d in docs.values():shutil.copyfile(primary/d['file'],out/d['file']);assert sha(out/d['file'])==d['sha256']
(out/'reviewed-manifest.json').write_text(json.dumps(proposal,indent=2,ensure_ascii=False)+'\n')
for src,name in [('/tmp/price-delay-primary-adjustment-content-review-20261021.json','price-delay-primary-adjustment-content-review.json')]:shutil.copyfile(src,REPO/'experiments/qlib'/name)
(REPO/'experiments/qlib/price-delay-primary-content-review.json').write_text(json.dumps(review,indent=2)+'\n')
shutil.copyfile(out/'reviewed-manifest.json',REPO/'experiments/qlib/price-delay-corporate-reviewed-manifest.json')
print('15PDF source proposal:54 textpages,41 visualpages;4taxflags unchanged,1unknown;3supplements;no ROI')
