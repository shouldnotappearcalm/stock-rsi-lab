"""Three exact pre2026 implementation notices, never a portfolio run."""
import json
from pathlib import Path
from urllib.request import Request,urlopen
from scripts.capture_cninfo_csi500_reports_pre2026 import RateLimitedClient,atomic_json,sha256_file
from scripts.audit_cninfo_report_admission import query

B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('experiments/qlib/illiquidity-corporate-notice-request.json')
OUTPUT=B/'illiquidity-corporate-notices-20261020'
r=json.loads(R.read_text())
assert r['status']=='FROZEN_THREE_PRE2026_ILLIQUIDITY_CORPORATE_NOTICES'
assert sha256_file(__file__)==r['capture_code_sha256']
for f,h in r['shared_method_sha256'].items():assert sha256_file(f)==h
assert sha256_file(B/'cninfo-csi500-reports-20261017/plan.json')==r['org_map_plan_sha256']
assert sha256_file(B/'illiquidity-raw-source-continuation-20261020/manifest.json')==r['raw_manifest_sha256']
assert not OUTPUT.exists();OUTPUT.mkdir();(OUTPUT/'request.json').write_bytes(R.read_bytes())
orgs=json.loads((B/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
client=RateLimitedClient(.3);documents=[];responses=[]
def fetch(url,payload):
    value=client.fetch(url,payload)
    path=OUTPUT/('http-response-'+str(len(responses)+1)+'.json')
    atomic_json(path,{'url':url,'request_payload':dict(payload),'response':value})
    responses.append({'file':path.name,'sha256':sha256_file(path)})
    return value
try:
    assert len(r['cases'])==3 and r['max_pages_per_exact_day']==2
    for case in r['cases']:
        code,day=case['instrument'],case['publication_day']
        assert '2024-01-01'<=day<='2025-12-31' and orgs[code]==case['organization_id']
        rows=query(orgs[code],code[2:],'',day,day,max_pages=2,fetch=fetch)
        atomic_json(OUTPUT/(code+'-query.json'),rows)
        matches=[x for x in rows if x['code']==code[2:] and x['day']==day and '权益分派实施公告' in x['title']]
        if len(matches)!=1:raise ValueError('exact original implementation notice not unique: '+code)
        row=matches[0];url='https://static.cninfo.com.cn/'+row['pdf_path'];path=OUTPUT/(code+'-'+day+'.pdf')
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:
            data=response.read(10*1024*1024+1)
        path.write_bytes(data)
        if not data.startswith(b'%PDF') or len(data)>10*1024*1024:raise ValueError('source is not a bounded PDF')
        documents.append({**row,'instrument':code,'url':url,'file':path.name,'sha256':sha256_file(path)})
        atomic_json(OUTPUT/'progress.json',{'documents':documents,'http_responses':responses})
        print(code,day,path.name,flush=True)
except Exception as exc:
    atomic_json(OUTPUT/'failure.json',{'error_type':type(exc).__name__,'error':str(exc),'documents':documents,'http_responses':responses})
    raise
manifest={'status':'THREE_PRE2026_ILLIQUIDITY_IMPLEMENTATION_NOTICES_CAPTURED',
    'request_sha256':sha256_file(R),'documents':documents,'http_responses':responses,
    'successful_api_page_responses':client.requests,'maximum_page_attempts_including_retries':18,
    'api_error_wire_bodies_preserved':False,'global_cross_restart_retry_bound_claimed':False,
    'documents_financially_reviewed':False,'new_2026_market_queries':False,
    'investment_rule_changed':False,'portfolio_returns_computed':False,'objective_achieved':False}
atomic_json(OUTPUT/'manifest.json',manifest)
print('three original notices captured; require numeric/tax review',flush=True)
