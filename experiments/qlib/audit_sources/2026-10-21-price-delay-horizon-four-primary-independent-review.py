"""Independent stdlib HTTP/source audit plus fixed manual all-page primary findings."""
import base64,copy,hashlib,json,re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');C=B/'price-delay-horizon-remaining-primary-20261021';P=Path('/tmp/price-delay-four-primary-independent-pages-20261021')
OUT=Path('/tmp/price-delay-horizon-four-primary-independent-review-20261021.json');REQ='70914dee967b00ced4b9e6216d32f56b34d7a8e117c308534e1e85fcfc167818'
ROOT_REVIEW=R/'experiments/qlib/price-delay-horizon-four-primary-content-review.json'
ROOT_REVIEW_SHA='8405862ab4ba8c2c44744a3ec2850dfaec808608b12c418761ec5cb232af3358'

def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def check_chain(identity,reservation,response,pdf,url,reserved_sha):
    assert identity=={'source':'CNINFO_HTTP','url':url,'payload':None,'notice_request_sha256':REQ}
    key=dig(identity);assert reservation['identity_sha256']==key and type(reservation['attempt']) is int and reservation['attempt']==1
    assert response['identity_sha256']==key and response['reservation_sha256']==reserved_sha and response['status']=='CAPTURED'
    payload=response['payload'];assert dig(payload)==response['payload_sha256'] and payload['fields']==['http_response'] and len(payload['rows'])==1
    v=payload['rows'][0];assert v['status']==200 and v['final_url']==url and v['body_complete'] is True and v['body_truncated'] is False and v['read_error_type'] is None and v['read_error'] is None
    raw=base64.b64decode(v['body_base64'],validate=True);assert raw==pdf and raw.startswith(b'%PDF') and len(raw)<=10485760

