"""Independent stdlib chain/prefix audit, with separately extracted visually reviewed four-page evidence."""
import base64,copy,hashlib,json,re
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
C=B/'price-delay-horizon-missing-primary-20261021';P=Path('/tmp/price-delay-SH603233-independent-pages-20261021');OUT=Path('/tmp/price-delay-horizon-single-primary-independent-review-20261021.json')
REQ='194e1c2514fe97fb0c0f16757ce3a4199e9bf3d60b2bff6f1862945bb32fa7f0';URL='https://static.cninfo.com.cn/finalpage/2026-10-12/1225600412.PDF'
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def chain(identity,reservation,response,pdf,reservation_sha):
    expected={'source':'CNINFO_HTTP','url':URL,'payload':None,'request_sha256':REQ}
    assert identity==expected
    key=dig(identity);assert reservation['identity_sha256']==key and type(reservation['attempt']) is int and reservation['attempt']==1
    assert response['identity_sha256']==key and response['reservation_sha256']==reservation_sha and response['status']=='CAPTURED'
    payload=response['payload'];assert response['payload_sha256']==dig(payload)
    assert payload['fields']==['http_response'] and len(payload['rows'])==1
    row=payload['rows'][0]
    assert row['status']==200 and row['final_url']==URL and row['body_complete'] is True and row['body_truncated'] is False and row['read_error_type'] is None and row['read_error'] is None
    data=base64.b64decode(row['body_base64'],validate=True);assert len(data)<=10*1024*1024 and data.startswith(b'%PDF') and data==pdf

def validate_economics(d):
    expected={'instrument':'SH603233','issuer_name':'大参林医药集团股份有限公司','announcement_number':'2026-055','publication_day':'2026-10-12','signature_day':'2026-10-12','record_date':'2026-10-16','ex_date':'2026-10-19','cash_payment_date':'2026-10-19','cash_per_original_share_CNY':'0.41','stock_per_original_share':'0','capital_per_original_share':'0','eligible_share_count':'1132170028','total_share_count':'1138892282','excluded_repurchase_shares':'6722254','price_reference_cash_per_share_CNY':'0.41'}
    assert all(d[k]==v for k,v in expected.items())
    assert int(d['total_share_count'])-int(d['eligible_share_count'])==int(d['excluded_repurchase_shares'])
    assert 'approximate' in d['price_reference_cash_qualifier'] and d['capital_tax_exemption_claimed'] is False and d['stock_tax_basis_claimed'] is False
    return expected

def negative(fn):
    try:fn()
    except (AssertionError,ValueError,KeyError):return True
    raise AssertionError('negative control passed unexpectedly')

