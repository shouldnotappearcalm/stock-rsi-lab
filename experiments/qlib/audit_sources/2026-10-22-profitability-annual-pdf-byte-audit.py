"""Separate raw PDF capture reconstruction; no PDF text, financial values or ROI.
Written after acquisition, not a blinded independent-researcher audit.
"""
import argparse
import hashlib
import json
from pathlib import Path


def need(v, message):
    if not v: raise AssertionError(message)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    for name in ('repo-root','source-root','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();root,base,run,out=map(lambda p:Path(p).resolve(),(a.repo_root,a.source_root,a.run_dir,a.output));reqpath=Path(a.request).resolve()
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'new external report only')
    need(sha(reqpath)==a.expected_request_sha256,'frozen PDF request identity');req=read(reqpath)
    need(req['status']=='FROZEN_BEFORE_FIXED12_ANNUAL_PDF_CAPTURE' and len(req['documents'])==36
         and len(req['resources'])==req['max_logical_attempts']==34 and req['cache_reuse_count']==2
         and req['per_resource_attempts']==1 and req['financial_numeric_parsing_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False,'exact fixed36 source-only capture')
    expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    paths={k:(root if k.startswith('repo/') else base)/k.split('/',1)[1] for k in req['input_sha256']};paths['frozen_source_request']=reqpath
    need(len(paths)==96,'complete96 bound inputs')
    for k,p in paths.items():need(sha(p)==expected[k],'actual input before reconstruction')
    outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    need(len(outputs)==178,'exact178 successful PDF capture outputs')
    cases=read(run/'case_results.json');summary=read(run/'summary.json');rebuilt=[];allids=set();cached=0;bytecount=0
    for d in req['documents']:
        key=d['capture_key'];identity=d['announcement_id'];need(identity not in allids,'unique frozen document IDs');allids.add(identity)
        if d['source_kind']=='REUSE_AUTHENTICATED_ORIGINAL_PDF':
            need(sha(base/d['source_path'])==d['source_sha256'],'cached original PDF remains unchanged')
            record={**d,'status':'ORIGINAL_PDF_BYTES_REUSED_IDENTITY_REVIEW_SEPARATE'};cached+=1
        else:
            resource=req['resources'][key];need(resource=={'method':'GET','url':d['url'],'payload':None},'exact frozen PDF GET')
            h=digest({'resource':key,'identity':resource});folder=run/'http'/h
            need({p.name for p in folder.iterdir()}=={'request.json','reservation.json','body.bin','response.json'},'exact four HTTP artifacts')
            need(read(folder/'request.json')=={'resource':key,**resource},'original request object')
            reservation=read(folder/'reservation.json');need(reservation['resource']==key and reservation['attempt']==reservation['maximum_logical_attempts']==1 and reservation['identity_sha256']==digest(resource),'one reserved logical attempt')
            response=read(folder/'response.json');need(response['resource']==key and response['identity_sha256']==digest(resource)
                and response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
                and response['body_complete'] is True and response['request_sha256']==sha(folder/'request.json')
                and response['reservation_sha256']==sha(folder/'reservation.json') and response['body_sha256']==sha(folder/'body.bin')
                and response['body_bytes']==(folder/'body.bin').stat().st_size,'raw HTTP identity/body conservation')
            with (folder/'body.bin').open('rb') as stream:need(stream.read(5)==b'%PDF-','raw PDF magic only')
            need(1000<=response['body_bytes']<=26214400,'bounded nontrivial captured source')
            receipt={'folder':'http/'+h,'record':response,'response_sha256':sha(folder/'response.json')}
            record={**d,'status':'PDF_MAGIC_CAPTURED_NUMERIC_IDENTITY_REVIEW_PENDING','receipt':receipt,
                'source_path':str((folder/'body.bin').relative_to(base)),'source_sha256':sha(folder/'body.bin'),
                'captured_at_utc':response['captured_at_utc']};bytecount+=response['body_bytes']
        need(record==read(run/(key+'.json'))==cases[key]==summary['results_by_document'][key],'literal source document packets and case results reconstructed')
        rebuilt.append(record)
    need(cached==2 and read(run/'documents.json')==rebuilt,'complete36 document order/identity and2 reuses')
    need(summary['status']=='FIXED12_ANNUAL_PDF_BYTES_CAPTURED_REVIEW_PENDING' and summary['documents_recorded']==36
        and summary['logical_attempts']==34 and summary['rejected_documents']==0 and summary['cached_reused']==2
        and summary['input_count']==96 and summary['request_sha256']==a.expected_request_sha256
        and summary['all_inputs_unchanged'] is True and summary['financial_numeric_values_decoded'] is False
        and summary['investment_factor_admitted'] is False and summary['portfolio_returns_computed'] is False
        and summary['objective_achieved'] is False,'source-only complete summary')
    need(read(run/'input-before.json')==expected,'input-before identity')
    post={'all_inputs_unchanged':True,'count':96,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-postcheck.json')==post,'input postcheck')
    terminal=read(run/'terminal.json');need(terminal['logical_attempts']==34 and terminal['completed_documents']==36
        and terminal['pending']==[] and terminal['original_error'] is None and terminal['postcheck']==post
        and terminal['persistence_errors']==[],'successful terminal')
    for k,p in paths.items():need(sha(p)==expected[k],'actual input after reconstruction')
    need(outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all output bytes unchanged during audit')
    report={'status':'PASS_SEPARATE_FIXED12_ANNUAL_PDF_BYTE_AUDIT','audit_code_sha256':sha(__file__),
        'request_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),'all96_input_sha256':expected,
        'all178_output_sha256':outputs,'source_documents_reconstructed':36,'fresh_logical_GET_attempts':34,
        'original_cached_PDFs_reused':2,'fresh_PDF_bytes':bytecount,'source_document_records':rebuilt,
        'production_modules_imported':False,'blinded_audit_claimed':False,'PDF_text_or_financial_values_decoded':False,
        'issuer_and_fiscal_content_identity_verified':False,'financial_version_history_complete':False,
        'historical_arrival_verified':False,'investment_factor_admitted':False,'security_ranking_or_portfolio_returns_computed':False,
        '2026_financial_or_market_values_decoded':False,'objective_achieved':False}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(report['status'],sha(out),bytecount)
if __name__=='__main__':main()
