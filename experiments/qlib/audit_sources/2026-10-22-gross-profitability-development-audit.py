"""Separate GP ranks/native scalar quotes/cash-flow QA; no production imports.
Same researcher after outcomes. Not a raw-share or original annual-PDF audit.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import struct


PRIMARY='gp_assets_top_decile_conditional'
LOW='gp_assets_bottom_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',LOW)
SOURCE='gross-profitability-monthly-availability-v1-20261022'
PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
GAPS='low-risk-gap-states-pre2026-20261017'


def need(ok, why):
    if not ok: raise ValueError(why)


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def inventory(folder):
    return {str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
def near(a,b,why):
    need(math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-5),why)
def rows(path):
    with path.open() as handle:return list(csv.DictReader(handle))


def order_fill_quantities(order,factor):
    # Qlib0.9.8 report.py stores signed amount_delta/deal_amount_delta.
    # exchange.py uses floor((amount*factor+0.1)/100)*100/factor.
    # This is a documented engine tolerance,not a raw-share execution claim.
    requested=float(order['requested_normalized_units']);signed=float(order['filled_normalized_units'])
    need(all(math.isfinite(v) for v in (requested,signed,factor)) and factor>0
         and order['side'] in ('BUY','SELL'),'finite signed indicator quantities/factor')
    sign=1 if order['side']=='BUY' else -1
    need(requested*sign>=0 and signed*sign>=0,'indicator quantity/direction sign')
    raw_requested,raw_filled=abs(requested)*factor,abs(signed)*factor
    excess=raw_filled-raw_requested
    if excess>1e-7:
        rounded=(raw_requested+.1)//100*100
        need(excess<=.1+1e-7 and math.isclose(raw_filled,rounded,rel_tol=0,abs_tol=1e-7),
             'overfill must equal exact installed engine rounding rule')
    full_sell=order['side']=='SELL' and math.isclose(signed,requested,rel_tol=1e-10,abs_tol=1e-8)
    if raw_filled>1e-7 and not full_sell:
        need(math.isclose(raw_filled/100,round(raw_filled/100),rel_tol=0,abs_tol=1e-8),
             'rounded execution must use a100-source-unit lot')
    return {'signed_units':signed,'absolute_units':abs(signed),
        'rounded_above_requested':excess>1e-7,'raw_unit_excess':max(0.,excess)}


class QuoteReader:
    def __init__(self,root):
        self.root=root;self.calendar=(root/'calendars/day.txt').read_text().splitlines()
        need(self.calendar==sorted(set(self.calendar)) and self.calendar[-1]=='2025-12-31','native quote calendar capped at2025')
        self.index={d:i for i,d in enumerate(self.calendar)};self.cache={}

    def value(self,code,field,day,*,as_of='2025-12-31'):
        need(day<=as_of<='2025-12-31' and day in self.index,'native scalar asof boundary')
        need(re.fullmatch(r'(?:SH|SZ)[0-9]{6}',code) and field in ('open','close','volume','factor'),'native scalar identity/field')
        key=(code,field,day)
        if key in self.cache:return self.cache[key]
        path=self.root/'features'/code.lower()/(field+'.day.bin')
        size=path.stat().st_size
        need(size>=8 and size%4==0,'native feature extent')
        with path.open('rb') as stream:
            first=struct.unpack('<f',stream.read(4))[0]
            need(math.isfinite(first) and first==int(first),'native integer offset')
            start,count=int(first),size//4-1
            need(start>=0 and start+count<=len(self.calendar),'native feature has no future tail')
            offset=self.index[day]-start
            if not 0<=offset<count:value=None
            else:
                stream.seek(4+offset*4);value=struct.unpack('<f',stream.read(4))[0]
                if not math.isfinite(value):value=None
        self.cache[key]=value;return value


def input_paths(req,root,base,membership,request):
    old=base/'cninfo-csi500-reports-20261017'
    fixed=base/'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
    originals={d['capture_key']:d for d in read(fixed)}
    aliases={'membership_intervals':membership,'metadata_manifest':old/'manifest.json','metadata_plan':old/'plan.json',
        'PDF_document_records':fixed,'inventory_code':root/'experiments/qlib/audit_sources/2026-10-22-profitability-historical-source-inventory-v2.py'}
    paths={'frozen_request':request}
    for key in req['input_sha256']:
        if key=='membership':path=membership
        else:
            prefix,name=key.split('/',1)
            if prefix=='repo':path=root/name
            elif prefix=='source':path=base/name
            else:
                need(prefix=='catalog','known bound input alias')
                if name in aliases:path=aliases[name]
                elif name.startswith('metadata/'):path=old/'codes'/(name[9:]+'.json')
                else:
                    need(name.startswith('PDF/') and name[4:] in originals,'original PDF alias')
                    path=base/originals[name[4:]]['source_path']
        paths[key]=path
    return paths


def audit_formations(base,req,run,quotes):
    memberships=defaultdict(list)
    for line in (base/PROVIDER/'instruments/csi500.txt').read_text().splitlines():
        code,first,last=line.split();memberships[code].append((first,last))
    targets,receipts=read(run/'targets.json'),read(run/'formation_receipts.json')
    need(len(receipts)==len(req['formations'])==24,'all24 formations')
    cohort=req['cohort'];supported=0;formed=[]
    for formation,receipt in zip(req['formations'],receipts):
        execution,previous=formation['execution_session'],formation['as_of'][:10]
        source=read(base/SOURCE/(execution+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
        need(datetime.fromisoformat(source['as_of'])==datetime.fromisoformat(formation['as_of'])
             and source['visibility_mode']=='RECONSTRUCTED_PUBLICATION_DAY_END','same audited publication reconstruction clock')
        need([r['instrument'] for r in source['classifications']]==cohort,'all dated394 source names')
        active={c for c in cohort if any(a<=previous<=b for a,b in memberships[c])}
        minimum=int(previous[:4])-(2 if previous[5:7]<='06' else 1)
        scores,evidence,admission={},{},[]
        for row in source['classifications']:
            code,reason=row['instrument'],None
            if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif row['annual_status']!='LATEST_CURRENT_SOURCE_SUPPORTED_NOT_ADMITTED':reason=row['annual_status']
            elif row['latest_fiscal_year']<minimum:reason='STALE_ANNUAL_SOURCE'
            if reason is None:
                current=row['current_observation'];o=current['source']
                need(o['instrument']==code and o['record_id']==current['record_id']==digest({k:v for k,v in o.items() if k!='record_id'})
                     and o['payload']['column_role']=='CURRENT' and o['fiscal_end']==f'{row["latest_fiscal_year"]}-12-31'
                     and datetime.fromisoformat(o['public_day_end_at'])<=datetime.fromisoformat(formation['as_of']),
                     'independent coherent visible current record')
                amounts={}
                for field in ('revenue','cost_of_sales','total_assets'):
                    cell=o['payload']['cells'][field];scale={'元':1,'万元':10000}[cell['unit']]
                    amounts[field]=Fraction(cell['literal'].replace(',',''))*scale
                    need(amounts[field]==Fraction(cell['value_CNY']),'exact literal/unit conversion')
                need(amounts['total_assets']>0,'positive original total assets')
                values=[quotes.value(code,f,previous,as_of=previous) for f in ('close','volume','factor')]
                if any(v is None or v<=0 for v in values):reason='NO_POSITIVE_FORMATION_QUOTE'
                else:
                    score=(amounts['revenue']-amounts['cost_of_sales'])/amounts['total_assets']
                    scores[code]=score;reason='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED'
                    evidence[code]={'record_id':current['record_id'],'source_sha256':row['selected_source_sha256'],
                        'fiscal_end':o['fiscal_end'],'publication_day':o['publication_day'],'score_fraction':str(score)}
                    supported+=1
            admission.append({'instrument':code,'reason':reason})
        need(len(scores)>=100 and 2*len(scores)>=len(active),'independent fixed structural coverage')
        n=len(scores)//10
        selected={PRIMARY:sorted(scores,key=lambda c:(-scores[c],c))[:n],
            LOW:sorted(scores,key=lambda c:(scores[c],c))[:n],'eligible_equal_weight':sorted(scores)}
        need(receipt['cohort_admission']==admission and receipt['ranked_source']==evidence
             and receipt['selections']==selected and receipt['eligible']==len(scores)
             and receipt['admission_counts']==dict(Counter(r['reason'] for r in admission))
             and receipt['minimum_fiscal_year']==minimum and receipt['latest_factor_price_read']==previous,
             'complete independent admission/rank/source receipt')
        for name,names in selected.items():
            target=targets[name][execution]
            need(target['as_of']==previous and list(target['weights'])==names,'independent ordered target identities')
            for weight in target['weights'].values():near(weight,.95/len(names),'equal95% target allocation')
        packet=read(run/'formations'/(execution+'.json'))
        need(packet=={'targets':{name:targets[name][execution] for name in NAMES},'receipt':receipt},'persisted formation prefix')
        formed.append({'execution_session':execution,'eligible':len(scores),'primary_names':selected[PRIMARY]})
    return {'formation_count':24,'cohort_formation_rows_checked':len(cohort)*24,
        'exact_eligible_source_ratios_checked':supported,'formations':formed}


def mark_verified(code,day,mark,quotes,states):
    data=states.get(code,{})
    if data.get(day,{}).get('tradestatus')!='0':return False
    for prior in reversed([d for d in quotes.calendar if d<day]):
        close=quotes.value(code,'close',prior)
        if close is None or close<=0:continue
        factor=quotes.value(code,'factor',prior)
        try:raw=float(data.get(prior,{}).get('close',''))
        except (ValueError,TypeError):return False
        return (factor is not None and factor>0 and math.isfinite(raw)
            and math.isclose(close/factor,raw,abs_tol=.005,rel_tol=1e-6)
            and math.isclose(mark,close,abs_tol=1e-8,rel_tol=1e-8))
    return False


def audit_account(folder,quotes,extra,metrics,states):
    import pandas as pd
    days,orders,holdings=rows(folder/'days.csv'),rows(folder/'orders.csv'),rows(folder/'holdings.csv')
    sessions=[d for d in quotes.calendar if '2024-01-02'<=d<='2025-12-31']
    need([r['session'] for r in days]==sessions and len(days)==485,'all485 continuous account sessions')
    report=pd.read_pickle(folder/'report.pkl')
    need([d.strftime('%Y-%m-%d') for d in report.index]==sessions,'original Qlib report calendar')
    by_order,by_hold=defaultdict(list),defaultdict(list)
    for row in orders:by_order[row['session']].append(row)
    for row in holdings:by_hold[row['session']].append(row)
    need(set(by_order)<=set(sessions) and set(by_hold)<=set(sessions),'only pre2026 account records')
    marks=read(folder/'suspension_mark_audit.json');missing={};prior_cash=prior_nav=peak=1000000.
    total_cost=total_turnover=0.;exposure=0.;drawdown=0.;last_year_nav=1000000.;annual={};previous_units={}
    intents=read(folder/'decision_intents.json');rounding_overfills=0;max_raw_excess=0.
    need(len(intents)==24 and len({i['execution_session'] for i in intents})==24,'all24 decision intents')
    for index,day in enumerate(sessions):
        r=days[index];original=report.iloc[index];trade_value=cost=turnover=0.;deltas=defaultdict(float)
        for order in by_order[day]:
            signed=float(order['signed_trade_value']);fee=float(order['cost'])
            factor=quotes.value(order['instrument'],'factor',day)
            quantities=order_fill_quantities(order,factor)
            filled=quantities['absolute_units']
            need(fee>=0,'nonnegative simulation fee')
            rounding_overfills+=quantities['rounded_above_requested']
            max_raw_excess=max(max_raw_excess,quantities['raw_unit_excess'])
            if filled>0:
                price=float(order['normalized_price']);near(abs(signed),filled*price,'normalized fill notional')
                near(price,quotes.value(order['instrument'],'open',day),'native daily-open execution price')
                rate=(.0005 if order['side']=='BUY' else .0015)+extra/10000
                near(fee,max(5.,abs(signed)*rate),'declared per-side daily proxy fee')
            else:near(signed,0,'unfilled notional');near(fee,0,'unfilled cost')
            need((order['side']=='BUY' and signed>=0) or (order['side']=='SELL' and signed<=0),'direction/notional sign')
            deltas[order['instrument']]+=quantities['signed_units']
            trade_value+=signed;cost+=fee;turnover+=abs(signed)
        units={};stock=0.
        for holding in by_hold[day]:
            code=holding['instrument'];amount=float(holding['normalized_units']);price=float(holding['normalized_price'])
            need(code not in units and amount>0 and price>0,'unique positive normalized holding')
            units[code]=amount;value=amount*price;near(value,float(holding['value']),'holding quantity*mark')
            quote=quotes.value(code,'close',day)
            if quote is not None and quote>0:near(price,quote,'native closing holding mark')
            else:missing[(code,day)]=price
            stock+=value
        for code in set(units)|set(previous_units)|set(deltas):
            near(units.get(code,0),previous_units.get(code,0)+deltas.get(code,0),'normalized inventory conservation')
        cash=float(r['cash']);nav=cash+stock
        need(cash>=-.01,'cash never borrowed')
        near(cash,prior_cash-trade_value-cost,'independent daily cash conservation')
        near(stock,float(r['stock_value']),'stock aggregation');near(nav,float(r['account_value']),'cash+stock equity')
        near(nav,float(original['account']),'independent CSV account/original report')
        near(nav/prior_nav-1,float(original['return']-original['cost']),'continuous net return')
        near(cost,float(r['cost']),'daily cost');near(turnover,float(r['turnover']),'daily turnover')
        total_cost+=cost;total_turnover+=turnover
        near(total_cost,float(original['total_cost']),'cumulative cost');near(total_turnover,float(original['total_turnover']),'cumulative turnover')
        exposure+=stock/nav;peak=max(peak,nav);drawdown=min(drawdown,nav/peak-1)
        if index==len(sessions)-1 or sessions[index+1][:4]!=day[:4]:
            annual[day[:4]]=100*(nav/last_year_nav-1);last_year_nav=nav
        previous_units=units;prior_cash=cash;prior_nav=nav
    need(len(marks)==len(missing) and {(r['instrument'],r['session']) for r in marks}==set(missing),'all missing held marks explicit')
    unverified=0
    for r in marks:
        key=(r['instrument'],r['session']);near(r['marked_normalized_price'],missing[key],'marked missing quote')
        verified=mark_verified(*key,missing[key],quotes,states)
        need(r['verified']==verified,'independent suspension source verification')
        unverified+=not verified
    expected={'2024_return_pct':annual['2024'],'2025_return_pct':annual['2025'],
        'net_compound_return_pct':100*(prior_nav/1000000-1),'average_exposure_pct':100*exposure/len(days),
        'max_drawdown_pct':100*drawdown,'cost_pct_initial':100*total_cost/1000000,
        'turnover_x_initial':total_turnover/1000000,'final_account_CNY':prior_nav}
    for key,value in expected.items():near(metrics[key],value,'independent account metric '+key)
    need(metrics['unverified_held_marks']==unverified and metrics['orders']==len(orders),'independent order/mark counts')
    return {**expected,'sessions':len(days),'orders_checked':len(orders),'holding_rows_checked':len(holdings),
        'unverified_held_marks':unverified,'engine_rounding_above_request_orders':rounding_overfills,
        'max_engine_source_unit_excess':max_raw_excess,'order_indicator_quantities_are_signed':True}


def main():
    p=argparse.ArgumentParser()
    for name in ('repo-root','source-root','membership-file','request','expected-request-sha256','run-dir','output'):
        p.add_argument('--'+name,required=True)
    a=p.parse_args();root,base,membership,request,run,output=(Path(getattr(a,k)).resolve() for k in
        ('repo_root','source_root','membership_file','request','run_dir','output'))
    need(not output.exists() and not output.is_relative_to(run),'fresh external GP audit output')
    need(sha(request)==a.expected_request_sha256,'frozen GP request hash')
    req=read(request);paths=input_paths(req,root,base,membership,request)
    expected={**req['input_sha256'],'frozen_request':a.expected_request_sha256}
    for key,path in paths.items():need(sha(path)==expected[key],'input before: '+key)
    outputs=inventory(run);summary=read(run/'summary.json');terminal=read(run/'terminal.json')
    need(len(outputs)==79 and read(run/'input-before.json')==expected,'complete79-file GP run/input manifest')
    need(not terminal['pending_profiles'] and terminal['original_error'] is None and not terminal['persistence_errors']
         and terminal['postcheck']['all_inputs_unchanged'],'complete unchanged successful engineering execution')
    quotes=QuoteReader(base/PROVIDER);formation=audit_formations(base,req,run,quotes)
    states={}
    for path in (base/GAPS/'codes').glob('*.json'):
        packet=read(path);states[packet['instrument']]={r['date']:r for r in packet['rows']}
    accounts={}
    for extra in (20,40):
        for name in NAMES:
            label=str(extra)+'/'+name;metrics=read(run/label/'metrics.json')
            need(metrics==summary['results_by_extra_bps_and_family'][label],'published original metric identity')
            accounts[label]=audit_account(run/label,quotes,extra,metrics,states)
    primary=accounts['40/'+PRIMARY]
    selected=PRIMARY if min(primary['2024_return_pct'],primary['2025_return_pct'])>0 and primary['average_exposure_pct']>=90 and primary['unverified_held_marks']==0 else None
    need(summary['selected_development_lead']==selected,'primary-only fixed40bp development gate')
    for key in ('raw_share_execution_verified','investment_factor_admitted','2026_financial_or_market_values_read','sealed_evidence','objective_achieved'):
        need(summary[key] is False,'economic evidence limit')
    for key,path in paths.items():need(sha(path)==expected[key],'input after: '+key)
    need(inventory(run)==outputs,'all GP output bytes unchanged through audit')
    result={'status':'SEPARATE_NATIVE_RANKS_AND_SIX_DAILY_ACCOUNT_AUDIT_PASSED_NOT_RAW_CONFIRMATION',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':a.expected_request_sha256,
        'input_count':len(paths),'input_binding_digest':digest(expected),'all_output_sha256':outputs,
        'all_inputs_and_outputs_unchanged':True,'formation_audit':formation,'account_audits':accounts,
        'native_unique_scalar_quotes_read':len(quotes.cache),'no_production_imports':True,
        'same_researcher_after_outcomes':True,'complete_annual_PDF_reextraction':False,
        'prior_close_sizing_independently_reimplemented':False,'raw_share_execution_verified':False,
        'selected_development_lead':selected,'objective_achieved':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as handle:json.dump(result,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'status':result['status'],'selected_development_lead':selected,
        'formation_rows_checked':formation['cohort_formation_rows_checked'],'accounts_checked':len(accounts),
        'holding_rows_checked':sum(v['holding_rows_checked'] for v in accounts.values())}))


if __name__=='__main__':main()
