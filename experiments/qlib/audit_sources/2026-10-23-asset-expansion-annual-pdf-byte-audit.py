"""Separate400-resource PDF byte/lineage audit; no PDF extractor or project imports."""
import argparse
from collections import Counter
from datetime import date
import hashlib,json,re
from pathlib import Path

SOURCE='asset-expansion-2026-metadata-completed-20261023'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file()}


def audit(base,repo,request,expected,run):
    need(sha(request)==expected,'frozen all400 PDF request');req=read(request);before=inventory(run)
    bound={request:expected};qa=read(repo/'experiments/qlib/asset-expansion-2026-completed-metadata-audit.json')
    need(qa['all_394_sources_accepted'] is True and qa['full_report_candidates']==400,'complete source metadata required')
    for group in ('method_sha256','public_sha256'):
        for n,h in req[group].items():bound[repo/n]=h
    for n,h in qa['all_output_sha256'].items():bound[base/SOURCE/n]=h
    for p,h in bound.items():need(sha(p)==h,'original input before '+str(p))
    cases=read(base/SOURCE/'case_results.json');docs=[];resources={};ids=set()
    for code,case in sorted(cases.items()):
        need(case['status'] in ('METADATA_CAPTURED_WITH_CANDIDATES','METADATA_CAPTURED_NO_FULL_CANDIDATE'),'accepted original metadata')
        for v in case['full_report_candidates']:
            aid,day,path,year=v['announcement_id'],v['day'],v['pdf_path'],v['fiscal_year']
            need(v['instrument']==code and 'CANDIDATE' in v['classification'] and aid.isdigit() and aid not in ids
                and date.fromisoformat(day).isoformat()==day and '2026-01-01'<=day<='2026-10-21'
                and (year is None or type(year) is int and 1900<=year<=2025 and year<int(day[:4]))
                and re.fullmatch('finalpage/'+re.escape(day)+'/'+aid+r'\.[pP][dD][fF]',path),'literal source issuer/date/fiscal metadata/original path')
            ids.add(aid);key=code+'-'+aid;url='https://static.cninfo.com.cn/'+path
            docs.append({'key':key,'instrument':code,'announcement_id':aid,'day':day,'metadata_fiscal_year':year,
                'metadata_classification':v['classification'],'file':key+'.pdf','url':url,'cover_fiscal_identity_verified':False})
            resources[key]={'method':'GET','url':url,'payload':None}
    need(len(docs)==400 and docs==req['documents'] and resources==req['resources'],'independently reconstruct all400 original editions,not one latest')
    results=read(run/'case_results.json');terminal=read(run/'terminal.json');keys=[v['key'] for v in docs]
    need(list(results)==keys[:len(results)] and terminal['pending']==[k for k in keys if k not in results]
        and terminal['completed_resources']==len(results) and not terminal['changed_original_inputs']
        and not terminal['persistence_errors'],'complete captured prefix and immutable terminal')
    need(read(run/'input-before.json')=={str(p):h for p,h in bound.items()},'complete source input bindings')
    descriptors={d['key']:d for d in docs};successful=[];failures=[];counts=Counter();bytecount=0
    for key,v in results.items():
        need(read(run/(key+'.json'))==v,'per-case immutable source record');doc=descriptors[key];resource=resources[key]
        need(all(v[k]==x for k,x in doc.items()),'original source descriptor unchanged');counts[v['status']]+=1
        folder=run/'http'/digest({'resource':key,'identity':resource})
        q,res,response=(read(folder/n) for n in ('request.json','reservation.json','response.json'))
        need(q=={'resource':key,**resource} and res['resource']==key and res['attempt']==1
            and res['maximum_logical_attempts']==1 and res['identity_sha256']==digest(resource)
            and response['resource']==key and response['identity_sha256']==digest(resource)
            and response['request_sha256']==sha(folder/'request.json') and response['reservation_sha256']==sha(folder/'reservation.json'),
            'one exact original URL/request/reservation/response hash chain')
        transport=run/'curl-transport'/folder.name;tr=read(transport/'transport.json')
        need(read(transport/'request.json')==q and tr['resource']==key and tr['automatic_retries']==0
            and tr['redirects_permitted'] is False and all(sha(transport/n)==h for n,h in tr['artifact_sha256'].items()),'all actual curl artifacts retained and authenticated')
        if v['status']=='PDF_SOURCE_REJECTED':
            failures.append({'key':key,'error_type':v['error_type'],'error':v['error'],
                'HTTP_record_status':response['status'],'curl_returncode':tr['returncode']});continue
        need(v['status']=='ORIGINAL_PDF_BYTES_CAPTURED_NOT_FISCAL_ADMISSION' and response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED'
            and response['http_status']==200 and response['body_complete'] is True and response['final_url']==resource['url']
            and tr['returncode']==0 and tr['original_error'] is None,'complete official source HTTP200 and curl success')
        body=folder/'body.bin';pdf=run/doc['file'];h=sha(pdf)
        need(h==v['source_sha256']==response['body_sha256']==sha(body)==sha(transport/'body.bin')
            and pdf.stat().st_size==body.stat().st_size==response['body_bytes']<=67108864,'all three original byte copies match exact complete response')
        with pdf.open('rb') as f:need(f.read(5)==b'%PDF-','original PDF byte signature')
        need((transport/'stdout.bin').read_text().strip().splitlines()==['200',resource['url']]
            and v['source_path']==run.name+'/'+doc['file'] and v['captured_at_utc']==response['captured_at_utc']
            and v['receipt']=={'folder':str(folder.relative_to(run)),'record':response,'response_sha256':sha(folder/'response.json')},'capture time/path/full original receipt')
        successful.append(v);bytecount+=pdf.stat().st_size
    need(read(run/'documents.json')==successful,'all successful originals including every metadata edition')
    attempts=len(list((run/'http').rglob('reservation.json')))
    need(attempts==terminal['logical_attempts'] and attempts in (len(results),len(results)+1) and attempts<=400,'global source attempts and interrupted prefix')
    if not terminal['pending']:
        s=read(run/'summary.json');need(s['resource_count']==400 and s['status_counts']==dict(counts)
            and s['successful_original_PDFs']==len(successful) and s['original_PDF_bytes']==bytecount
            and s['all_original_inputs_unchanged'] is True and s['cover_fiscal_identity_verified'] is False
            and s['financial_numeric_values_decoded'] is False and s['2026_portfolio_returns_computed'] is False,'accurate complete source-only summary')
    for p,h in bound.items():need(sha(p)==h,'original input after '+str(p))
    need(inventory(run)==before,'all PDF/HTTP/curl/case output bytes unchanged through QA')
    return {'status':'SEPARATE_2026_ANNUAL_PDF_BYTE_PREFIX_AUDIT_NOT_FINANCIAL_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':expected,'resource_count':400,
        'completed_resources':len(results),'successful_original_PDFs':len(successful),'original_PDF_bytes':bytecount,
        'logical_attempts':attempts,'pending':terminal['pending'],'original_terminal_error':terminal['original_error'],
        'source_rejections':failures,'all400_originals_captured':len(successful)==400,
        'status_counts':dict(counts),'all_output_sha256':before,'all_original_inputs_unchanged':True,
        'no_production_imports':True,'same_researcher_separate_QA':True,'PDF_text_or_financial_values_decoded':False,
        'cover_fiscal_identity_verified':False,'historical_arrival_verified':False,'financial_version_history_complete':False,
        '2026_portfolio_returns_computed':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','repo-root','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.output);need(not out.exists(),'fresh external source byte audit')
    result=audit(Path(a.source_root),Path(a.repo_root),Path(a.request).resolve(),a.expected_request_sha256,Path(a.run_dir))
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'],'originals',result['successful_original_PDFs'],'rejected',len(result['source_rejections']),'pending',len(result['pending']))

if __name__=='__main__':main()
