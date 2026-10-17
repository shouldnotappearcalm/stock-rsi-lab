"""Bounded issuer-notice capture for source discrepancies, not alpha feedback."""
import json
from pathlib import Path
from urllib.request import Request,urlopen

from scripts.capture_cninfo_csi500_reports_pre2026 import RateLimitedClient,atomic_json,sha256_file
from scripts.audit_cninfo_report_admission import CNINFO,publication_date

BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
OUTPUT=BASE/'reversal-full-corporate-notices-20261017'
CASES=(('SH601966','2024-06-01','2024-06-14'),('SH601966','2025-10-01','2025-10-23'),
       ('SH601966','2026-06-01','2026-06-24'),('SH600895','2026-10-01','2026-10-16'),
       ('SZ002508','2024-01-01','2024-01-10'),('SH603737','2026-05-01','2026-06-01'))
assert not OUTPUT.exists();OUTPUT.mkdir()
client=RateLimitedClient(.3)
orgs=json.loads((BASE/'cninfo-csi500-reports-20261017/plan.json').read_text())['org_by_code']
missing=[code for code,_,_ in CASES if code not in orgs]
if missing:
    mapping=client.fetch(CNINFO+'/new/data/szse_stock.json');atomic_json(OUTPUT/'routing-map.json',mapping)
    for row in mapping['stockList']:
        for code in missing:
            if row['code']==code[2:]:orgs[code]=row['orgId']
plan={'cases':CASES,'org_by_code':{c:orgs[c] for c,_,_ in CASES},'script_sha256':sha256_file(__file__),
      'raw_manifest_sha256':sha256_file(BASE/'reversal-raw-full-20261017/manifest.json'),
      'current_mapping_used_only_for_source_routing':True,'query_page_cap':5,'2026_strategy_returns_queried':False}
atomic_json(OUTPUT/'plan.json',plan);documents=[]
for code,start,end in CASES:
    assert '2024-01-01'<=start<=end<='2026-10-16'
    payload={'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
        'stock':code[2:]+','+orgs[code],'searchkey':'','secid':'','category':'','trade':'',
        'seDate':start+'~'+end,'sortName':'','sortType':'','isHLtitle':'true'}
    first=client.fetch(CNINFO+'/new/hisAnnouncement/query',payload);pages=(int(first.get('totalAnnouncement',0))+29)//30
    if pages>5:raise ValueError('notice query exceeded bounded page cap')
    rows=first.get('announcements') or []
    for page in range(2,pages+1):
        payload['pageNum']=str(page);rows.extend(client.fetch(CNINFO+'/new/hisAnnouncement/query',payload).get('announcements') or [])
    atomic_json(OUTPUT/(code+'-'+start+'-query.json'),rows)
    matches=[]
    for row in rows:
        day=publication_date(row['announcementTime'])
        if row['secCode']!=code[2:] or not start<=day<=end:raise ValueError('notice identity/window changed')
        if '权益分派实施公告' in row['announcementTitle']:matches.append((row,day))
    if not matches:raise ValueError('implementation notice unavailable: '+code+' '+start)
    for row,day in matches:
        url='https://static.cninfo.com.cn/'+row['adjunctUrl'];path=OUTPUT/(code+'-'+str(row['announcementId'])+'.pdf')
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:data=response.read(10*1024*1024+1)
        if not data.startswith(b'%PDF') or len(data)>10*1024*1024:raise ValueError('bounded original PDF required')
        path.write_bytes(data);documents.append({'instrument':code,'day':day,'title':row['announcementTitle'],
            'announcement_id':str(row['announcementId']),'url':url,'file':path.name,'sha256':sha256_file(path)})
        print(code,day,url,flush=True)
atomic_json(OUTPUT/'manifest.json',{'status':'REVERSAL_FULL_ORIGINAL_NOTICES_CAPTURED','documents':documents,
    'plan_sha256':sha256_file(OUTPUT/'plan.json'),'query_sha256':{p.name:sha256_file(p) for p in OUTPUT.glob('*-query.json')},
    '2026_strategy_returns_queried':False})
