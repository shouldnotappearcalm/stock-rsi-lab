"""Independent Fraction verification of four pre-existing coordinate proofs.
Read-only saved packets/PDF receipts; no production coordinate function/import,
network, economic inference from factors, account or ROI calculation.
"""
from pathlib import Path
from fractions import Fraction as Q
import base64,copy,hashlib,json,re
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
V=B/'szse-value-momentum-raw-full-v2-20261021';PRIMARY=B/'szse-value-momentum-primary-2026-gaps-20261021';REVIEW=R/'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'
OUT=Path('/tmp/price-delay-horizon-existing-coordinate-reuse-audit-20261021.json')
ROOTS=['reversal-raw-full-20261017','szse-value-raw-full-20261017'];CODES=['SZ002608','SZ002756'];HALF=Q(1,2000000)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(v,s):
    if not v:raise AssertionError(s)
def text(v):return str(v.numerator)+'/'+str(v.denominator)
def six(s):
    need(isinstance(s,str) and re.fullmatch(r'[0-9]+\.[0-9]{6}',s) is not None,'published six decimal factor');q=Q(s);need(q>HALF,'positive factor interval');return q
def rowsby(rows,key):
    keys=[r[key] for r in rows];need(keys==sorted(set(keys)),'unique ordered source rows');return dict(zip(keys,rows))
