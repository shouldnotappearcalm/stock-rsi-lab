"""Original HTTP bytes and a second PDF extractor; no production imports."""
import argparse,base64,hashlib,json,re
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def need(x,m):
    if not x:raise ValueError(m)

def http_original(directory,receipt,file,publisher=False):
    paths={}
    for label in ('request','reserved','response'):
        rel=Path(receipt[label+'_file']);need(not rel.is_absolute() and '..' not in rel.parts,'local receipt')
        paths[label]=directory/rel;need(sha(paths[label])==receipt[label+'_sha256'],'original HTTP chain hash')
    q,r,s=(read(paths[n]) for n in ('request','reserved','response'));key=digest(q)
    need(r['identity_sha256']==s['identity_sha256']==key and r['attempt']==1
        and s['status']=='CAPTURED' and s['reservation_sha256']==sha(paths['reserved'])
        and digest(s['payload'])==s['payload_sha256'],'complete one-attempt original envelope')
    p=s['payload'];need(p['fields']==['publisher_http_response' if publisher else 'http_response'] and len(p['rows'])==1,'one full HTTP response')
    row=p['rows'][0]
    if publisher:need(row['curl_returncode']==0 and row['HTTP_status']=='200' and row['URL']==q['url'],'successful official-publisher bytes')
    else:need(row['status']==200 and row['body_complete'] is True and row['body_truncated'] is False
        and row['read_error_type'] is None and row['final_url']==q['url'],'successful complete original HTTP bytes')
    need(base64.b64decode(row['body_base64'],validate=True)==file.read_bytes(),'PDF equals original HTTP body')
    return {str(p):sha(p) for p in paths.values()}

def main():
    from pdfminer.high_level import extract_text
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    base=Path(a.source_root);out=Path(a.output);need(not out.exists(),'fresh primary audit')
    old=base/'low-market-residual-vol1m-primary-pre2026-20261021';first=base/'asset-expansion-primary-pre2026-20261022';pub=base/'asset-expansion-publisher-original-20261022'
    od=read(old/'manifest.json')['documents']['SH603688|2024-05-22'];fd=read(first/'manifest.json')['documents']['SH600535'];pd=read(pub/'manifest.json')
    need(pd['capture_complete'] is True and pd['error'] is None,'complete registered publisher capture')
    cases=[('SH600535',first,fd['file'],fd['sha256'],fd['HTTP_PDF_receipt'],False,3,
        ['600535','2024年年度权益分派实施公告','每股现金红利0.20元','2025/3/25','2025/3/26','2025年3月20日']),
      ('SH600737',pub,pd['file'],pd['sha256'],pd['HTTP_receipt'],True,3,
        ['600737','2024年末期权益分派实施公告','每股现金红利0.41元','2025/8/12','2025/8/13','2025年8月5日','不涉及派送红股及转增股本']),
      ('SH603688',old,od['file'],od['sha256'],od['HTTP_pdf_receipt'],False,5,
        ['603688','2023年年度权益分派实施公告','每股现金红利5.7元','每股转增股份0.5股','2024/5/21','2024/5/22','2024年5月16日','5.6925','0.4993'])]
    documents=[];bound={}
    for code,directory,file,h,receipt,publisher,pages,tokens in cases:
        f=directory/file;need(sha(f)==h and f.read_bytes().startswith(b'%PDF'),'original issuer PDF hash')
        bound[str(f)]=h;bound[str(directory/'manifest.json')]=sha(directory/'manifest.json')
        bound.update(http_original(directory,receipt,f,publisher))
        text=extract_text(f);parts=[v for v in text.split('\f') if v.strip()];need(len(parts)==pages,'complete original page count')
        compact=re.sub(r'\s+','',text)
        for t in tokens:need(t in compact,'second extractor original identity/economic token '+t)
        documents.append({'instrument':code,'source_relative':str(f.relative_to(base)),'file':file,'sha256':h,
            'pages_read':pages,'pdfminer_text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'checked_tokens':tokens,'HTTP_bytes_authenticated':True,'second_extractor_matches_reviewed_facts':True})
    failed=[]
    for n in ('asset-expansion-primary-pre2026-20261022','asset-expansion-primary-continuation-pre2026-20261022'):
        for f in (base/n).glob('queries/*/response-1.json'):
            v=read(f)
            if v['status']=='SOURCE_ERROR':
                need(v['error_type']=='URLError' and 'SSL' in v['error'],'original TLS failures retained');failed.append({'file':str(f.relative_to(base)),'sha256':sha(f),'error_type':v['error_type'],'error':v['error']});bound[str(f)]=sha(f)
    need(len(failed)==2,'both original CNINFO download failures retained')
    for f,h in bound.items():need(sha(f)==h,'all original bytes unchanged after primary QA')
    result={'status':'THREE_ORIGINALS_HTTP_AND_SECOND_PDF_EXTRACTOR_CHECKED_NOT_ACCOUNT_ADMISSION',
        'audit_code_sha256':sha(Path(__file__)),'documents':documents,'original_TLS_failures':failed,'all_inputs_sha256':bound,
        'pages_read':11,'no_production_imports':True,'second_extractor':'pdfminer20251230',
        'same_researcher_review':True,'original_pypdf_review_also_completed':True,'source_packets_modified':False,
        'cash_amounts_match_vendor':True,'capital_tax_exemption_verified':False,'fractional_allocation_verified':False,
        'physical_account_admitted':False,'new_2026_provider_queries':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print(result['status'],'11pages,2TLSfailures retained')

if __name__=='__main__':main()
