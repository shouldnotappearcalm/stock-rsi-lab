"""Independent technical audit: local primary PDFs, metadata and HTTP byte chain.
No economic content review, network, SDK, account replay or runtime imports.
"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import base64,hashlib,json,re,subprocess
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
O=B/'price-delay-corporate-primary-20261021'
REQ=R/'experiments/qlib/price-delay-corporate-source-request.json'
OUT=Path('/tmp/price-delay-primary-capture-independent-audit-20261021.json')
EXPECTED='15d50d8a38fcbe88e2e2304c1680e74d01e132f714eb691f1657799c854568ec'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hbytes(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_bytes())
def need(v,s):
    if not v:raise AssertionError(s)
def canonical(v):return hbytes(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode())
def pub(ms):return datetime.fromtimestamp(ms/1000,timezone(timedelta(hours=8))).date().isoformat()
def main():
    req=read(REQ);m=read(O/'manifest.json');freeze=subprocess.check_output(['git','rev-parse','12d8ed8'],cwd=R,text=True).strip()
    need(sha(REQ)==sha(O/'request.json')==m['request_sha256']==EXPECTED,'request SHA')
    need(hbytes(subprocess.check_output(['git','show',freeze+':'+str(REQ.relative_to(R))],cwd=R))==EXPECTED,'frozen request')
    for n,h in req['method_code_sha256'].items():need(sha(R/n)==h==hbytes(subprocess.check_output(['git','show',freeze+':'+n],cwd=R)),'method '+n)
    need(sha(R/req['protocol_file'])==req['protocol_sha256']==hbytes(subprocess.check_output(['git','show',freeze+':'+req['protocol_file']],cwd=R)),'protocol')
    bindings={'price-delay-raw-dev-20261021/manifest.json':'raw_manifest_sha256','price-delay-raw-source-corporate-questions-20261021.json':'raw_audit_sha256','cninfo-csi500-reports-20261017/plan.json':'org_map_plan_sha256'}
    for n,k in bindings.items():need(sha(B/n)==req[k],'source '+n)
    independent=R/'experiments/qlib/price-delay-raw-source-independent-audit.json';need(sha(independent)==req['independent_raw_source_audit_sha256'],'independent raw audit')
    ia=read(independent);rawm=read(B/'price-delay-raw-dev-20261021/manifest.json');q=read(B/'price-delay-raw-source-corporate-questions-20261021.json');orgs=read(B/'cninfo-csi500-reports-20261017/plan.json')['org_by_code']
    need(rawm['window']==['2023-12-29','2025-12-31'] and q['manifest_sha256']==sha(B/'price-delay-raw-dev-20261021/manifest.json') and not q['questions']['unknown_economics'],'raw question provenance')
    packets={}
    for c,h in rawm['per_code_sha256'].items():
        p=B/'price-delay-raw-dev-20261021/codes'/(c+'.json');need(sha(p)==h,'original raw packet');packets[c]=read(p);need(packets[c]['window']==['2023-12-29','2025-12-31'],'physically pre2026 packet')
    expected={}
    for kind,field in [('NONCASH','noncash'),('ADJUSTMENT_WITHOUT_DISTRIBUTION','adjustments_without_distribution')]:
        for item in q['questions'][field]:
            c=item['instrument'];r=item['record'];d=r['dividOperateDate'];key=c+'|'+d
            need(key not in expected and '2024-01-01'<=d<='2025-12-31','unique pre2026 question')
            need(r in packets[c]['distributions' if kind=='NONCASH' else 'adjustments'],'source row exact')
            if kind=='ADJUSTMENT_WITHOUT_DISTRIBUTION':need(not any(x['dividOperateDate']==d for x in packets[c]['distributions']),'unmatched row')
            expected[key]={'case_id':key,'instrument':c,'kind':kind,'source_record':r}
    cases={c['case_id']:c for c in req['cases']};need(len(req['cases'])==len(cases)==len(expected)==15 and set(cases)==set(expected),'complete15case scope')
    for key,c in cases.items():
        need(all(c[k]==v for k,v in expected[key].items()) and c['organization_id']==orgs[c['instrument']],'source case/issuer/org exact')
        need('2024-01-01'<=c['publication_day']<='2025-12-31','pre2026 publication')
        if c['kind']=='NONCASH':need(c['publication_day']==c['source_record']['dividPlanDate'],'noncash publication source')
        if 'related_vendor_distribution' in c:need(c['related_vendor_distribution'] in packets[c['instrument']]['distributions'] and c['publication_day']==c['related_vendor_distribution']['dividPlanDate'],'related source notice date')
    need(len(req['reuse_documents'])==12 and len(set(cases)-set(req['reuse_documents']))==3,'12+3')
    docs=m['documents'];need(set(docs)==set(cases) and read(O/'progress.json')==docs and read(O/'errors.json')==m['errors']=={} and m['pending_cases']==[],'complete docs no errors pending')
    allfiles={str(p.relative_to(O)):sha(p) for p in O.rglob('*') if p.is_file() and p.name not in ('manifest.json','capture.lock')}
    need(allfiles==m['artifact_sha256'],'exact recursive artifact file/hash map')
    for key,d in docs.items():
        c=cases[key];p=O/d['file'];raw=p.read_bytes();need(Path(d['file']).name==d['file'] and sha(p)==d['sha256'] and raw.startswith(b'%PDF') and b'%%EOF' in raw[-2048:],'PDF byte integrity')
        need(d['instrument']==c['instrument'] and d.get('code',c['instrument'][2:])==c['instrument'][2:] and d['day']==c['publication_day'] and '2024-01-01'<=d['day']<='2025-12-31','document issuer/day metadata')
        if 'timestamp_ms' in d:need(pub(d['timestamp_ms'])==d['day'],'publication timestamp')
        expectedpath='finalpage/'+d['day']+'/'+d['announcement_id']+'.PDF';need(re.fullmatch(r'[0-9]+',d['announcement_id']) and d.get('pdf_path',expectedpath).lower()==expectedpath.lower() and d['url']=='https://static.cninfo.com.cn/'+d.get('pdf_path',expectedpath),'announcement original path identity')
        if key in req['reuse_documents']:
            reuse=req['reuse_documents'][key];directory=B/reuse['directory'];need(Path(reuse['directory']).name==reuse['directory'],'reuse directory')
            need(sha(directory/'reviewed-manifest.json')==reuse['reviewed_manifest_sha256'],'reviewed source manifest')
            proof=read(directory/'reviewed-manifest.json');need(reuse['metadata'] in proof['documents'],'reviewed source metadata membership')
            need((directory/reuse['file']).read_bytes()==raw and sha(p)==reuse['sha256'],'byteexact reviewed PDF copy')
            exp={**reuse['metadata'],'capture_route':'BYTE_IDENTICAL_REVIEWED_PRIMARY_REUSE','original_reviewed_manifest_sha256':reuse['reviewed_manifest_sha256']};need(d==exp,'reused identity provenance exact')
    queries={};querymap={};bodies={};identities={}
    for folder in (O/'queries').iterdir():
        need(folder.is_dir() and {p.name for p in folder.iterdir()}=={'request.json','reserved-1.json','response-1.json'},'one completed attempt')
        identity=read(folder/'request.json');key=canonical(identity);need(folder.name==key and identity['source']=='CNINFO_HTTP' and identity['notice_request_sha256']==EXPECTED,'query identity')
        res=read(folder/'reserved-1.json');response=read(folder/'response-1.json');need(res['identity_sha256']==key and res['attempt']==1 and response['identity_sha256']==key and response['reservation_sha256']==sha(folder/'reserved-1.json') and response['status']=='CAPTURED','reservation response link')
        payload=response['payload'];need(response['payload_sha256']==canonical(payload) and payload['fields']==['http_response'] and len(payload['rows'])==1,'payload checksum/envelope')
        need(datetime.fromisoformat(res['reserved_at_utc'])<=datetime.fromisoformat(payload['captured_at_utc']),'time order')
        wire=payload['rows'][0];need(wire['status']==200 and wire['final_url']==identity['url'] and wire['body_truncated'] is False and wire['body_complete'] is True and wire['read_error_type'] is None and wire['read_error'] is None,'complete HTTP success/no redirect')
        body=base64.b64decode(wire['body_base64'],validate=True);need(0<len(body)<=10*1024*1024,'HTTP bounded bytes');bodies[key]=body;identities[key]=identity
        queries[key]={'identity':identity,'body_sha256':hbytes(body),'body_bytes':len(body),'content_type':wire['content_type'],'response_sha256':sha(folder/'response-1.json')}
        for p in folder.iterdir():querymap[str(p.relative_to(O))]=sha(p)
    need(len(queries)==m['HTTP_query_reservations']==6<=m['maximum_HTTP_query_reservations']==req['maximum_http_query_reservations']==9 and len(querymap)==18,'6actual/9budget')
    used=set();fresh=[]
    for key in sorted(set(cases)-set(req['reuse_documents'])):
        c=cases[key];d=docs[key];need(c['instrument'] in {'SH600390','SH600754','SH603529'} and c['publication_day']=='2024-07-06','three fixed fresh issuers/exactday')
        payload={'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':c['instrument'][2:]+','+c['organization_id'],'searchkey':'','secid':'','category':'','trade':'','seDate':'2024-07-06~2024-07-06','sortName':'','sortType':'','isHLtitle':'true'}
        listing=[k for k,i in identities.items() if i=={'source':'CNINFO_HTTP','url':'https://www.cninfo.com.cn/new/hisAnnouncement/query','payload':payload,'notice_request_sha256':EXPECTED}];need(len(listing)==1,'exact issuer/day listing query');lk=listing[0];used.add(lk);data=json.loads(bodies[lk]);rows=data['announcements'];need(len(rows)==int(data['totalAnnouncement']) and 0<len(rows)<=30,'single complete listing page')
        need(all(r['secCode']==c['instrument'][2:] and r['orgId']==c['organization_id'] and pub(r['announcementTime'])==c['publication_day'] for r in rows),'listing all exact issuer/day')
        match=[r for r in rows if re.search('权益分派实施(?:的)?公告',r['announcementTitle'])];need(len(match)==1,'unique implementation notice')
        a=match[0];projection={'code':a['secCode'],'title':a['announcementTitle'],'day':pub(a['announcementTime']),'timestamp_ms':a['announcementTime'],'announcement_id':a['announcementId'],'pdf_path':a['adjunctUrl']}
        need(all(d[k]==v for k,v in projection.items()),'fresh document matches unique listing')
        receipt=d['HTTP_pdf_receipt'];qkeys=set()
        for typ in ('request','reserved','response'):
            path=receipt[typ+'_file'];need(path in querymap and querymap[path]==receipt[typ+'_sha256'],'PDF receipt byte binding');qkeys.add(Path(path).parent.name)
        need(len(qkeys)==1,'PDF one query');pk=qkeys.pop();used.add(pk)
        need(identities[pk]=={'source':'CNINFO_HTTP','url':d['url'],'payload':None,'notice_request_sha256':EXPECTED} and bodies[pk]==(O/d['file']).read_bytes(),'original PDF complete response bytes exact')
        need(d['capture_route']=='JOURNALED_ORIGINAL_PRIMARY_HTTP','fresh capture route');fresh.append({'case_id':key,'instrument':c['instrument'],'day':d['day'],'listing_query':lk,'PDF_query':pk,'file':d['file'],'sha256':d['sha256']})
    need(used==set(queries),'all6 queries correspond to three listing/PDF pairs')
    target=B/'price-delay-pre2026-formations-20261021/targets.json';rawreq=read(B/'price-delay-raw-dev-20261021/request.json');need(sha(target)==rawreq['target_sha256'],'targets unchanged')
    old=B/'price-delay-clock-v2-pre2026-development-20261021';need(sha(old/'summary.json')==ia['old_summary_sha256'],'old account summary')
    for n,h in ia['old42_financial_sha256'].items():need(sha(old/n)==h,'old42 financial file')
    report={'status':'PASS_INDEPENDENT_PRIMARY_CAPTURE_TECHNICAL_AUDIT','request_sha256':EXPECTED,'freeze_commit':freeze,'manifest_sha256':sha(O/'manifest.json'),'audit_script_sha256':sha(Path(__file__)),'method_code_sha256':req['method_code_sha256'],'protocol_sha256':req['protocol_sha256'],'raw_manifest_sha256':req['raw_manifest_sha256'],'raw_question_audit_sha256':req['raw_audit_sha256'],'independent_raw_audit_sha256':req['independent_raw_source_audit_sha256'],'org_map_plan_sha256':req['org_map_plan_sha256'],'all15_source_cases_issuer_day_exact':True,'case_ids':sorted(cases),'reviewed_byte_reuse_documents':12,'fresh_documents':fresh,'HTTP_queries':queries,'HTTP_query_artifact_sha256':querymap,'all_artifact_sha256':allfiles,'all15_PDF_sha256':{k:d['sha256'] for k,d in docs.items()},'errors':0,'pending':0,'HTTP_logical_queries':6,'HTTP_query_budget':9,'attempts_per_query':1,'all_HTTP_bodies_complete_no_redirect_and_base64_bound':True,'all_three_listings_exact_issuer_Jul6_and_unique_implementation_notice':True,'original_raw_packets_targets_old_summary_and42_financial_files_unchanged':True,'2026_source_records_or_queries':False,'network_or_account_performed_by_auditor':False,'repository_modified':False,'financial_PDF_content_review_performed':False,'PIT_certified':False,'tax_certified':False,'formal_source_admission':False,'objective_achieved':False,'limitations':['Technical byte capture and metadata lineage only; PDF economic content is reviewed separately.','CNINFO listing identity and byteexact original/reused PDFs do not prove historical PIT arrival, statutory tax treatment or economic eligibility.','Logical HTTP reservation count is observed; broader transport attempt completeness is not certified.','Current organization-map provenance is authenticated as frozen metadata, not asserted as historical security-master evidence.'],'critical_or_important_findings':[]}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(OUT),'sha256':sha(OUT),'script_sha256':report['audit_script_sha256'],'documents':15,'reuse':12,'fresh':3,'logical_HTTP_queries':6,'artifacts':len(allfiles)}))
if __name__=='__main__':main()