def normalized_daily(r):return [r['date'],r['code'],*[Q(r[k]) if r[k] else None for k in ['open','high','low','close','preclose','volume','amount']],r['tradestatus'],r['isST'],r['adjustflag']]
def require_intersection(lower,upper,published):need(lower<=published+HALF and upper>=published-HALF,'sixdecimal exact rounding intervals disjoint')
def main():
    vm=read(V/'manifest.json');plan=read(V/'request.json');checks=read(V/'coordinate_checks.json');reviews=read(REVIEW);primary=read(PRIMARY/'manifest.json');docs={d['instrument']:d for d in reviews['documents']}
    need(sha(V/'request.json')==vm['request_sha256'] and sha(V/'coordinate_checks.json')==vm['coordinate_checks_sha256'],'V2request/check proof hashes')
    publicrequest=R/'experiments/qlib/szse-value-momentum-raw-reassembly-v2-request.json';prior_audit=B/'szse-value-momentum-raw-reassembly-v2-audit-20261021.json'
    need(sha(publicrequest)==sha(V/'request.json') and read(prior_audit)['raw_manifest_sha256']==sha(V/'manifest.json'),'public frozen V2request and prior independent audit anchors')
    need(sha(PRIMARY/'manifest.json')==vm['primary_manifest_sha256']==plan['local_source_sha256']['szse-value-momentum-primary-2026-gaps-20261021/manifest.json'] and sha(REVIEW)==vm['primary_content_review_sha256']==plan['public_evidence_sha256']['experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'],'seven-notice content/PDFmanifest bindings')
    need(len(docs)==7 and set(docs)==set(primary['documents']) and primary['capture_complete'] is True and not primary['errors'] and not primary['pending'],'complete existingsevennotice capture/content review')
    method='scripts/reassemble_value_momentum_raw_extension_v2.py';need(sha(R/method)==plan['method_code_sha256'][method],'existing V2method hash without invoking it')
    v1=B/vm['source_query_receipts_relative_to'];need(sha(v1/'manifest.json')==vm['v1_manifest_sha256'],'saved V1response manifest')
    pdfbindings={};rawreceipts={};packetbindings={};pairresults=[];manifests={root:read(B/root/'manifest.json') for root in ROOTS};touched={str(V/'manifest.json'):sha(V/'manifest.json'),str(V/'coordinate_checks.json'):sha(V/'coordinate_checks.json'),str(V/'request.json'):sha(V/'request.json'),str(PRIMARY/'manifest.json'):sha(PRIMARY/'manifest.json'),str(REVIEW):sha(REVIEW)}
    for code in CODES:
        vp=V/'codes'/(code+'.json');need(sha(vp)==vm['per_code_sha256'][code],'V2packet hash');full=read(vp);touched[str(vp)]=sha(vp);review=docs[code];doc=primary['documents'][code]
        need(full['instrument']==code and full['window']==['2023-12-29','2026-10-20'] and full['provenance']['kind']=='LOCAL_ONLY_V2_FORE_COORDINATE_REASSEMBLY' and full['provenance']['factor_values_normalized_or_rewritten'] is False,'V2literal mixed-prefix provenance')
        need(all(review[k]==doc[k] for k in ['instrument','file','sha256','publication_day']) and full['provenance']['primary_notice_sha256']==review['sha256'],'review/PDF/source binding')
        need(Q(review['cash_per_original_share_CNY'])>0 and Q(review['stock_per_original_share'])==Q(review['capital_per_original_share'])==0 and review['primary_pages'],'cashonly notice reviewed, not derived from factor')
        pp=PRIMARY/doc['file'];pdf=pp.read_bytes();need(sha(pp)==doc['sha256'] and pdf.startswith(b'%PDF'),'original PDFbytes');touched[str(pp)]=sha(pp)
        receipt=doc['pdf_receipt'];paths={}
        for kind in ['request','reserved','response']:
            name=receipt[kind+'_file'];need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe PDFreceipt');p=PRIMARY/name;need(sha(p)==receipt[kind+'_sha256'],'PDFreceipt SHA');paths[kind]=p;touched[str(p)]=sha(p)
        identity=read(paths['request']);key=canonical(identity);reserve=read(paths['reserved']);response=read(paths['response']);need(identity['source']=='CNINFO_HTTP' and identity['url']==doc['url'] and identity['payload'] is None and reserve['identity_sha256']==response['identity_sha256']==key and reserve['attempt']==1 and response['reservation_sha256']==sha(paths['reserved']) and response['status']=='CAPTURED','PDFrequest/reserve/response identity')
        payload=response['payload'];need(canonical(payload)==response['payload_sha256'] and payload['fields']==['http_response'] and len(payload['rows'])==1,'PDFresponse payload binding');wire=payload['rows'][0]
        need(wire['status']==200 and wire['final_url']==doc['url'] and wire['body_complete'] is True and wire['body_truncated'] is False and wire['read_error_type'] is None and wire['read_error'] is None and base64.b64decode(wire['body_base64'],validate=True)==pdf,'full captured HTTP PDFbytes')
        pdfbindings[code]={'file':doc['file'],'sha256':sha(pp),'publication_day':review['publication_day'],'record_date':review['record_date'],'ex_date':review['ex_date'],'cash_payment_date':review['cash_payment_date'],'actual_cash_per_original_share_CNY':review['cash_per_original_share_CNY'],'separate_price_reference_cash_per_share_CNY':review.get('price_reference_cash_per_share_CNY'),'review_primary_pages':review['primary_pages'],'pdf_receipt':receipt}
        # Authenticate the immutable SDK rows from which this V2 increment was composed.
        projected={}
        for component,rec in full['source_query_receipts'].items():
            paths={}
            for kind in ['request','reserved','response']:
                name=rec[kind+'_file'];need(not Path(name).is_absolute() and '..' not in Path(name).parts,'safe rawreceipt');p=v1/name;need(sha(p)==rec[kind+'_sha256'],'raw source receiptSHA');paths[kind]=p;touched[str(p)]=sha(p)
            i=read(paths['request']);k=canonical(i);a=read(paths['reserved']);z=read(paths['response']);need(i['instrument']==code and i['component']==component and i['composite_raw_extension_request_sha256']==full['provenance']['v1_request_sha256'] and a['identity_sha256']==z['identity_sha256']==k and a['attempt']==1 and z['reservation_sha256']==sha(paths['reserved']) and z['status']=='CAPTURED','raw saved queryidentity')
            pl=z['payload'];need(z['payload_sha256']==canonical(pl) and pl['fields']==['provider_response'] and len(pl['rows'])==1,'SDKresponse checksum');sdk=pl['rows'][0];need(sdk['initial_error_code']==sdk['final_error_code']=='0' and sdk['iteration_error_type'] is None and sdk['iteration_error'] is None,'SDKsuccess')
            fields=sdk['fields'];need(len(fields)==len(set(fields)) and all(len(r)==len(fields) for r in sdk['rows']),'SDKschema');projected[component]=[dict(zip(fields,r)) for r in sdk['rows']]
            rawreceipts[code+'/'+component]=rec
        need(set(projected)=={'daily','dividend2026','adjustments'},'same savedthreecomponents')
        need(projected['daily']==[r for r in full['bars'] if r['date']>='2026-01-01'] and projected['dividend2026']==[r for r in full['distributions'] if r['dividOperateDate']>='2026-01-01'] and projected['adjustments']==[r for r in full['adjustments'] if r['dividOperateDate']>='2026-01-01'],'literal V2increment equals SDKresponse fields')
        for root in ROOTS:
            cp=B/root/'codes'/(code+'.json');need(sha(cp)==manifests[root]['per_code_sha256'][code],'cached original packet hash');cached=read(cp);touched[str(cp)]=sha(cp);touched[str(B/root/'manifest.json')]=sha(B/root/'manifest.json')
            lineage=full['provenance']['registered_source_lineage']['registered_caches'];match=[(n,r) for n,r in enumerate(lineage) if r['source_directory']==root];need(len(match)==1,'specific cached root in original lineage');proofindex,origin=match[0]
            need(origin['source_packet_sha256']==sha(cp) and origin['source_window']==cached['window'] and cached['instrument']==code and cached['window']==['2023-12-29','2026-10-16'],'cached lineage exact')
            lo,hi='2023-12-29','2026-10-16';left=rowsby([r for r in full['bars'] if lo<=r['date']<=hi],'date');right=rowsby(cached['bars'],'date');need(set(left)==set(right) and len(left)==674,'all674commoncalendar')
            need(all(left[d]==r and normalized_daily(left[d])==normalized_daily(r) for d,r in right.items()),'all common daily fields and numeric core exact')
            dv=[r for r in full['distributions'] if lo<=r['dividOperateDate']<=hi];need(dv==cached['distributions'],'all common dividend fields/order exact')
            oldall=rowsby(cached['adjustments'],'dividOperateDate');newall=rowsby(full['adjustments'],'dividOperateDate');need(set(oldall)=={d for d in newall if d<=hi},'all common adjustment rowdates exact')
            changed=[];pre26=0
            for d,before in oldall.items():
                after=newall[d];need({k:v for k,v in before.items() if k!='foreAdjustFactor'}=={k:v for k,v in after.items() if k!='foreAdjustFactor'},'all nonfore adjustment fields exact')
                if before['foreAdjustFactor']!=after['foreAdjustFactor']:changed.append(d)
                if d<='2025-12-31':need(before==after,'pre26 literal coordinate prefix kept');pre26+=1
            old=rowsby([r for r in cached['adjustments'] if '2026-01-01'<=r['dividOperateDate']<=hi],'dividOperateDate');new=rowsby([r for r in full['adjustments'] if r['dividOperateDate']>='2026-01-01'],'dividOperateDate');added=[r for d,r in new.items() if d>hi]
            need(len(changed)==1 and changed==list(old) and len(added)==1 and review['ex_date']==added[0]['dividOperateDate'],'only one common2026fore revision and one noticedate addition')
            old_latest=old[max(old)];new_latest=new[max(new)];need(old_latest['foreAdjustFactor']==new_latest['foreAdjustFactor']=='1.000000','latest fore one')
            ob=six(old_latest['backAdjustFactor']);nb=six(new_latest['backAdjustFactor']);need(nb>ob,'increased latest backcoordinate');ratio=ob/nb;rl=(ob-HALF)/(nb+HALF);rh=(ob+HALF)/(nb-HALF);steps=[]
            for d,before in old.items():
                after=new[d];a,b=six(before['foreAdjustFactor']),six(after['foreAdjustFactor']);lower=(a-HALF)*rl;upper=(a+HALF)*rh;require_intersection(lower,upper,b)
                for row in [before,after]:six(row['backAdjustFactor']);six(row['adjustFactor'])
                steps.append({'date':d,'cached_fore':before['foreAdjustFactor'],'fresh_fore':after['foreAdjustFactor'],'predicted_interval':[text(lower),text(upper)],'fresh_rounding_interval':[text(b-HALF),text(b+HALF)],'nonfore_fields_exact':True})
            for f in ['foreAdjustFactor','backAdjustFactor','adjustFactor']:six(added[0][f])
            need(added[0]['code']==old_latest['code'] and added[0]['adjustFactor']==added[0]['backAdjustFactor'],'new source adjustment integrity')
            proof={'instrument':code,'comparison_window':['2026-01-01',hi],'common_daily_rows':sum(d>='2026-01-01' for d in right),'common_distribution_rows':sum(r['dividOperateDate']>='2026-01-01' for r in dv),'old_latest_back':old_latest['backAdjustFactor'],'new_latest_back':new_latest['backAdjustFactor'],'ratio_exact':text(ratio),'ratio_rounding_interval':[text(rl),text(rh)],'common_fore_coordinate_checks':steps,'new_adjustment_row':added[0],'primary_notice':review,'economic_cause_inferred_from_factors':False}
            need(proof==checks[code][proofindex],'independent Fractionproof exactly matches existing source-root mapped coordinate_checks entry')
            pairresults.append({'instrument':code,'cached_root':root,'V2_packet_sha256':sha(vp),'cached_manifest_sha256':sha(B/root/'manifest.json'),'cached_packet_sha256':sha(cp),'all_common_daily_rows_literal_and_normalized_core_exact':674,'all_common_distribution_rows_exact':len(dv),'pre2026_adjustment_rows_literal_exact':pre26,'all_common_nonfore_fields_exact':True,'changed_fore_dates':changed,'existing_coordinate_proof_index':proofindex,'existing_proof_sha256':canonical(checks[code][proofindex]),'fraction_reconstructed_proof':proof,'existing_proof_can_be_reused_unchanged':True})
            packetbindings[code+'/'+root]={'V2':sha(vp),'cached':sha(cp)}
    need(len(pairresults)==4,'exact4pairs')
    negatives={}
    for name in ['wrong_fore_outside_rounding','nonfore_change','cash_notice_ratio_inferred_from_factor','wrong_source_root_proof']:
        example=copy.deepcopy(pairresults[0]['fraction_reconstructed_proof']);stored=pairresults[0]['fraction_reconstructed_proof']
        try:
            if name=='wrong_fore_outside_rounding':s=example['common_fore_coordinate_checks'][0];require_intersection(Q(s['predicted_interval'][0]),Q(s['predicted_interval'][1]),Q(1))
            elif name=='nonfore_change':example['common_fore_coordinate_checks'][0]['nonfore_fields_exact']=False;need(example==stored,'nonfore mismatch')
            elif name=='cash_notice_ratio_inferred_from_factor':example['economic_cause_inferred_from_factors']=True;need(example==stored,'economic inference changed')
            else:example['ratio_exact']='1/1';need(example==stored,'root-specific existing proof mismatch')
        except AssertionError:negatives[name]=True
        else:raise AssertionError('coordinate negativecontrol accepted')
    for p,h in touched.items():need(sha(Path(p))==h,'all touched source bytes unchanged')
    report={'status':'FOUR_EXISTING_COORDINATE_PROOFS_INDEPENDENTLY_FRACTION_RECONSTRUCTED_REUSABLE_UNCHANGED','audit_code_sha256':sha(Path(__file__)),'imports_project_code':False,'production_coordinate_function_called':False,'V2_manifest_sha256':sha(V/'manifest.json'),'public_V2_request_sha256':sha(publicrequest),'prior_V2_independent_audit_sha256':sha(prior_audit),'V2_request_sha256':sha(V/'request.json'),'coordinate_checks_sha256':sha(V/'coordinate_checks.json'),'seven_notice_content_review_sha256':sha(REVIEW),'seven_notice_capture_manifest_sha256':sha(PRIMARY/'manifest.json'),'pairs':pairresults,'primary_PDF_manifest_receipt_bindings':pdfbindings,'six_saved_raw_query_receipts':rawreceipts,'existing_proof_can_be_reused_unchanged':True,'raw_source_bytes_modified':False,'new_cash_entitlement_rows_created':False,'cash_or_tax_inferred_from_adjustment_factors':False,'economic_cause_inferred_from_factors':False,'semantic_negative_controls_rejected':negatives,'account_or_ROI_computed':False,'network_calls':0,'strategy_changes_or_recommendations':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['This is exact coordinate-rounding consistency plus existing reviewed cash-notice provenance, not an independent proof of the economic cause of factor changes.','The V2literal pre2026coordinate prefix stays unchanged; only2026increment forecoordinates are compared using latest-back ratio intervals. This is not a claim of one globally rewritten coordinate basis.','Actual shareholder cash0.05/0.30CNY is bound to the existing notices; any separate price-reference cash remains distinct. No new cash/tax source is inferred, no raw dividend row is supplemented here.','Reuses the existing seven-notice content review and reauthenticates two original PDF complete-byte receipts; does not re-review economics, certify PIT/arrival or grant account/source admission.']}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(OUT),'report_sha256':sha(OUT),'script_sha256':report['audit_code_sha256'],'pairs':4,'proof_reusable_unchanged':True,'ratios':{c:next(x['fraction_reconstructed_proof']['ratio_exact'] for x in pairresults if x['instrument']==c) for c in CODES}}))
if __name__=='__main__':main()
