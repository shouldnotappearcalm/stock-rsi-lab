"""Independent34formation audit: own struct binary reader and NumPy OLS.
Reuses the published independent pre2026 auditor's mathematical design only.
No project snapshot/factor/fit/ranking imports, account replay, ROI or network.
"""
from pathlib import Path
from datetime import date,timedelta
from bisect import bisect_left,bisect_right
from functools import lru_cache
import hashlib,json,math,struct,subprocess
import numpy as np
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
P=B/'qlib-enhanced-dev';OLD=B/'qlib-price-delay-pre2026-20261021';F=B/'price-delay-horizon-formations-20261021';OF=B/'price-delay-pre2026-formations-20261021'
PLAN=R/'experiments/qlib/price-delay-horizon-formation-plan.json';REPORT=Path('/tmp/price-delay-horizon-formation-independent-audit-20261021.json')
EXPECTED='0a2d18136247770b0ef605063d8f818c1f75940e4e20a3d754b261dccc997b82'
REFERENCE=R/'experiments/qlib/audit_sources/2026-10-21-price-delay-formation-audit.py'
PREFIXES=('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003')
FIELDS=('open','high','low','close','volume','factor','amount','adjclose')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def need(v,s):
    if not v:raise AssertionError(s)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def serialized(v):return (json.dumps(v,indent=2)+'\n').encode()
def input_digest(codes):
    names=['instruments/all.txt']+[f'features/{c.lower()}/{field}.day.bin' for c in sorted(codes) for field in FIELDS]+['features/sh000905/adjclose.day.bin'];h=hashlib.sha256();filehash={}
    for name in names:
        raw=(P/name).read_bytes();h.update(name.encode()+b'\0'+raw+b'\0');filehash[name]=hashlib.sha256(raw).hexdigest()
    return h.hexdigest(),filehash

