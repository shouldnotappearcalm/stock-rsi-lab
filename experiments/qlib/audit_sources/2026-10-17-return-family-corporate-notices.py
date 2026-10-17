"""Capture three specific 2024 notices; no strategy or 2026 data query."""
import json
from pathlib import Path
from urllib.request import Request,urlopen

from scripts.capture_cninfo_csi500_reports_pre2026 import RateLimitedClient,sha256_file,atomic_json
from scripts.audit_cninfo_report_admission import query

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
OUTPUT=BASE/'return-family-corporate-notices-20261017'
CASES=(('SH600482','2024-11-01','2024-11-30','2024-11-15'),
       ('SH600167','2024-12-01','2024-12-31','2024-12-20'),
       ('SH600763','2024-07-01','2024-07-31','2024-07-01'))
assert not OUTPUT.exists();OUTPUT.mkdir()
orgs=json.loads((BASE/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
atomic_json(OUTPUT/'plan.json',{'cases':CASES,'capture_sha256':sha256_file(__file__),
    'raw_manifest_sha256':sha256_file(BASE/'return-families-raw-dev-20261017/manifest.json'),
    'purpose':'Missing special cash dividends and unsupported stock-dividend source evidence; no strategy change'})
client=RateLimitedClient(.3);documents=[]
for code,start,end,day in CASES:
    rows=query(orgs[code],code[2:],'',start,end,max_pages=5,fetch=client.fetch)
    atomic_json(OUTPUT/(code+'-query.json'),rows)
    matches=[r for r in rows if r['day']==day and '权益分派实施公告' in r['title']]
    if len(matches)!=1:raise ValueError('exact original implementation notice unavailable: '+code)
    row=matches[0];url='https://static.cninfo.com.cn/'+row['pdf_path'];path=OUTPUT/(code+'-'+day+'.pdf')
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:
        data=response.read(10*1024*1024+1)
    if not data.startswith(b'%PDF') or len(data)>10*1024*1024:raise ValueError('bounded original PDF required')
    path.write_bytes(data);documents.append({**row,'instrument':code,'url':url,'file':path.name,'sha256':sha256_file(path)})
    print(code,day,url,flush=True)
atomic_json(OUTPUT/'manifest.json',{'status':'THREE_2024_ORIGINAL_NOTICES_CAPTURED','documents':documents,
    'plan_sha256':sha256_file(OUTPUT/'plan.json'),'per_query_sha256':{p.name:sha256_file(p) for p in OUTPUT.glob('*-query.json')},
    '2026_strategy_returns_queried':False})
