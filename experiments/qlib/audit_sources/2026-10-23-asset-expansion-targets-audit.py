"""Separate native scalar/rational target reconstruction, no project imports."""
import argparse,copy,hashlib,json,math,re,struct
from collections import Counter,defaultdict
from datetime import datetime,time
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

PRIMARY='low_asset_expansion_decile_conditional'
HIGH='high_asset_expansion_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',HIGH)
PROVIDER='qlib-enhanced-dev'
OLD_PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
VIEWS='asset-expansion-monthly-availability-through2026-v1-20261023'
OLD_RUN='asset-expansion-conditional-development-v1-20261022'


def need(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def canonical(v):return json.loads(json.dumps(v,allow_nan=False))
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}


class NativeQuotes:
    """Decode only the requested scalar, with an explicit independent asof."""
    def __init__(self,root):
        self.root=Path(root);self.days=(self.root/'calendars/day.txt').read_text().splitlines()
        need(self.days and self.days==sorted(set(self.days)),'native ordered explicit quote calendar')
        self.index={d:i for i,d in enumerate(self.days)};self.cache={}

    def value(self,code,field,day,*,as_of):
        need(day<=as_of<='2026-10-21' and day in self.index,'native prior-close scalar boundary')
        need(re.fullmatch(r'(SH|SZ)[0-9]{6}',code) and field in ('close','volume','factor'),'native scalar source identity')
        key=(code,field,day)
        if key in self.cache:return self.cache[key]
        p=self.root/'features'/code.lower()/(field+'.day.bin');size=p.stat().st_size
        need(size>=8 and size%4==0,'native feature byte extent')
        with p.open('rb') as f:
            first=struct.unpack('<f',f.read(4))[0];need(math.isfinite(first) and first==int(first),'native integer source offset')
            start,count=int(first),size//4-1;need(start>=0 and start+count<=len(self.days),'native feature within actual calendar')
            offset=self.index[day]-start
            if not 0<=offset<count:value=None
            else:
                f.seek(4*(offset+1));value=struct.unpack('<f',f.read(4))[0]
                if not math.isfinite(value):value=None
        self.cache[key]=value;return value