def main():
    req=read(C/'request.json');assert h(C/'request.json')==REQ==h(R/'experiments/qlib/price-delay-horizon-single-primary-request.json')
    assert req['url']==URL and req['maximum_http_queries']==req['max_attempts']==1
    assert h(R/req['protocol_file'])==req['protocol_sha256']
    for mapping,root in [('method_code_sha256',R),('local_source_sha256',B)]:
        for n,x in req[mapping].items():assert h(root/n)==x
    m=read(C/'manifest.json');assert m['request_sha256']==REQ and m['capture_complete'] is True and m['source_inputs_unchanged_after_capture'] is True and m['errors']=={} and set(m['documents'])=={'SH603233'}
    for k in ['documents_financially_reviewed','source_admitted_for_account_replay','historical_arrival_verified','portfolio_returns_computed','investment_rules_changed','objective_achieved']:assert m[k] is False
    d=m['documents']['SH603233'];receipt=d['pdf_receipt'];files={}
    for k in ['request','reserved','response']:
        p=C/receipt[k+'_file'];assert p.resolve().is_relative_to(C.resolve()) and h(p)==receipt[k+'_sha256'];files[k]=read(p)
    assert len(list(C.rglob('reserved-*.json')))==len(list(C.rglob('response-*.json')))==m['http_query_reservations']==1
    pdf=(C/d['file']).read_bytes();assert h(C/d['file'])==d['sha256']=='6bc1e1c5fe3f61008331fddabbfa7d6d6aed3146c0448e1e232e8dcedf559dff'
    chain(files['request'],files['reserved'],files['response'],pdf,receipt['reserved_sha256'])
    assert Path(receipt['request_file']).parent.name==dig(files['request'])
    public=R/'experiments/qlib/price-delay-horizon-single-primary-content-review.json';assert h(public)=='b20a662cc6149c96397089a769f3e43dd96b85039c13ea544441cb4a17c6285f'
    review=read(public);assert review['capture_manifest_sha256']==h(C/'manifest.json') and review['request_sha256']==REQ and review['pages_read']==4 and len(review['documents'])==1
    rd=review['documents'][0];facts=validate_economics(rd)
    for k,v in d.items():assert rd[k]==v
    text=[re.sub(r'\s+','',(P/f'page-{i}.txt').read_text()) for i in range(1,5)]
    assert all(v in text[0] for v in ['603233','2026-055','A股每股现金红利0.41元','2026/10/16','2026/10/19'])
    assert all(v in text[1] for v in ['无送股和转增分配','1,132,170,028','1,138,892,282','6,722,254','≈0.41元/股'])
    assert all(v in text[2] for v in ['暂不扣缴所得税','实际转让股票','20%','10%','暂免征收个人所得税','0.369元'])
    assert '2026年10月12日' in text[3]
    rawreq=read(R/'experiments/qlib/price-delay-horizon-raw-source-request.json');raw=B/'price-delay-raw-horizon-20261021';rm=read(raw/'manifest.json')
    assert h(R/'experiments/qlib/price-delay-horizon-raw-source-request.json')=='762b77dfed8c2a85e5fbfb7bdc7db149fd4216378230906b6ef8e18aa6ca4160'==h(raw/'request.json')
    assert h(B/'price-delay-raw-dev-20261021/manifest.json')==rawreq['local_source_sha256']['price-delay-raw-dev-20261021/manifest.json']
    assert rm['names']==202 and len(rm['per_code_sha256'])==202 and list(rm['errors_sha256'])==['SH603233'] and not rm['pending_codes'] and rm['query_reservations_consumed']==345 and rm['admitted_for_account_replay'] is False
    assert h(raw/'errors/SH603233.json')==rm['errors_sha256']['SH603233']
    assert read(raw/'price-delay-scope.json')['capture_complete'] is False
    for n,x in rawreq['immutable_financial_sha256'].items():assert h(B/n)==x
    assert len(rawreq['immutable_financial_sha256'])==48
    old=B/'price-delay-raw-dev-20261021';prefix=0
    for c,x in rawreq['original_packet_sha256'].items():
        op=old/'codes'/(c+'.json');assert h(op)==x
        if c in rm['per_code_sha256']:
            np=raw/'codes'/(c+'.json');assert h(np)==rm['per_code_sha256'][c];a,b=read(op),read(np)
            for k,f in [('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')]:assert [v for v in b[k] if v[f]<='2025-12-31']==a[k]
            prefix+=1
    assert len(rawreq['original_packet_sha256'])==151
    negatives={}
    changed=copy.deepcopy(files['response']);changed['payload']['rows'][0]['final_url']=URL+'?changed';changed['payload_sha256']=dig(changed['payload'])
    negatives['coherently_rehashed_wrong_final_url']=negative(lambda:chain(files['request'],files['reserved'],changed,pdf,receipt['reserved_sha256']))
    changed=copy.deepcopy(files['response']);changed['payload']['rows'][0]['body_base64']=base64.b64encode(pdf+b'changed').decode();changed['payload_sha256']=dig(changed['payload'])
    negatives['coherently_rehashed_HTTP_body_differs_from_PDF']=negative(lambda:chain(files['request'],files['reserved'],changed,pdf,receipt['reserved_sha256']))
    changed=copy.deepcopy(files['reserved']);changed['attempt']=2
    negatives['second_attempt_rejected']=negative(lambda:chain(files['request'],changed,files['response'],pdf,receipt['reserved_sha256']))
    changed=copy.deepcopy(files['response']);changed['payload']['rows'][0]['body_complete']=False;changed['payload_sha256']=dig(changed['payload'])
    negatives['coherently_rehashed_partial_body_rejected']=negative(lambda:chain(files['request'],files['reserved'],changed,pdf,receipt['reserved_sha256']))
    for k,v,label in [('cash_per_original_share_CNY','0.40758','diluted_reference_not_actual_cash'),('record_date','2026-10-19','wrong_record_date'),('stock_per_original_share','0.1','invented_stock_ratio'),('eligible_share_count','1138892282','repurchase_shares_included')]:
        x=copy.deepcopy(rd);x[k]=v;negatives[label]=negative(lambda:validate_economics(x))
    reference=Fraction(1132170028*41,1138892282*100)
    result={'status':'INDEPENDENT_ONE_PRIMARY_CHAIN_AND_ALL_FOUR_PAGES_REVIEW_PASS_NO_ADMISSION','audit_code_sha256':h(Path(__file__)),'imports_project_code':False,'capture_manifest_sha256':h(C/'manifest.json'),'request_sha256':REQ,'primary_pdf_sha256':d['sha256'],'root_content_review_sha256':h(public),'all4pages_independently_text_extracted_and_visually_reviewed':True,'pages':[{'page':i,'text_file':str(P/f'page-{i}.txt'),'text_sha256':h(P/f'page-{i}.txt'),'screenshot':str(P/f'page-{i}.png'),'screenshot_sha256':h(P/f'page-{i}.png')} for i in range(1,5)],'verified_primary_fields':facts,'reference_cash':{'actual_eligible_share_cash':'0.41','published_approximate_all_capital_reference':'0.41','notice_formula_exact_rational':str(reference),'notice_formula_decimal_diagnostic':str(Decimal(reference.numerator)/Decimal(reference.denominator)),'diagnostic_is_not_new_cash_entitlement_or_factor_mapping':True},'receipt':receipt,'one_exact_query_reservation_and_response_verified':True,'postcheck_inputs_reauthenticated':True,'original_151_packet_hashes_unchanged':True,'successful_assembled_original_prefixes_literal_equal':prefix,'all48_original_financial_hashes_unchanged':True,'raw_capture_202_of203_failure_preserved':True,'semantic_negative_controls_rejected':negatives,'critical':[],'important':[],'minor':[],'limitations':['Cash0.41 is for eligible ordinary registered holders. Repurchased shares are excluded; named self-paying holders have separate payment handling.','The notice delegates distribution through ChinaClear; designated trading holders can receive on payment day, undesignated holders wait. This does not independently certify investor receipt.','Personal/fund tax is deferred until share transfer and holding-period based:20percent up to1month,10percent over1month through1year,temporary exemption over1year. This is issuer notice evidence, not independent tax-law advice, FIFO lot validation or actual liability certification.','Publication/signature day is Oct12 from captured official URL and notice; historical first availability remains uncertified.','No factor economic causality, coordinate consistency or complete company-action coverage is proved by this PDF review.','All4pages visually reviewed independently; no internet, project code import, account replay, portfolio ROI or source mutation.'],'source_admitted_for_account_replay':False,'new_events_compiled':False,'portfolio_returns_computed':False,'objective_achieved':False}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(OUT);print(h(OUT));print('originalprefixes',prefix,'negatives',len(negatives),'reference',result['reference_cash'])
if __name__=='__main__':main()