def facts():
    return {
'SH603605':{'issuer_name':'珀莱雅化妆品股份有限公司','announcement_number':'2026-080','publication_day':'2026-10-12','signature_day':'2026-10-12','record_date':'2026-10-15','ex_date':'2026-10-16','cash_payment_date':'2026-10-16','stock_listing_date':None,'cash_per_original_share_CNY':'1.18','stock_per_original_share':'0','capital_per_original_share':'0','eligible_share_count':'392321960','total_share_count':'395976172','excluded_repurchase_shares':'3654212','issuer_total_cash_CNY':'462939912.80','price_reference_cash_per_share_CNY':'1.17','price_reference_cash_qualifier':'Published approximate diluted reference, not actual eligible-share cash.','price_reference_share_change_ratio':'0','capital_tax_evidence_level':'NOT_APPLICABLE_NO_NONCASH','direct_premium_source_and_no_tax_statement':False,'primary_pages':[1,2,3,4],'field_pages':{'identity':[1,4],'actual_cash':[1,2,3,4],'record_ex_pay':[1,2],'no_stock_capital':[2],'eligible_base_and_reference':[2],'cash_receipt':[2,3],'tax':[3,4]},'notes':['Actual cash1.18 differs from reference1.17; convertible bond conversion price adjustment onp4 is not an A-share entitlement.','Delegated cash through ChinaClear; holders without designated trading wait, and named self-paying holders use separate company payment.']},
'SH603596':{'issuer_name':'芜湖伯特利汽车安全系统股份有限公司','announcement_number':'2026-039','publication_day':'2026-04-30','signature_day':'2026-04-30','record_date':'2026-05-08','ex_date':'2026-05-11','cash_payment_date':'2026-05-11','stock_listing_date':'2026-05-11','cash_per_original_share_CNY':'0.38','stock_per_original_share':'0','capital_per_original_share':'0.48','eligible_share_count':'606513139','total_share_count':'606513139','excluded_repurchase_shares':'0','issuer_total_cash_CNY':'230474992.82','issuer_capital_shares':'291126307','issuer_post_total_shares':'897639446','price_reference_cash_per_share_CNY':None,'price_reference_share_change_ratio':None,'capital_tax_evidence_level':'DIRECT_ISSUER_PREMIUM_SOURCE_AND_TRANSFER_NO_TAX_STATEMENT','direct_premium_source_and_no_tax_statement':True,'primary_pages':[1,2,3,4],'field_pages':{'identity':[1,4],'actual_cash_capital_base':[1,2],'record_ex_pay_list':[1,2],'cash_and_share_receipt':[2],'premium_source_and_transfer_no_tax':[3],'cash_tax':[2,3],'share_structure':[4]},'notes':['p3item6 explicitly says capital reserve originates from share premium issuance and this transfer is not taxed.','This is the2026May11 event only; it does not retroactively upgrade the separate2024 event.','No separate diluted price-reference formula is stated because the notice says no differential distribution.','Published aggregate291126307 is integer;606513139*.48=291126306.72 does not establish investor fractional-share allocation.']},
'SH603606':{'issuer_name':'宁波东方电缆股份有限公司','announcement_number':'2026-024','publication_day':'2026-05-19','signature_day':'2026-05-19','record_date':'2026-05-25','ex_date':'2026-05-26','cash_payment_date':'2026-05-26','stock_listing_date':'2026-05-26','cash_per_original_share_CNY':'0.56','stock_per_original_share':'0','capital_per_original_share':'0.2','eligible_share_count':'685465602','total_share_count':'687715368','excluded_repurchase_shares':'2249766','issuer_capital_shares':'137093120','issuer_post_total_shares':'824808488','price_reference_cash_per_share_CNY':'0.5582','price_reference_share_change_ratio':'0.1993','price_reference_cash_qualifier':'Published approximate all-capital diluted cash/share ratios; distinct from0.56/0.2 actual eligible-share entitlements.','capital_tax_evidence_level':'UNRESOLVED_GENERAL_CAPITAL_RESERVE_ONLY','direct_premium_source_and_no_tax_statement':False,'primary_pages':[1,2,3,4,5],'field_pages':{'identity':[1,5],'actual_cash_capital':[1,2],'record_ex_pay_list':[1,3],'eligible_base_and_reference':[2],'cash_and_share_receipt':[3],'cash_tax':[3,4],'share_structure':[5]},'notes':['All5pages inspected: generic capital reserve transfer, no explicit share-premium source or transfer-tax exemption statement.','Cash tax calculations0.56/0.504 alone are not promoted to a confirmed capital-tax exemption. Unknown remains unresolved.','The account zero-record guard must remain where tax proof is insufficient; this review does not run or waive it.']},
'SZ002831':{'issuer_name':'深圳市裕同包装科技股份有限公司','announcement_number':'2026-036','publication_day':'2026-05-29','signature_day':'2026-05-29','record_date':'2026-06-03','ex_date':'2026-06-04','cash_payment_date':'2026-06-04','stock_listing_date':'2026-06-04','cash_per_original_share_CNY':'0.8038127','cash_per_10_original_shares_CNY':'8.038127','stock_per_original_share':'0','capital_per_original_share':'0.4019063','capital_per_10_original_shares':'4.019063','eligible_share_count':'915182294','total_share_count':'920513500','excluded_repurchase_shares':'5331206','issuer_total_cash_CNY':'735635150.73','issuer_capital_shares':'367817529','issuer_post_total_shares':'1288331029','price_reference_cash_per_share_CNY':'0.7991573','price_reference_share_change_ratio':'0.3995786','price_reference_cash_qualifier':'Per10 whole-capital reference7.991573/3.995786 truncated to6decimals without rounding; divide10 to displayed per-share reference. Not actual eligible-share rights.','capital_tax_evidence_level':'PREMIUM_BALANCE_AND_EXPLICIT_CASH_TAX_AMOUNT_CONDITIONAL_INFERENCE','direct_premium_source_and_no_tax_statement':False,'fractional_share_method':'Largest fractional remainders first; random ordering among equal remainders until total distributed shares match. Not independent per-account floor or round.','primary_pages':[1,2,3,4,5],'field_pages':{'identity':[1,5],'actual_cash_capital':[1,3],'original_proposal_and_premium_balance':[2],'final_eligible_base':[1,2,3],'record_ex':[1,3],'cash_pay_and_share_credit_list':[4],'reference':[1],'tax_FIFOrule_and_amounts':[3],'fractional_allocation':[4],'share_structure':[4]},'notes':['p2 says proposed transfer amount does not exceed capital-reserve/share-premium balance. This supports a conditional source inference, not explicit tracing or a statutory exemption declaration.','p3explicit cash-only tax examples per10:1.607625 at20percent,0.803813 at10percent and net7.234314 at10percent. Rounding applies; these are not extra dividend/share cash values.','FIFO is explicitly described as the issuer tax method, but actual account lots, holding periods and settlement are not certified.','Actual final eligible base915182294 differs from earlier proposed919543954. Final ratios8.038127/4.019063 replace proposed8/4 in document evidence only.','The current compiler/account has NOT been demonstrated to support7-decimal entitlement overrides or fractional registry allocation. Preserve vendor scalars and fail-closed fractional entitlement guard.']}}

