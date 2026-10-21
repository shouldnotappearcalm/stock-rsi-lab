"""Independent standard-library HTTP/PDF provenance reconstruction; no ROI."""
import argparse,base64,hashlib,json,re
from datetime import datetime,timedelta,timezone
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def body(wire,url):
    if (wire['status']!=200 or wire['final_url']!=url or wire['body_complete'] is not True
            or wire['body_truncated'] is not False or wire['read_error_type'] is not None):
        raise ValueError('incomplete original HTTP body')
    data=base64.b64decode(wire['body_base64'],validate=True)
    if not data or len(data)>10485760:raise ValueError('bounded nonempty original body required')
    return data


def audit(repo,base,expected_manifest):
    out=base/'low-beta60-corporate-2026-20261021'
    path=repo/'experiments/qlib/low-beta60-2026-primary-capture-request.json'
    request_sha='d7f73f8aab1f10a73a3c9d1c1e350ec9ab1fb4f513e1f1530ef1be24680d8aa9'
    assert sha(path)==request_sha and sha(out/'manifest.json')==expected_manifest
    request=json.loads(path.read_bytes());manifest=json.loads((out/'manifest.json').read_bytes())
    assert (out/'request.json').read_bytes()==path.read_bytes()
    for bindings,root in ((request['method_code_sha256'],repo),(request['public_evidence_sha256'],repo),
                          (request['local_source_sha256'],base)):
        for f,h in bindings.items():assert not Path(f).is_absolute() and '..' not in Path(f).parts and sha(root/f)==h
    assert manifest['request_sha256']==request_sha and manifest['capture_complete'] is True
    assert manifest['errors']=={} and manifest['pending_documents']==[]
    assert manifest['abnormal_termination'] is False and manifest['stopped_after_three_failures'] is False
    actual={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    assert actual==manifest['artifact_sha256']
    expected={};decoded={}
    def identity(url,payload=None):return {'source':'CNINFO_HTTP','url':url,'payload':payload,'notice_request_sha256':request_sha}
    for folder in sorted((out/'queries').iterdir()):
        assert {p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'}
        item=json.loads((folder/'request.json').read_bytes());reservation=json.loads((folder/'reserved-1.json').read_bytes())
        response=json.loads((folder/'response-1.json').read_bytes())
        assert folder.name==digest(item)==reservation['identity_sha256']==response['identity_sha256']
        assert reservation['attempt']==1 and response['reservation_sha256']==sha(folder/'reserved-1.json')
        assert response['status']=='CAPTURED' and digest(response['payload'])==response['payload_sha256']
        payload=response['payload'];assert payload['fields']==['http_response'] and len(payload['rows'])==1
        decoded[folder.name]=body(payload['rows'][0],item['url'])
    listing_row=None
    for c in request['documents']:
        key=c['document_id'];doc=manifest['documents'][key];pdf=out/(key+'.pdf')
        assert doc['file']==pdf.name and doc['instrument']==c['instrument'] and doc['publication_day']==c['publication_day']
        data=pdf.read_bytes();assert data.startswith(b'%PDF') and sha(pdf)==doc['sha256']
        if 'reuse_file' in c:
            assert data==(base/c['reuse_file']).read_bytes() and sha(pdf)==c['reuse_sha256']
            assert doc['capture_route']=='BYTE_IDENTICAL_REUSE' and doc['pdf_receipt'] is None
            continue
        url=c.get('url')
        if url is None:
            p={'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
                'stock':c['instrument'][2:]+','+c['organization_id'],'searchkey':'','secid':'','category':'',
                'trade':'','seDate':c['publication_day']+'~'+c['publication_day'],
                'sortName':'','sortType':'','isHLtitle':'true'}
            item=identity('https://www.cninfo.com.cn/new/hisAnnouncement/query',p);k=digest(item);expected[k]=item
            listing=json.loads(decoded[k]);rows=listing['announcements']
            assert type(listing['totalAnnouncement']) is int and listing['totalAnnouncement']==len(rows)<=30
            matches=[]
            for row in rows:
                assert row['secCode']==c['instrument'][2:]
                assert type(row['announcementTime']) is int
                assert datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()==c['publication_day']
                title=re.sub('<[^>]*>','',row['announcementTitle']).split('：')[-1]
                if title==c['exact_title']:matches.append(row)
            assert len(matches)==1;listing_row=matches[0]
            assert re.fullmatch('[0-9]+',listing_row['announcementId'])
            assert listing_row['adjunctUrl']=='finalpage/'+c['publication_day']+'/'+listing_row['announcementId']+'.PDF'
            assert listing_row==doc['listing_row'];url='https://static.cninfo.com.cn/'+listing_row['adjunctUrl']
        assert re.fullmatch('https://static\\.cninfo\\.com\\.cn/finalpage/'+c['publication_day']+'/[0-9]+\\.PDF',url)
        item=identity(url);k=digest(item);expected[k]=item
        assert decoded[k]==data and doc['url']==url and doc['capture_route']=='JOURNALED_ORIGINAL_HTTP'
        for receipt in (doc['pdf_receipt'],doc['listing_receipt']):
            if receipt is None:continue
            for f,h in (('request_file','request_sha256'),('reserved_file','reserved_sha256'),('response_file','response_sha256')):
                assert not Path(receipt[f]).is_absolute() and '..' not in Path(receipt[f]).parts and sha(out/receipt[f])==receipt[h]
    assert len(decoded)==len(expected)==manifest['http_query_reservations']==request['maximum_http_queries']==6
    assert set(decoded)==set(expected)
    for k,item in expected.items():
        assert (out/'queries'/k/'request.json').read_bytes()==(json.dumps(item,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    negatives={}
    valid={'status':200,'final_url':'https://example.invalid/','body_complete':True,'body_truncated':False,
           'read_error_type':None,'body_base64':base64.b64encode(b'%PDF-1.4').decode()}
    for name,change in (('non200',{'status':404}),('redirect',{'final_url':'https://other.invalid/'}),
                         ('truncated',{'body_truncated':True}),('partial',{'body_complete':False}),
                         ('invalid_base64',{'body_base64':'!!!'})):
        try:body({**valid,**change},valid['final_url'])
        except (ValueError,TypeError):negatives[name]=True
        else:raise AssertionError('invalid HTTP envelope accepted')
    return {'status':'INDEPENDENT_SIX_PRIMARY_PDFS_AND_SIX_HTTP_RECEIPTS_RECONSTRUCTED',
        'audit_code_sha256':sha(__file__),'request_sha256':request_sha,'capture_manifest_sha256':expected_manifest,
        'documents':6,'reused_original_bytes':1,'new_pdf_responses':5,'listing_responses':1,
        'canonical_request_bytes_authenticated':6,'all_pdf_bytes_equal_response_or_bound_cache':True,
        'canonical_SH603826_url':'https://static.cninfo.com.cn/'+listing_row['adjunctUrl'],
        'http_envelope_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,
        'source_content_financially_admitted':False,'historical_arrival_verified':False,
        'portfolio_returns_computed':False,'objective_achieved':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--expected-manifest-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(a.repo,a.base,a.expected_manifest_sha256)
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(result['status'])