def main():
    plan=read(PLAN);summary=read(F/'summary.json');freeze=subprocess.check_output(['git','rev-parse','27da939'],cwd=R,text=True).strip()
    need(sha(PLAN)==EXPECTED==summary['plan_sha256'] and hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+str(PLAN.relative_to(R))],cwd=R)).hexdigest()==EXPECTED,'frozen plan')
    need(plan['candidate']=='price_delay_d1' and plan['candidate_budget']==1 and plan['formation_count']==34 and plan['window']==['2024-01-02','2026-10-20'] and plan['portfolio_returns_to_compute'] is False and plan['investment_rule_changes_permitted'] is False,'fixed forward formation scope')
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('immutable_financial_sha256',B)]:
        for name,h in plan[field].items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(root/name)==h,'bound identity '+name)
            if root==R:need(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+name],cwd=R)).hexdigest()==h,'freeze blob '+name)
    need(len(plan['method_code_sha256'])==9 and len(plan['public_evidence_sha256'])==8 and len(plan['local_source_sha256'])==5 and len(plan['immutable_financial_sha256'])==48,'complete binding scope counts')
    prior=read(B/'price-delay-intraday-pre2026-20261021/summary.json');audit=read(R/'experiments/qlib/price-delay-intraday-independent-ledger-audit.json');verification=read(R/'experiments/qlib/price-delay-intraday-verification.json');review=read(R/'experiments/qlib/price-delay-intraday-output-review.json')
    need(prior['raw_development_confirmation_passes'] is True and audit['all_six_profile_ledgers_reconstructed'] is True and audit['development_confirmation_passes_independently'] is True and audit['imports_project_code'] is False and audit['summary_sha256']==sha(B/'price-delay-intraday-pre2026-20261021/summary.json') and verification['root_ledger_reproduction_byte_identical'] is True and review['ready_for_2026_source_design'] is True,'development gate evidence')
    financial={f'price-delay-intraday-pre2026-20261021/{label}/{n}':h for label,v in prior['results_by_profile'].items() for n,h in v['artifact_sha256'].items()};need(financial==plan['immutable_financial_sha256'],'all48financialidentities')
    prereq=read(R/'experiments/qlib/price-delay-pre2026-formation-request.json');source_request=read(R/'experiments/qlib/price-delay-provider-pre2026-request.json')
    for name,h in prereq['method_code_sha256'].items():need(sha(R/name)==h,'original formation rule untouched')
    calendar=[date.fromisoformat(d) for d in (P/'calendars/day.txt').read_text().splitlines()];need(calendar==sorted(set(calendar)) and calendar[-1].isoformat()==plan['source_calendar_end']=='2026-10-13','source explicit calendar')
    index={d:i for i,d in enumerate(calendar)};members={}
    for line in (P/'instruments/csi500.txt').read_text().splitlines():
        code,a,b=line.split();need(date.fromisoformat(a)<=date.fromisoformat(b),'valid membership span')
        if code.startswith(PREFIXES):members.setdefault(code,[]).append((a,b))
    original_codes=sorted(c for c,spans in members.items() if any(a<='2025-12-31' and b>='2023-12-29' for a,b in spans));fullcodes=sorted(c for c,spans in members.items() if any(a<='2026-10-20' and b>='2023-12-29' for a,b in spans))
    need(len(original_codes)==501 and len(fullcodes)==526 and fullcodes==plan['full_source_codes'],'501old/526full source scope')
    old_source_digest,_=input_digest(original_codes);full_digest,fullhash=input_digest(fullcodes)
    need(old_source_digest==plan['source_input_sha256']['price_files'] and plan['source_input_sha256']==source_request['source_input_sha256'] and full_digest==plan['full_price_input_digest'],'complete original and full source aggregate hashes')
    for name,h in plan['source_input_sha256'].items():
        if name!='price_files':need(sha(P/name)==h,'source auxiliary hash');fullhash[name]=h
    pm=read(OLD/'manifest.json');need(sha(OLD/'manifest.json')==prereq['provider_manifest_sha256'] and len(pm['per_feature'])==4010,'old physical provider identity')
    need(pm['all_output_values_at_or_before']=='2025-12-31','old physical cutoff')
    prefixhash={}
    for name,meta in pm['per_feature'].items():
        clipped=(OLD/name).read_bytes();need(hashlib.sha256(clipped).hexdigest()==meta['sha256'],'old4010featurehash')
        need(len(clipped)%4==0 and len(clipped)>=8,'binaryprefixlength');off=struct.unpack('<f',clipped[:4])[0];need(off==int(off) and int(off)+len(clipped)//4-2==meta['last_index'],'prefixoffsetextent')
        with (P/name).open('rb') as f:need(f.read(len(clipped))==clipped,'exact original pre2026 byte prefix')
        prefixhash[name]=meta['sha256']
    need(set(summary['artifact_sha256'])=={'targets.json','formation_receipts.json','candidate_targets.json'},'complete output artifact scope')
    for name,h in summary['artifact_sha256'].items():need(sha(F/name)==h,'formation artifact hash')
    targets=read(F/'targets.json');receipts=read(F/'formation_receipts.json');oldtargets=read(OF/'targets.json');oldreceipts=read(OF/'formation_receipts.json')
    prefix={family:{d:t for d,t in values.items() if d<='2025-12-31'} for family,values in targets.items()};prefixreceipts=[r for r in receipts if r['execution_session']<='2025-12-31']
    need(prefix==oldtargets and prefixreceipts==oldreceipts and serialized(prefix)==(OF/'targets.json').read_bytes() and serialized(prefixreceipts)==(OF/'formation_receipts.json').read_bytes(),'original24object and serializedbyteprefix exact')
    need(read(F/'candidate_targets.json')==targets['price_delay_d1'],'candidate export')
    @lru_cache(None)
    def binary(code,field):
        need(code in set(fullcodes)|{'SH000905'} and field in ('close','factor','volume'),'only registered factor fields')
        path=P/f'features/{code.lower()}/{field}.day.bin';raw=path.read_bytes();need(len(raw)>=8 and len(raw)%4==0,'float32 feature length')
        vals=struct.unpack('<'+'f'*(len(raw)//4),raw);offset=vals[0];need(math.isfinite(offset) and offset==int(offset) and 0<=offset<len(calendar) and int(offset)+len(vals)-1<=len(calendar),'binary offset/extent')
        return int(offset),vals[1:]
    latest_decoded=None;read_count=0
    @lru_cache(None)
    def value(code,field,day):
        nonlocal latest_decoded,read_count
        need(day in index and day<=date(2026,10,13),'authorized date boundary');latest_decoded=max(day,latest_decoded) if latest_decoded else day;read_count+=1
        offset,vals=binary(code,field);n=index[day]-offset
        if n<0 or n>=len(vals):return None
        v=vals[n];return v if math.isfinite(v) else None
    def positive(v):return v is not None and math.isfinite(v) and v>0
    expected_days=[d for i,d in enumerate(calendar) if i and date(2024,1,2)<=d<=date(2026,10,20) and (d.year,d.month)!=(calendar[i-1].year,calendar[i-1].month)]
    need(len(expected_days)==34 and [r['execution_session'] for r in receipts]==[d.isoformat() for d in expected_days] and set(targets)=={'price_delay_d1','eligible_equal_weight','low_delay_control'},'complete34monthlykeys')
    for family,t in targets.items():need(list(t)==[d.isoformat() for d in expected_days],'all34familykeys')
    maxerr={k:0. for k in ['delay','r2_restricted','r2_full','alpha','coefficients']};totalfits=0;checks=[];minsingular=1.;mingap=1.;reconstructed_targets={name:{} for name in targets}
    for receipt,execution in zip(receipts,expected_days):
        prior_day=calendar[index[execution]-1];cap=prior_day.replace(day=1)-timedelta(days=1);lastmarker=cap-timedelta(days=(cap.weekday()-2)%7);markers=[lastmarker-timedelta(weeks=i) for i in reversed(range(57))];endpoints=[calendar[bisect_right(calendar,m)-1] for m in markers]
        need(receipt['formation_asof']==prior_day.isoformat() and receipt['measurement_cap']==cap.isoformat() and receipt['weekly_endpoints']==[{'marker':m.isoformat(),'session':s.isoformat()} for m,s in zip(markers,endpoints)] and all(s<=m<=cap for m,s in zip(markers,endpoints)),'backward weekly endpoint and skip-latest-month design')
        market=[value('SH000905','close',d) for d in endpoints];need(all(positive(v) for v in market),'positive market endpoints')
        mr=[market[i+1]/market[i]-1 if endpoints[i+1]>endpoints[i] else None for i in range(56)];paired=[i for i in range(4,56) if all(mr[i-j] is not None for j in range(5))];need(len(paired)==receipt['market_paired_weeks']>=40,'market contemporaneous plus4lags')
        names=sorted(c for c,spans in members.items() if any(a<=prior_day.isoformat()<=b for a,b in spans));need(len(names)==receipt['historical_members']>=200,'historical member pool')
        fits={};excluded={};missing={};obs=[]
        for code in names:
            if not all(positive(value(code,f,prior_day)) for f in ('close','factor','volume')):excluded[code]='MISSING_OR_INACTIVE_FORMATION';continue
            y=[];x=[];badweeks=[]
            for k in paired:
                left,right=endpoints[k],endpoints[k+1];needed=calendar[bisect_left(calendar,left):bisect_right(calendar,right)];need(max(needed)<=cap,'stock measurement no lookahead')
                if right<=left or not all(positive(value(code,f,d)) for d in needed for f in ('close','factor','volume')):badweeks.append(markers[k+1].isoformat());continue
                y.append(value(code,'close',right)/value(code,'close',left)-1);x.append([mr[k-j] for j in range(5)])
            bad=len(y)<40
            if not bad:
                y=np.asarray(y,dtype=float);x=np.asarray(x,dtype=float);yc=y-y.mean();xc=x-x.mean(axis=0);norm=np.linalg.norm(xc,axis=0);singular=np.linalg.svd(xc,compute_uv=False)
                if singular[0]>0:minsingular=min(minsingular,float(singular[-1]/singular[0]))
                bad=float(yc@yc)<=1e-24 or float(min(norm))<=1e-12 or np.linalg.matrix_rank(xc,tol=1e-12*float(max(norm)))<5
            if bad:excluded[code]='INSUFFICIENT_40_PAIRED_WEEKS_OR_DEGENERATE';continue
            fullx=np.column_stack([np.ones(len(y)),x]);restx=fullx[:,:2];coef=np.linalg.lstsq(fullx,y,rcond=None)[0];restricted=np.linalg.lstsq(restx,y,rcond=None)[0];rssfull=np.sum((y-fullx@coef)**2);rssrest=np.sum((y-restx@restricted)**2);tss=np.sum((y-y.mean())**2);r2full=1-rssfull/tss;r2rest=1-rssrest/tss
            if r2full<=1e-12:excluded[code]='INSUFFICIENT_40_PAIRED_WEEKS_OR_DEGENERATE';continue
            score=1-r2rest/r2full;fits[code]=float(score);totalfits+=1;obs.append(len(y));stored=receipt['fits'][code]
            need(set(stored)=={'delay','r2_restricted','r2_full','alpha','coefficients','observations'} and stored['observations']==len(y) and len(stored['coefficients'])==5,'full stored fit schema/sample')
            for name,v in [('delay',score),('r2_restricted',r2rest),('r2_full',r2full),('alpha',coef[0])]:
                err=abs(float(v)-stored[name]);maxerr[name]=max(maxerr[name],err);need(err<1e-10,'NumPy fit '+execution.isoformat()+' '+code+' '+name)
            err=max(abs(float(v)-a) for v,a in zip(coef[1:],stored['coefficients']));maxerr['coefficients']=max(maxerr['coefficients'],err);need(err<1e-10,'NumPy all5coefficients')
            if badweeks:missing[code]=badweeks
        need(set(fits)==set(receipt['fits']) and excluded==receipt['excluded'] and missing==receipt['missing_stock_weeks'],'all eligible/excluded/missing weeks exact')
        need(len(fits)==receipt['eligible']>=100 and len(fits)>=.5*len(names),'coverage gate')
        count=max(1,len(fits)//10);highorder=sorted(fits,key=lambda c:(-fits[c],c));high=highorder[:count];low=sorted(fits,key=lambda c:(fits[c],c))[:count]
        need(high==receipt['selected'] and low==receipt['low_delay_control'],'fixed deciles and deterministic code tie break');mingap=min(mingap,fits[highorder[count-1]]-fits[highorder[count]])
        for family,chosen in [('price_delay_d1',high),('eligible_equal_weight',sorted(fits)),('low_delay_control',low)]:
            expected={'as_of':prior_day.isoformat(),'weights':{c:.95/len(chosen) for c in chosen}};need(targets[family][execution.isoformat()]==expected,'all3families ranks/weights exact');reconstructed_targets[family][execution.isoformat()]=expected
        need(receipt['latest_measurement_price_read']==max(endpoints).isoformat() and receipt['latest_formation_price_read']==prior_day.isoformat(),'exact last-read timing')
        checks.append({'execution_session':execution.isoformat(),'formation_asof':prior_day.isoformat(),'measurement_cap':cap.isoformat(),'last_measurement_session':max(endpoints).isoformat(),'members':len(names),'eligible':len(fits),'selected_count':count,'market_paired_weeks':len(paired),'stock_observations_range':[min(obs),max(obs)],'all_fit_and_missing_fields_checked':True})
        print('Independent formation',execution.isoformat(),len(fits),'fits verified',flush=True)
    need(reconstructed_targets==targets,'entire34targetobject')
    need(summary['original_24_formations_and_receipts_identical'] is True and summary['formations']==34 and summary['portfolio_returns_computed'] is False and summary['investment_rule_changed'] is False and summary['controls_selectable'] is False and summary['source_calendar_end']=='2026-10-13' and summary['unconditional_interim_observation_end']=='2026-10-20' and summary['full_October_2026_complete'] is False,'truthful summary scope')
    for field,root in [('method_code_sha256',R),('public_evidence_sha256',R),('local_source_sha256',B),('immutable_financial_sha256',B)]:
        for name,h in plan[field].items():need(sha(root/name)==h,'all frozen identities unchanged after audit')
    need(input_digest(fullcodes)[0]==plan['full_price_input_digest'] and sha(PLAN)==EXPECTED,'all526source digest unchanged after audit')
    report={'status':'INDEPENDENT_NUMPY_STRUCT_ALL34_PRICE_DELAY_FORMATIONS_RECONSTRUCTED_NO_PORTFOLIO_RETURNS','summary_sha256':sha(F/'summary.json'),'all34_formations_independently_reconstructed':True,'original24_prefix_identical':True,'imports_project_code':False,'audit_code_sha256':sha(Path(__file__)),'portfolio_returns_computed':False,'plan_sha256':EXPECTED,'freeze_commit':freeze,'artifact_sha256':summary['artifact_sha256'],'method_code_sha256':plan['method_code_sha256'],'independent_mathematical_reference':{'file':str(REFERENCE.relative_to(R)),'sha256':sha(REFERENCE),'reference_QlibSnapshot_not_imported':True,'adaptation':'Own struct little-endian float32 reader replaces production snapshot; independent NumPy lstsq on each stock-specific paired sample, unchanged published34formation design.'},'full_source_names_authenticated':526,'full_source_aggregate_sha256':full_digest,'full_source_file_sha256':fullhash,'original4010_physical_prefixes_byte_identical':True,'original4010_prefix_sha256':prefixhash,'all48_financial_files_unchanged':True,'immutable_financial_sha256':financial,'pre2026_gate_evidence_bound':True,'original24_targets_serialized_bytes_identical':True,'original24_complete_receipts_serialized_bytes_identical':True,'all34_three_family_targets_exact':True,'all_eligibility_exclusions_missing_weeks_and_lag_metadata_exact':True,'all_individual_fits_numpy_reconstructed':totalfits,'max_absolute_fit_errors':maxerr,'minimum_design_singular_ratio':minsingular,'minimum_high_decile_selection_boundary_gap':mingap,'formations':checks,'reader_decoded_feature_files':binary.cache_info().currsize,'reader_unique_value_requests':read_count,'latest_quote_date_decoded':latest_decoded.isoformat(),'source_calendar_end':'2026-10-13','full_October_2026_complete':False,'new_2026_source_quotes_read_as_authorized':True,'investment_rule_changed':False,'controls_selectable':False,'2026_account_or_ROI_computed':False,'network_calls':0,'repository_modified':False,'candidate_promoted':False,'objective_achieved':False,'critical_or_important_findings':[],'limitations':['Forward application of one frozen rule only; no portfolio account, ROI, new candidate comparison or method change.','All pre2026prefixes are independently bytecompared with the authorized full provider; source-file hashes bind the current vendor snapshot, not historical PIT arrival or unrevised data.','The full provider calendar ends2026-10-13 and only monthly formations throughOctober are constructed. Oct20is an unconditional interim observation cutoff; fullOctober is incomplete.','NumPy OLS matches all stored coefficients/Rsquared/delay values within1e-10, with exact eligibility, missing-week, ranks and target weights.','Original24targets and complete receipts are exact objects and exact reserialized prior artifacts; all48financial files stay unchanged.']}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(REPORT),'report_sha256':sha(REPORT),'audit_code_sha256':report['audit_code_sha256'],'formations':34,'fits':totalfits,'max_errors':maxerr,'prefixes':4010,'financial_files':48,'portfolio_returns_computed':False}))
if __name__=='__main__':main()