def validate_facts(code,d):
    original=facts()[code]
    for k,v in original.items():assert d[k]==v
    assert int(d['total_share_count'])-int(d['eligible_share_count'])==int(d['excluded_repurchase_shares'])
    if code=='SZ002831':
        assert Decimal(d['cash_per_10_original_shares_CNY'])/10==Decimal(d['cash_per_original_share_CNY'])
        assert Decimal(d['capital_per_10_original_shares'])/10==Decimal(d['capital_per_original_share'])

def negative(fn):
    try:fn()
    except (AssertionError,ValueError,KeyError):return True
    raise AssertionError('negative unexpectedly passed')

def main():
    req=read(C/'request.json');assert h(C/'request.json')==REQ==h(R/'experiments/qlib/price-delay-horizon-four-primary-request.json')
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B)]:
        for n,x in req[field].items():assert h(root/n)==x
    m=read(C/'manifest.json');s=read(C/'price-delay-scope.json');assert m['request_sha256']==s['request_sha256']==REQ and s['source_manifest_sha256']==h(C/'manifest.json')
    assert m['capture_complete'] is True and s['capture_complete'] is True and s['postcheck']['frozen_inputs_unchanged'] is True and not m['errors'] and not m['pending_documents'] and m['abnormal_termination'] is False
    assert m['http_query_reservations']==m['maximum_http_queries']==len(list(C.rglob('reserved-*.json')))==len(list(C.rglob('response-*.json')))==4
    assert set(m['documents'])=={x['document_id'] for x in req['documents']}
    files={str(p.relative_to(C)):h(p) for p in C.rglob('*') if p.is_file() and p.name not in ['manifest.json','price-delay-scope.json']};assert files==m['artifact_sha256']
    for k in ['documents_financially_reviewed','historical_arrival_verified','admitted_for_account_replay','portfolio_returns_computed','objective_achieved']:assert m[k] is False
    results=[];chains={};totalpages=0
    for planned in req['documents']:
        key=planned['document_id'];d=m['documents'][key];code=d['instrument'];assert all(d[k]==planned[k] for k in ['instrument','publication_day','url']);pdf=(C/d['file']).read_bytes();assert h(C/d['file'])==d['sha256']
        receipt=d['pdf_receipt'];chainfiles={}
        for k in ['request','reserved','response']:
            p=C/receipt[k+'_file'];assert p.resolve().is_relative_to(C.resolve()) and h(p)==receipt[k+'_sha256'];chainfiles[k]=read(p)
        check_chain(chainfiles['request'],chainfiles['reserved'],chainfiles['response'],pdf,d['url'],receipt['reserved_sha256']);chains[code]=(chainfiles,pdf,d['url'],receipt['reserved_sha256'])
        details=facts()[code];validate_facts(code,details);pages=[];text=[]
        for page in details['primary_pages']:
            tp=P/f'{key}-page-{page}.txt';ip=P/f'{key}-page-{page}.png';text.append(re.sub(r'\s+','',tp.read_text()));pages.append({'page':page,'text':str(tp),'text_sha256':h(tp),'screenshot':str(ip),'screenshot_sha256':h(ip)})
        totalpages+=len(pages);joined=''.join(text)
        assert code[2:] in text[0] and details['announcement_number'] in text[0]
        if code=='SH603605':assert all(x in joined for x in ['1.18','1.17','392,321,960','395,976,172','3,654,212','无送股和转增股本'])
        if code=='SH603596':assert '股票溢价发行所形成的资本公积金' in text[2] and '转增股本不扣税' in text[2]
        if code=='SH603606':assert '溢价' not in joined and '转增股本不扣税' not in joined and '0.5582' in text[1] and '0.1993' in text[1]
        if code=='SZ002831':assert all(x in joined for x in ['8.038127','4.019063','7.991573','3.995786','0.7991573','0.3995786','先进先出','随机排序派发','股本溢价'])
        results.append({**d,**details,'all_pages_independently_text_and_visual_reviewed':True,'page_evidence':pages})
    assert totalpages==18
    rawreqpath=R/'experiments/qlib/price-delay-horizon-raw-source-request.json';assert h(rawreqpath)=='762b77dfed8c2a85e5fbfb7bdc7db149fd4216378230906b6ef8e18aa6ca4160';rawreq=read(rawreqpath)
    assert len(rawreq['immutable_financial_sha256'])==48
    for n,x in rawreq['immutable_financial_sha256'].items():assert h(B/n)==x
    raw=B/'price-delay-raw-horizon-v2-20261021';rm=read(raw/'manifest.json');vendor={}
    for code,d in facts().items():
        p=raw/'codes'/(code+'.json');assert h(p)==rm['per_code_sha256'][code];rows=[x for x in read(p)['distributions'] if x['dividOperateDate']==d['ex_date']]
        assert len(rows)==(0 if code=='SH603605' else 1)
        v={'packet_sha256':h(p),'matching_distribution_count':len(rows),'source_rows':rows}
        if rows:
            row=rows[0];assert row['dividRegistDate']==d['record_date'] and row['dividPayDate']==d['cash_payment_date'] and row['dividStockMarketDate']==d['stock_listing_date']
            v['cash_scalar_minus_primary']=str(Decimal(row['dividCashPsBeforeTax'])-Decimal(d['cash_per_original_share_CNY']));v['capital_scalar_minus_primary']=str(Decimal(row['dividReserveToStockPs'])-Decimal(d['capital_per_original_share']))
        vendor[code]=v
    assert vendor['SZ002831']['cash_scalar_minus_primary']=='3E-7' and vendor['SZ002831']['capital_scalar_minus_primary']=='-3E-7'
    negatives={};cc,pdf,url,rsha=chains['SH603605']
    for field,value,label in [('final_url',url+'?wrong','changed_final_url'),('body_complete',False,'incomplete_body'),('body_base64',base64.b64encode(pdf+b'changed').decode(),'different_HTTP_body')]:
        response=copy.deepcopy(cc['response']);response['payload']['rows'][0][field]=value;response['payload_sha256']=dig(response['payload']);negatives[label]=negative(lambda:check_chain(cc['request'],cc['reserved'],response,pdf,url,rsha))
    for code,k,v,label in [('SH603605','cash_per_original_share_CNY','1.17','cash_replaced_by_reference'),('SH603606','capital_per_original_share','0.1993','capital_replaced_by_diluted_reference'),('SH603606','direct_premium_source_and_no_tax_statement',True,'unresolved_tax_promoted'),('SZ002831','cash_per_original_share_CNY','0.803813','rounded_vendor_cash_used_as_exact'),('SZ002831','capital_per_original_share','0.401906','rounded_vendor_capital_used_as_exact'),('SZ002831','eligible_share_count','919543954','proposal_base_used_instead_of_final'),('SZ002831','capital_tax_evidence_level','DIRECT_EXEMPT','conditional_inference_promoted'),('SH603596','record_date','2026-05-11','ex_date_used_as_record')]:
        changed=copy.deepcopy(facts()[code]);changed[k]=v;negatives[label]=negative(lambda:validate_facts(code,changed))
    assert ROOT_REVIEW_SHA is not None and h(ROOT_REVIEW)==ROOT_REVIEW_SHA
    rootreview=read(ROOT_REVIEW)
    assert rootreview['capture_manifest_sha256']==h(C/'manifest.json') and rootreview['capture_scope_sha256']==h(C/'price-delay-scope.json') and rootreview['request_sha256']==REQ
    assert rootreview['documents_read']==4 and rootreview['pages_text_reviewed']==18 and rootreview['root_critical_pages_visually_reviewed']==9
    rootdocs={x['instrument']:x for x in rootreview['documents']};assert set(rootdocs)==set(facts())
    for record in results:
        code=record['instrument'];rd=rootdocs[code]
        for key in ['issuer_name','announcement_number','publication_day','file','sha256','url','pdf_receipt','record_date','ex_date','cash_payment_date','stock_listing_date','cash_per_original_share_CNY','stock_per_original_share','capital_per_original_share','primary_pages']:
            assert rd[key]==record[key]
        if code!='SH603596':
            for key in ['eligible_share_count','total_share_count','excluded_repurchase_shares','price_reference_cash_per_share_CNY']:assert rd[key]==record[key]
            assert rd['price_reference_capital_per_share']==record['price_reference_share_change_ratio']
        assert rd['root_all_pages_text_reviewed'] is True and rd['root_all_pages_visually_reviewed'] is False and rd['financial_projection_performed'] is False
    assert rootdocs['SH603596']['capital_tax_evidence_kind']=='DIRECT_PREMIUM_SOURCE_AND_NO_TAX_STATEMENT' and rootdocs['SH603596']['applies_only_to_this_2026_event_not_2024'] is True
    assert rootdocs['SH603606']['capital_tax_exemption_candidate'] is False and rootdocs['SH603606']['zero_record_ownership_guard_required_if_unresolved'] is True
    assert rootdocs['SZ002831']['strict_statutory_capital_tax_certification'] is False and rootdocs['SZ002831']['existing_precision_contract_supports_this_mixed_event'] is False and rootdocs['SZ002831']['source_scalar_rounding_algorithm_certified'] is False
    for key in ['source_rows_changed','new_events_compiled','account_registry_rule_changed','capital_tax_flags_upgraded','source_admitted_for_account_replay','portfolio_return_computed','investment_rules_changed','objective_achieved']:assert rootreview[key] is False
    result={'status':'FOUR_PRIMARY_HTTP_CHAINS_AND_ALL18_PAGES_INDEPENDENTLY_REVIEWED_NO_ADMISSION','audit_code_sha256':h(Path(__file__)),'imports_project_code':False,'capture_manifest_sha256':h(C/'manifest.json'),'scope_sha256':h(C/'price-delay-scope.json'),'request_sha256':REQ,'root_content_review_sha256':h(ROOT_REVIEW),'all18_pages_independently_text_extracted_and_visually_reviewed':True,'documents':results,'all4_request_reservation_response_HTTPbody_PDF_chains_verified':True,'all_capture_artifact_hashes_verified':len(files),'all48_original_financial_hashes_unchanged':True,'vendor_comparisons':vendor,'semantic_negative_controls_rejected':negatives,'critical':[],'important':[],'unresolved_evidence':['SH603606 capital-source/tax exemption remains unproved; retain the existing pre-mutation zero-record-ownership gate.','SZ002831 primary7-decimal rights differ from6-decimal vendor scalars; no scalar correction or current compiler support is authorized/certified.','SZ002831 fractional shares require cross-holder remainder allocation with random equal-tail ordering; the independent account fractional-entitlement guard must remain.'],'limitations':['Primary-level economic facts only; no source/account admission, events compiled, policy change, new query or ROI.','SH603596 explicit premium/no-tax evidence is event-specific to2026May11; original2024 unknown is unchanged.','SZ002831 premium-balance+cash-tax-example evidence is conditional inference, not direct no-tax text or independently certified statutory treatment.','Cash delivery clauses state delegated payment and separate self-paying holders; actual investor arrival and FIFO tax settlement remain unverified.','Publication dates bind official URL/signature, not historical first availability.','Actual entitlements and whole-capital price-reference ratios must remain separate; no factor-causality inference.','This script rechecks saved independent text/render artifacts; initial pypdf extraction and all-page visual review occurred separately and are represented by per-page hashes.'],'source_admitted_for_account_replay':False,'new_events_compiled':False,'current_compiler_support_for_precision_or_fractional_allocation_verified':False,'portfolio_returns_computed':False,'objective_achieved':False}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(OUT);print(h(OUT));print('18pages,4chains,48financials,negatives',len(negatives))
if __name__=='__main__':main()
