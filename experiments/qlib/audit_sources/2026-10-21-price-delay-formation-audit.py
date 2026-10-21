import json,hashlib,struct,math
from pathlib import Path
from datetime import date,timedelta
from bisect import bisect_right,bisect_left
from functools import lru_cache
import numpy as np
from stock_rsi.qlib_snapshot import QlibSnapshot
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
P=B/'qlib-price-delay-pre2026-20261021';F=B/'price-delay-pre2026-formations-20261021'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
request=R/'experiments/qlib/price-delay-pre2026-formation-request.json';rq=read(request);summary=read(F/'summary.json');manifest=read(P/'manifest.json')
assert sha(request)==summary['request_sha256']
assert sha(P/'manifest.json')==rq['provider_manifest_sha256']==summary['provider_manifest_sha256']
assert sha(R/'docs/research/price-delay-pre2026-design-2026-10-21.md')==rq['design_sha256']
for n,h in rq['method_code_sha256'].items():assert sha(R/n)==h
for n,h in summary['artifact_sha256'].items():assert sha(F/n)==h
calendar=[date.fromisoformat(d) for d in (P/'calendars/day.txt').read_text().splitlines()]
assert calendar==sorted(set(calendar)) and calendar[-1]==date(2025,12,31)
assert manifest['all_output_values_at_or_before']==manifest['output_calendar_end']=='2025-12-31'
assert len(manifest['per_feature'])==4010 and manifest['equity_names']==501
for n,m in manifest['per_feature'].items():
 p=P/n;assert sha(p)==m['sha256']
 data=p.read_bytes();start=struct.unpack('<f',data[:4])[0];assert start==int(start) and int(start)==m['start_index']
 last=int(start)+len(data)//4-2
 assert last==m['last_index'] and last<len(calendar) and calendar[last].isoformat()==m['last_date']<='2025-12-31'
members={};prefix=('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')
for line in (P/'instruments/csi500.txt').read_text().splitlines():
 code,a,b=line.split();assert a<=b<='2025-12-31'
 if code.startswith(prefix):members.setdefault(code,[]).append((a,b))
codes=sorted(c for c,spans in members.items() if any(a<='2025-12-31' and b>='2023-12-29' for a,b in spans))
files=['instruments/all.txt']+[f'features/{c.lower()}/{field}.day.bin' for c in codes for field in ('open','high','low','close','volume','factor','amount','adjclose')]+['features/sh000905/adjclose.day.bin']
hash_input=hashlib.sha256()
for n in files:hash_input.update(n.encode()+b'\0'+(P/n).read_bytes()+b'\0')
assert hash_input.hexdigest()==rq['input_sha256']['price_files']
for n,h in rq['input_sha256'].items():
 if n!='price_files':assert sha(P/n)==h
snapshot=QlibSnapshot(P);assert list(snapshot.calendar)==calendar
@lru_cache(None)
def value(code,field,at):
 assert at<=date(2025,12,31)
 return snapshot.value(code,field,at.isoformat())
