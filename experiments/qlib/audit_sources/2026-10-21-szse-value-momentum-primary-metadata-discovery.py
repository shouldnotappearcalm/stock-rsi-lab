"""Four fixed primary-metadata discovery calls; raw bytes retained, no PDF/admission/ROI."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
CODES=('SZ000563','SZ002608','SZ002756','SZ002131');URL='https://www.cninfo.com.cn/new/hisAnnouncement/query'
h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def visible_rows(value,code):
 rows=value.get('announcements') or [];result=[]
 for r in rows:
  if r['secCode']!=code[2:]:raise ValueError('source issuer mismatch')
  day=datetime.fromtimestamp(r['announcementTime']/1000,timezone.utc).astimezone(timezone(__import__('datetime').timedelta(hours=8))).date().isoformat()
  if not '2026-10-01'<=day<='2026-10-20':raise ValueError('source publication outside fixed window')
  path=r.get('adjunctUrl','')
  if not path.startswith('finalpage/') or '..' in path:raise ValueError('unexpected original-reference path')
  result.append({'instrument':code,'publication_day':day,'title':r['announcementTitle'],'announcement_id':r['announcementId'],'original_url':'https://static.cninfo.com.cn/'+path})
 return result

def main():
 p=argparse.ArgumentParser()
 for n in ('plan','expected-plan-sha256','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args();planfile=Path(a.plan);out=Path(a.output_dir)
 assert not out.exists() and h(planfile)==a.expected_plan_sha256
 plan=read(planfile);assert plan['method_sha256']==h(__file__) and [r['instrument'] for r in plan['requests']]==list(CODES)
 old=Path(plan['organization_map_file']);assert h(old)==plan['organization_map_sha256'];org=read(old)['org_by_code']
 for r in plan['requests']:
  assert r['url']==URL and r['payload']=={'pageNum':'1','pageSize':'30','column':'szse','tabName':'fulltext','plate':'','stock':r['instrument'][2:]+','+org[r['instrument']],'searchkey':'','secid':'','category':'','trade':'','seDate':'2026-10-01~2026-10-20','sortName':'','sortType':'','isHLtitle':'true'}
 fixture={'announcements':[{'secCode':'000563','announcementTime':1791907200000,'announcementTitle':'fixture','announcementId':'fixture','adjunctUrl':'finalpage/2026-10-14/fixture.PDF'}]}
 visible_rows(fixture,'SZ000563')
 try:visible_rows(fixture,'SZ002608')
 except ValueError:pass
 else:raise AssertionError('issuer mutation accepted')
 bad=json.loads(json.dumps(fixture));bad['announcements'][0]['adjunctUrl']='../other'
 try:visible_rows(bad,'SZ000563')
 except ValueError:pass
 else:raise AssertionError('unsafe reference accepted')
 if a.preflight_only:print('four exact metadata requests authenticated; no calls/output');return
 out.mkdir(parents=True);(out/'plan.json').write_bytes(planfile.read_bytes());results=[]
 for r in plan['requests']:
  c=r['instrument'];folder=out/c;folder.mkdir();(folder/'request.json').write_text(json.dumps(r,indent=2)+'\n')
  reserved={'instrument':c,'reserved_at':datetime.now(timezone.utc).isoformat(),'plan_sha256':h(planfile),'attempt':1}
  (folder/'reserved-1.json').write_text(json.dumps(reserved,indent=2)+'\n');result={'instrument':c,'status':'ERROR'}
  try:
   req=Request(URL,data=urlencode(r['payload']).encode(),headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'})
   with urlopen(req,timeout=20) as response:raw=response.read();http=response.status
   (folder/'response-1.bin').write_bytes(raw);value=json.loads(raw);rows=visible_rows(value,c)
   result.update(status='CAPTURED',http_status=http,raw_sha256=h(folder/'response-1.bin'),total_announcements=value.get('totalAnnouncement'),one_page_only=True,complete_metadata_coverage=value.get('totalAnnouncement',0)<=30,rows=rows)
  except Exception as exc:result.update(error_type=type(exc).__name__,error=str(exc))
  result.update(received_at=datetime.now(timezone.utc).isoformat(),request_sha256=h(folder/'request.json'),reservation_sha256=h(folder/'reserved-1.json'))
  (folder/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result);print(c,result['status'],len(result.get('rows',[])),flush=True)
 manifest={'status':'FOUR_PRIMARY_METADATA_RESPONSES_DISCOVERY_ONLY','plan_sha256':h(planfile),'logical_attempts':4,'max_attempts_per_request':1,'results':results,'pdf_originals_captured':False,'source_admission':False,'portfolio_returns_computed':False,'objective_achieved':False}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