def derive_formation(view,cases,cohort,memberships,quotes,execution,previous):
    clock=datetime.combine(datetime.fromisoformat(previous).date(),time(15,5),ZoneInfo('Asia/Shanghai'))
    need(datetime.fromisoformat(view['as_of'])==clock and view['visibility_mode']=='RECONSTRUCTED_PUBLICATION_DAY_END'
        and view['cohort_count']==len(cohort) and [r['instrument'] for r in view['classifications']]==sorted(cohort),
        'independent whole-cohort source clock')
    active={c for c in cohort if any(a<=previous<=b for a,b in memberships.get(c,[]))}
    minimum=int(previous[:4])-(2 if previous[5:7]<='06' else 1);admission=[];scores={};evidence={}
    for row in view['classifications']:
        code=row['instrument'];reason=None
        if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
        elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
        elif 'selected_capture_key' not in row:
            need(row['annual_status'] in ('NO_VISIBLE_ANNUAL_REPORT','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'),'independent unresolved source selection')
            reason=row['annual_status']
        elif row['latest_fiscal_year']<minimum:reason='STALE_ANNUAL_ASSETS'
        if reason is None:
            c=cases[row['selected_capture_key']]
            need(c['capture_key']==row['selected_capture_key'] and c['instrument']==code and c['fiscal_year']==row['latest_fiscal_year']
                and c['source_sha256']==row['selected_source_sha256'],'independent original selected edition')
            report=c['asset_report']
            if c['status']!='ASSET_CELLS_SUPPORTED_PENDING_SOURCE_QA':
                need(c['status'] in ('ASSET_SOURCE_SCHEMA_UNSUPPORTED','COVER_IDENTITY_UNVERIFIED') and report is None,
                    'latest failure has no admissible older numeric fallback')
                reason='LATEST_'+c['status']
            else:
                need(report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'})
                    and datetime.fromisoformat(report['public_day_end_at'])<=clock and report['instrument']==code
                    and report['report_year']==row['latest_fiscal_year'] and report['publication_day']==row['latest_publication_day']
                    and report['payload']['document_sha256']==row['selected_source_sha256'] and report['payload']['scope']=='CONSOLIDATED',
                    'one immutable visible consolidated annual source')
                year=row['latest_fiscal_year'];current,prior=f'{year}-12-31',f'{year-1}-12-31';balances=report['payload']['balances']
                need(current in balances and set(balances)<={current,prior},'only explicit adjacent year-end balances')
                if prior not in balances:reason='LATEST_HAS_NO_EXPLICIT_PRIOR_YEAR_END'
                else:
                    values={}
                    for i,period in enumerate((current,prior)):
                        cell=balances[period]
                        need(cell['column_index']==i and cell['fiscal_end']==period and cell['statement']=='合并资产负债表'
                            and cell['row_text_sha256']==digest(cell['row_text']),'independent literal fiscal asset column')
                        value=Fraction(cell['literal'].replace(',',''))*{'元':1,'万元':10000}[cell['unit']]
                        need(value>0 and value==Fraction(cell['value_CNY']),'independent exact CNY asset amount')
                        values[period]=value
                    scalars=[quotes.value(code,f,previous,as_of=previous) for f in ('close','volume','factor')]
                    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in scalars):reason='NO_POSITIVE_FORMATION_QUOTE'
                    else:
                        scores[code]=(values[current]-values[prior])/values[prior]
                        evidence[code]={'record_id':report['record_id'],'source_sha256':row['selected_source_sha256'],
                            'capture_key':row['selected_capture_key'],'report_year':year,'current_fiscal_end':current,'prior_fiscal_end':prior,
                            'publication_day':report['publication_day'],'expansion_fraction':str(scores[code])}
                        reason='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'
        admission.append({'instrument':code,'reason':reason})
    need(len(scores)>=100,'independent unchanged100-name diversification guard')
    count=len(scores)//10
    choices={PRIMARY:sorted(scores,key=lambda c:(scores[c],c))[:count],
        'eligible_equal_weight':sorted(scores),HIGH:sorted(scores,key=lambda c:(-scores[c],c))[:count]}
    targets={n:{'as_of':previous,'weights':{c:.95/len(selected) for c in selected}} for n,selected in choices.items()}
    receipt={'execution_session':execution,'formation_asof':previous,'source_as_of':view['as_of'],
        'initial_source_cohort':len(cohort),'formation_members':len(active),'eligible':len(scores),
        'eligible_fraction_of_active_initial_cohort':len(scores)/len(active),'minimum_fiscal_year':minimum,
        'cohort_admission':admission,'admission_counts':dict(Counter(r['reason'] for r in admission)),
        'ranked_source':evidence,'selections':choices,'latest_factor_price_read':previous,
        'metadata_selection_precedes_GP_numeric_status_filter':True,'source_availability':'RECONSTRUCTED_PUBLICATION_DAY_END',
        'classification_vintage':'2021Q3','historical_arrival_verified':False,'current_business_identity_verified':False,
        'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False}
    return targets,receipt


def check_formation(targets,receipt,*args):
    expected,source=derive_formation(*args)
    need(targets==expected and receipt==source,'independent exact target/eligibility/rational-expansion reconstruction')
    need(all(list(targets[n]['weights'])==list(expected[n]['weights']) for n in NAMES),'independent exact selection order')
    need(all(receipt[f] is False for f in ('historical_arrival_verified','current_business_identity_verified',
        'financial_reporting_compatibility_verified','investment_factor_admitted')),'strict target evidence limits')
    return expected,source


def negative_controls(targets,receipt,args):
    rejected=[]
    for name in ('wrong_weight','missing_primary_name','forged_expansion','wrong_coverage','future_quote_receipt','relabelled_exclusion'):
        t,r=copy.deepcopy(targets),copy.deepcopy(receipt);first=next(iter(t[PRIMARY]['weights']))
        if name=='wrong_weight':t[PRIMARY]['weights'][first]=.94
        elif name=='missing_primary_name':t[PRIMARY]['weights'].pop(first)
        elif name=='forged_expansion':r['ranked_source'][first]['expansion_fraction']='999'
        elif name=='wrong_coverage':r['eligible']=99
        elif name=='future_quote_receipt':r['latest_factor_price_read']=r['execution_session']
        else:next(x for x in r['cohort_admission'] if x['reason']!='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED')['reason']='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'
        try:check_formation(t,r,*args)
        except ValueError:rejected.append(name)
        else:raise ValueError('semantic negative accepted: '+name)
    return rejected


def main():
    p=argparse.ArgumentParser()
    for n in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();repo,base,membership,request,run,out=(Path(getattr(a,n)).resolve()
        for n in ('repo_root','source_root','membership_file','request','run_dir','output'))
    need(not out.exists() and not out.is_relative_to(run) and sha(request)==a.expected_request_sha256,'fresh QA/frozen target request')
    req=read(request);need(req['candidate']==PRIMARY and req['ranking_permitted'] is True
        and req['portfolio_returns_permitted'] is False and req['network_permitted'] is False and req['investment_rule_changed'] is False,
        'same policy,no account scorer')
    expected={**req['input_sha256'],'frozen_request':a.expected_request_sha256};paths={'frozen_request':request}
    for key in req['input_sha256']:
        if key=='membership':paths[key]=membership;continue
        prefix,name=key.split('/',1);need(prefix in ('repo','source') and not Path(name).is_absolute() and '..' not in Path(name).parts,'safe source namespace')
        paths[key]=(repo if prefix=='repo' else base)/name
    for key,f in paths.items():need(sha(f)==expected[key],'input before '+key)
    codehash=sha(Path(__file__));outputs=inventory(run)
    oldtext=(repo/'src/stock_rsi/asset_expansion_monthly.py').read_text();newtext=(repo/'src/stock_rsi/asset_expansion_horizon.py').read_text()
    wanted=oldtext.replace('"""One low-asset-expansion hypothesis using same-edition dated balance cells."""',
        '"""The unchanged expansion policy, with a bounded2026 formation window."""',1).replace(
        "START,END='2024-01-02','2025-12-31'","START,END='2024-01-02','2026-10-21'",1).replace(
        "'asset-expansion development ends in2025'","'asset-expansion horizon ends at fixed2026 source cutoff'",1)
    need(newtext==wanted,'separate literal proof: only declared window/description edits')
    olddays=(base/OLD_PROVIDER/'calendars/day.txt').read_text().splitlines();days=(base/PROVIDER/'calendars/day.txt').read_text().splitlines()
    need(olddays==days[:len(olddays)] and olddays[-1]=='2025-12-31' and days[-1]=='2026-10-13','unchanged historical calendar and actual horizon')
    prefixes={}
    for code in req['cohort']:
        for field in ('close','volume','factor'):
            relative='features/'+code.lower()+'/'+field+'.day.bin';old=base/OLD_PROVIDER/relative
            raw=old.read_bytes()
            with (base/PROVIDER/relative).open('rb') as f:prefix=f.read(len(raw))
            need(prefix==raw,'separate pre2026 byte-prefix check');prefixes[code+'/'+field]=sha(old)
    proof={'old_calendar_end':olddays[-1],'new_calendar_last_session':days[-1],'old_calendar_sessions':len(olddays),
        'feature_prefix_count':1182,'all_pre2026_byte_prefixes_equal':True,'no2026_float_values_decoded_in_prefix_check':True,
        'feature_prefix_sha256':prefixes}
    need(len(prefixes)==1182 and read(run/'pre2026-prefix-evidence.json')==proof,'all1182 independently reconstructed prefix receipts')
    expected_clocks=[{'execution_session':b,'as_of':a+'T15:05:00+08:00'} for a,b in zip(days,days[1:])
        if '2024-01-02'<=b<='2026-10-21' and a[:7]!=b[:7]]
    need(req['formations']==expected_clocks and len(expected_clocks)==34,'all34 actual monthly transitions')
    cohort=sorted({c for c,first,last in (s.split() for s in membership.read_text().splitlines())
        if first<='2024-01-02'<=last and c.startswith(('SH60','SZ00'))})
    need(cohort==req['cohort'] and len(cohort)==394,'same complete dated cohort')
    memberships=defaultdict(list)
    for line in membership.read_text().splitlines():
        c,first,last=line.split();memberships[c].append((first,last))
    cases=read(base/'annual-total-assets-all1236-v1-20261022/case_results.json');new=read(base/'asset-expansion-2026-assets-20261023/case_results.json')
    need(not set(cases)&set(new),'disjoint original asset cases');cases.update(new)
    targets,receipts=read(run/'targets.json'),read(run/'formation_receipts.json')
    need(set(targets)==set(NAMES) and len(receipts)==34 and all(list(targets[n])==[q['execution_session'] for q in expected_clocks] for n in NAMES),
        'all34 targets for all fixed families')
    names={'formations/'+q['execution_session']+'.json' for q in expected_clocks}|{
        'input-before.json','pre2026-prefix-evidence.json','targets.json','formation_receipts.json','input-postcheck.json','terminal.json','summary.json'}
    need(set(outputs)==names and len(outputs)==41 and read(run/'input-before.json')==expected,'complete41 immutable target artifacts')
    legacy_targets=read(base/OLD_RUN/'targets.json');legacy_receipts=read(base/OLD_RUN/'formation_receipts.json')
    need(receipts[:24]==legacy_receipts and all({d:t for d,t in targets[n].items() if d<'2026-01-01'}==legacy_targets[n] for n in NAMES),
        'all24 original target and full receipt parity')
    quotes=NativeQuotes(base/PROVIDER);details=[];last_args=None
    for q,r in zip(expected_clocks,receipts):
        d,previous=q['execution_session'],q['as_of'][:10];view=read(base/VIEWS/(d+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
        t={n:targets[n][d] for n in NAMES};args=(view,cases,cohort,memberships,quotes,d,previous)
        check_formation(t,r,*args);need(read(run/'formations'/(d+'.json'))=={'targets':t,'receipt':r},'exact completed-formation artifact')
        details.append({'execution_session':d,'eligible':r['eligible'],'primary_names':len(t[PRIMARY]['weights'])});last_args=(t,r,args)
    negatives=negative_controls(*last_args)
    post,terminal,summary=(read(run/n) for n in ('input-postcheck.json','terminal.json','summary.json'))
    need(post=={'all_inputs_unchanged':True,'count':len(paths),'mismatches':[]} and terminal['postcheck']==post
        and terminal['completed_formations']==[q['execution_session'] for q in expected_clocks] and not terminal['pending_formations']
        and terminal['pre2026_target_parity_formations']==24 and terminal['original_error'] is None and not terminal['persistence_errors'],
        'complete successful target termination')
    union=sorted({c for t in targets[PRIMARY].values() for c in t['weights']})
    future_union=sorted({c for d,t in targets[PRIMARY].items() if d>='2026-01-01' for c in t['weights']})
    need(summary['request_sha256']==a.expected_request_sha256 and summary['candidate']==PRIMARY and summary['completed_formations']==34
        and summary['pre2026_target_parity_formations']==24 and summary['primary_target_union']==union
        and summary['primary_2026_target_union']==future_union and summary['2026_formation_counts']==details[24:]
        and summary['targets_sha256']==sha(run/'targets.json') and summary['formation_receipts_sha256']==sha(run/'formation_receipts.json'),
        'independent complete target summary and dependency unions')
    for flag in ('investment_rule_changed','portfolio_returns_computed','historical_arrival_verified',
        'investment_factor_admitted','sealed_2026_evidence','objective_achieved'):need(summary[flag] is False,'strict target evidence limit '+flag)
    for key,f in paths.items():need(sha(f)==expected[key],'input after '+key)
    need(inventory(run)==outputs and sha(Path(__file__))==codehash,'all targets and separate checker unchanged')
    result={'status':'SEPARATE_ALL34_ASSET_EXPANSION_RANKS_AND_24_LEGACY_TARGETS_PASSED_NOT_ACCOUNT_ADMISSION',
        'audit_code_sha256':codehash,'request_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),
        'formations_checked':34,'cohort_formation_rows_checked':34*394,'pre2026_full_target_receipt_parity':24,
        'rational_expansions_checked':sum(d['eligible'] for d in details),'native_unique_scalar_quotes_read':len(quotes.cache),
        'native_latest_scalar_day':max(k[2] for k in quotes.cache),'primary_union_count':len(union),'primary_2026_union_count':len(future_union),
        'all1182_pre2026_feature_prefixes_equal':True,'policy_code_changed_only_at_declared_window':True,
        'all_consumed_input_sha256':expected,'all_output_sha256':outputs,'all_consumed_inputs_and_outputs_unchanged':True,
        'semantic_negative_controls_rejected_without_artifact_hash_gate':negatives,'formation_details':details,
        'no_production_imports':True,'same_researcher_after_target_run':True,'portfolio_returns_computed':False,
        'investment_factor_admitted':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print(result['status'],'formations34; nativequotes',len(quotes.cache),'semantic negatives',len(negatives))


if __name__=='__main__':main()