def pos(v):return v is not None and math.isfinite(v) and v>0
receipts=read(F/'formation_receipts.json');targets=read(F/'targets.json')
expected_days=[d for i,d in enumerate(calendar) if i and date(2024,1,2)<=d<=date(2025,12,31) and (d.year,d.month)!=(calendar[i-1].year,calendar[i-1].month)]
assert [r['execution_session'] for r in receipts]==[d.isoformat() for d in expected_days] and len(receipts)==24
assert set(targets)=={'price_delay_d1','eligible_equal_weight','low_delay_control'}
maxerr={k:0. for k in ('delay','r2_restricted','r2_full','alpha','coefficients')};total=0;checks=[];min_singular_ratio=1.;minimum_selection_margin=1.
for receipt,execution in zip(receipts,expected_days):
 prior=calendar[calendar.index(execution)-1];cap=prior.replace(day=1)-timedelta(days=1)
 marker=cap
 while marker.weekday()!=2:marker-=timedelta(days=1)
 markers=[marker-timedelta(weeks=i) for i in reversed(range(57))]
 endpoints=[calendar[bisect_right(calendar,m)-1] for m in markers]
 assert receipt['formation_asof']==prior.isoformat() and receipt['measurement_cap']==cap.isoformat()
 assert receipt['weekly_endpoints']==[{'marker':m.isoformat(),'session':s.isoformat()} for m,s in zip(markers,endpoints)]
 assert all(s<=m<=cap for m,s in zip(markers,endpoints))
 mc=[value('SH000905','close',d) for d in endpoints];assert all(pos(x) for x in mc)
 mr=[mc[i+1]/mc[i]-1 if endpoints[i+1]>endpoints[i] else None for i in range(56)]
 paired=[i for i in range(4,56) if all(mr[i-j] is not None for j in range(5))]
 assert len(paired)==receipt['market_paired_weeks']>=40
 names=sorted(c for c,spans in members.items() if any(a<=prior.isoformat()<=b for a,b in spans))
 assert len(names)==receipt['historical_members']>=200
 fits={};excluded={};missing={};obs_counts=[]
 for code in names:
  if not all(pos(value(code,f,prior)) for f in ('close','volume','factor')):
   excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
  y=[];x=[];missing_markers=[]
  for k in paired:
   start,stop=endpoints[k],endpoints[k+1]
   needed=calendar[bisect_left(calendar,start):bisect_right(calendar,stop)]
   assert max(needed)<=cap
   if not all(pos(value(code,f,d)) for d in needed for f in ('close','volume','factor')):
    missing_markers.append(markers[k+1].isoformat());continue
   y.append(value(code,'close',stop)/value(code,'close',start)-1)
   x.append([mr[k-j] for j in range(5)])
  bad=len(y)<40
  if not bad:
   y=np.asarray(y);x=np.asarray(x);yc=y-y.mean();xc=x-x.mean(axis=0);norm=np.linalg.norm(xc,axis=0)
   singular=np.linalg.svd(xc,compute_uv=False);min_singular_ratio=min(min_singular_ratio,float(singular[-1]/singular[0]))
   bad=float(yc@yc)<=1e-24 or min(norm)<=1e-12 or np.linalg.matrix_rank(xc,tol=1e-12*max(norm))<5
  if bad:
   excluded[code]='INSUFFICIENT_40_PAIRED_WEEKS_OR_DEGENERATE';continue
  fullx=np.column_stack([np.ones(len(y)),x]);restx=fullx[:,:2]
  coef=np.linalg.lstsq(fullx,y,rcond=None)[0];restricted=np.linalg.lstsq(restx,y,rcond=None)[0]
  rssfull=np.sum((y-fullx@coef)**2);rssrest=np.sum((y-restx@restricted)**2);tss=np.sum((y-y.mean())**2)
  r2full=1-rssfull/tss;r2rest=1-rssrest/tss
  if r2full<=1e-12:
   excluded[code]='INSUFFICIENT_40_PAIRED_WEEKS_OR_DEGENERATE';continue
  d1=1-r2rest/r2full;fits[code]=float(d1);total+=1;obs_counts.append(len(y))
  original=receipt['fits'][code]
  assert original['observations']==len(y)
  for k,v in [('delay',d1),('r2_restricted',r2rest),('r2_full',r2full),('alpha',coef[0])]:
   delta=abs(float(v)-original[k]);maxerr[k]=max(maxerr[k],delta);assert delta<1e-10,(code,execution,k,delta)
  error=max(abs(float(v)-a) for v,a in zip(coef[1:],original['coefficients']));maxerr['coefficients']=max(maxerr['coefficients'],error);assert error<1e-10
  if missing_markers:missing[code]=missing_markers
 assert set(fits)==set(receipt['fits']) and excluded==receipt['excluded'] and missing==receipt['missing_stock_weeks']
 assert len(fits)==receipt['eligible']>=100 and len(fits)>=.5*len(names)
 n=max(1,len(fits)//10);ordered=sorted(fits,key=lambda c:(-fits[c],c));low=sorted(fits,key=lambda c:(fits[c],c))[:n]
 assert ordered[:n]==receipt['selected'] and low==receipt['low_delay_control']
 minimum_selection_margin=min(minimum_selection_margin,fits[ordered[n-1]]-fits[ordered[n]])
 for family,chosen in [('price_delay_d1',ordered[:n]),('eligible_equal_weight',sorted(fits)),('low_delay_control',low)]:
  assert targets[family][execution.isoformat()]=={'as_of':prior.isoformat(),'weights':{c:.95/len(chosen) for c in chosen}}
 assert receipt['latest_measurement_price_read']==max(endpoints).isoformat() and receipt['latest_formation_price_read']==prior.isoformat()
 checks.append({'execution_session':execution.isoformat(),'measurement_cap':cap.isoformat(),'last_measurement_session':max(endpoints).isoformat(),'members':len(names),'eligible':len(fits),'selected':n,'market_paired_weeks':len(paired),'stock_observations_range':[min(obs_counts),max(obs_counts)]})
 print('verified',execution,len(fits),flush=True)
report={'status':'INDEPENDENT_NUMPY_ALL24_FORMATIONS_RECONSTRUCTED_NO_PORTFOLIO_ROI','request_sha256':sha(request),'formation_summary_sha256':sha(F/'summary.json'),'provider_manifest_sha256':sha(P/'manifest.json'),'formation_artifact_sha256':summary['artifact_sha256'],'auditor_source_sha256':sha(Path(__file__)),'frozen_method_and_design_bindings_checked':True,'capped_feature_hash_and_physical_extent_checks':4010,'equity_names':501,'physical_calendar_end':'2025-12-31','uncapped_provider_opened':False,'all24_measurement_caps_and_backward_weekly_endpoints_verified':True,'all_eligible_excluded_and_missing_weeks_exact':True,'all_actual_fits_numpy_reconstructed':total,'max_absolute_errors':maxerr,'minimum_actual_design_singular_ratio':min_singular_ratio,'minimum_high_decile_selection_boundary_gap':minimum_selection_margin,'all_three_family_targets_exact':True,'candidate':'price_delay_d1','controls_nonselectable_by_registered_design':['eligible_equal_weight','low_delay_control'],'formations':checks,'critical_findings':[],'important_findings':[],'limitations':['QlibSnapshot source reader reused as authorized; no production price_delay fit/ranking/endpoint helpers imported. NumPy lstsq independently estimates both intercept regressions on each reconstructed stock-specific paired sample.','Verified capped-provider hashes and physical extents, not a new independent reread of original uncapped source byte prefixes; original uncapped source was not opened.','Historical memberships and adjusted data are the frozen provider version, not certified historical announcement arrival/PIT.','Same eligibility/selection direction and descriptive-only controls verified in design and formation objects; forthcoming portfolio-runner selection gate not reviewed here.','No original-paper replication claim or portfolio-performance conclusion.'],'portfolio_returns_computed':False,'new_network_queries':0,'2026_market_values_read':False,'repository_files_modified':False}
out=Path('/tmp/price-delay-pre2026-formation-review-20261021.json');out.write_text(json.dumps(report,indent=2)+'\n');print('REPORT',sha(out),'FITS',total,'ERRORS',maxerr)
