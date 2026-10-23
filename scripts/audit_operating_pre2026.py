"""Separate approved-source ranks and native intent/account checks; no new producer imports."""
import argparse
from collections import Counter,defaultdict
from datetime import date,datetime,time,timezone
from decimal import Decimal,localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

PRIMARY='operating_profit_prior_assets_top_decile_conditional'
LOW='operating_profit_prior_assets_bottom_decile_control'
NAMES=(PRIMARY,'eligible_equal_weight',LOW)
OUTPUT='operating-profitability-conditional-development-v1-20261023'
SOURCE='operating-asset-recovery-source-v1-20261023'
LEGACY='operating-corpus-source-v1-20261023'
PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
SOURCE_REQUEST='experiments/qlib/operating-asset-recovery-source-request.json'
SOURCE_SHA='d7faf59fab2f90d6dc477f54b3b3ecb7a5c8487dcd0328378e3ed823efa024b2'
PROOF='experiments/qlib/operating-asset-recovery-independent-check.json'
PROOF_SHA='7551c4d43dece6b1eb983e107a27c52658f9443350cbd65a2bfbb7c944e589fa'
COVERAGE='experiments/qlib/operating-asset-recovery-source-coverage.json'
COVERAGE_SHA='b8931b04b8d6d84897f51e8cd31d01c5bcb353390032f96dd438e3432c1c4bff'
ENGINE_REQUEST='experiments/qlib/gross-profitability-pre2026-request.json'
ENGINE_SHA='b8dded6ac3fbeeda528b43004cf9eb513171f61dd6d93b11fe738109e19da5b5'
NATIVE='experiments/qlib/audit_sources/2026-10-22-gross-profitability-development-audit.py'
NATIVE_SHA='cfa7f994915eb5c1b8ab51e43ab1ede92aab1d99c615ac962938adc609d5b33f'
FIELDS=('revenue','cost_of_sales','selling_expenses','administrative_expenses','research_expenses')
LABELS=('营业收入','营业成本','销售费用','管理费用','研发费用')


def need(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def inventory(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def compact(v):return re.sub(r'\s+','',v)
def near(a,b,why):need(math.isfinite(float(a)) and math.isfinite(float(b)) and math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-6),why)
def aware(v):
    d=datetime.fromisoformat(v);need(d.utcoffset() is not None,'aware source time');return d
def public(doc):return datetime.combine(date.fromisoformat(doc['day']),time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
def false_flags(v):
    for key in ('historical_arrival_verified','financial_cross_issuer_comparability_verified','investment_factor_admitted','raw_share_execution_verified','2026_financial_or_market_values_read','sealed_evidence','objective_achieved'):
        if key in v:need(v[key] is False,'unsupported assurance remains false')
def cny(cell):
    unit=cell['unit'];need(unit in ('元','万元'),'supported original monetary unit');scale=1 if unit=='元' else 10000
    value=Fraction(cell['literal'].replace(',',''))*scale;need(value==Fraction(cell['value_CNY']),'independent literal/unit amount')
    if 'unit_evidence_literal' in cell:
        m=re.search(r'(?:单位[:：](?:人民币)?|金额单位(?:[:：]|(?:均)?为)人民币)(元|万元)',compact(cell['unit_evidence_literal']));need(m is not None and m.group(1)==unit,'source declaration agrees with normalized unit')
    return value

def text(value):
    with localcontext() as ctx:ctx.prec=60;return format(Decimal(value.numerator)/Decimal(value.denominator),'.2f')


def source_score(document,case,legacy_record,approved_id,as_of):
    clock=aware(as_of);pub=public(document);observed=aware(document['captured_at_utc']);year=document['effective_fiscal_year']
    need(pub<=clock and pub<=observed,'independently visible coherent source clocks');false_flags(case)
    need(case['capture_key']==document['capture_key'] and case['instrument']==document['instrument'] and case['fiscal_year']==year
        and case['source_sha256']==document['source_sha256'] and case['effective_record_id']==approved_id and type(approved_id) is str,'approved selected original case')
    current,prior=f'{year}-12-31',f'{year-1}-12-31'
    if case['effective_source_status']=='UNCHANGED_LEGACY_OPERATING_SOURCE_SUPPORTED':
        need(case['source_record'] is None and case['asset_bridge'] is None,'unchanged legacy path only');record=legacy_record;payload=record['payload']
        need(record['contract']=='CN_OP_EX_RND_SAME_EDITION_LAGGED_ASSETS_V1' and payload['scope']=='CONSOLIDATED','legacy consolidated contract')
        income=payload['parsed']['income'];balances=payload['parsed']['balances'];need(set(balances)=={current,prior},'two legacy annual asset columns')
        for column,p in enumerate((current,prior)):
            cell=balances[p];need(cell['fiscal_end']==p and cell['column_index']==column and cell['statement']=='合并资产负债表'
                and cell['reported_comparative_balance_date']==prior and compact(cell['header_line']).endswith(f'{year}年12月31日{year-1}年12月31日'),
                'explicit same-edition previous December31 assets');cny(cell)
        denominator=cny(balances[prior]);asset_id=None
    else:
        need(case['effective_source_status']=='SUMMARY_SOURCE_RECOVERED_NOT_INVESTMENT_ADMITTED','supported current operating record')
        record=case['source_record'];payload=record['payload'];asset=payload['asset_bridge']
        need(record['contract']=='CN_OPERATING_INCOME_AND_SUMMARY_PRIOR_ASSETS_SOURCE_V1' and type(asset) is dict and asset==case['asset_bridge']
            and asset['record_id']==digest({k:v for k,v in asset.items() if k!='record_id'})
            and asset['contract']=='CN_ANNUAL_SUMMARY_PRIOR_YEAR_END_ASSET_WORDS_V1','nonnull coherent asset witness');false_flags(asset)
        need(payload['income_origin']=='CONSOLIDATED_INCOME_STATEMENT' and payload['asset_origin']=='MAIN_ACCOUNTING_DATA_SUMMARY_YEAR_END'
            and asset['source_sha256']==document['source_sha256'] and asset['report_year']==year and asset['publication_day']==document['day']
            and asset['normative_basis']['body_sha256']=='b727419bdab8b137224cea1c9c8b7d20e8a8f1e3714c6ef2e3a6242cd4767615'
            and '2021-06-28'<=document['day']<'2025-07-01' and asset['same_edition_primary_reconciliation'] is True,'original table origins and applicable normative source')
        groups=asset['columns_by_year'];a,p=asset['current'],asset['prior']
        need(len(groups[str(year)])==1 and a==groups[str(year)][0] and p==groups[str(year-1)][-1]
            and a['fiscal_end']==current and p['fiscal_end']==prior
            and p['adjustment']==('AFTER_ADJUSTMENT' if len(groups[str(year-1)])==2 else 'AS_REPORTED'),'correct labelled prior-year adjustment selection')
        unit=re.fullmatch(r'总资产[（(](元|万元)[）)]',compact(asset['row_label_word']['text']));need(unit is not None and a['unit']==p['unit']==unit.group(1),'original summary row unit')
        control=asset['primary'];cell=control['cell'];tokens=re.findall(r'-?[0-9][0-9,]*\.[0-9]{2}',cell['row_text'])
        need(control['source_sha256']==document['source_sha256'] and control['report_year']==year and len(tokens)==2
            and cell['fiscal_end']==current and cell['statement']=='合并资产负债表' and cell['column_index']==0
            and cell['row_text_sha256']==digest(cell['row_text']) and cny(a)==cny(cell)
            and cny(p)==Fraction(tokens[1].replace(',',''))*(1 if cell['unit']=='元' else 10000),'same-PDF original primary asset reconciliation')
        denominator=cny(p);asset_id=asset['record_id'];income=payload['income']
    false_flags(record)
    need(record['record_id']==approved_id==digest({k:v for k,v in record.items() if k!='record_id'}) and record['instrument']==document['instrument']
        and record['report_year']==year and record['publication_day']==document['day'] and aware(record['public_day_end_at'])==pub
        and aware(record['observed_at'])==observed and payload['document_sha256']==document['source_sha256']
        and payload['announcement_id']==document['announcement_id'],'exact approved report identity/body/clocks')
    need(set(income)=={current,prior} and denominator>0,'both original income periods and positive prior assets')
    for period,fields in income.items():
        need(set(fields)==set(FIELDS),'all five explicit income fields')
        for field,label in zip(FIELDS,LABELS):
            cell=fields[field];column=year-int(period[:4]);tokens=re.findall(r'-?[0-9][0-9,]*\.[0-9]{2}',cell['row_text'])
            need(cell['statement']=='合并利润表' and cell['fiscal_end']==period and cell['column_index']==column and len(tokens)==2
                and cell['literal']==tokens[column] and cell['row_text_sha256']==digest(cell['row_text'])
                and re.match(r'^(?:其中[:：])?'+label,compact(cell['row_text']))
                and compact(cell['header_line']).endswith(f'{year}年度{year-1}年度'),'original scoped income fiscal column/row/literal');cny(cell)
    values={f:cny(income[current][f]) for f in FIELDS};numerator=values['revenue']-values['cost_of_sales']-values['selling_expenses']-values['administrative_expenses']
    return {'instrument':document['instrument'],'capture_key':document['capture_key'],'record_id':record['record_id'],'source_sha256':document['source_sha256'],
        'asset_record_id':asset_id,'current_fiscal_end':current,'prior_asset_fiscal_end':prior,'publication_day':document['day'],
        'score_fraction':str(numerator/denominator),'operating_profit_CNY':text(numerator),'lagged_assets_CNY':text(denominator),
        'research_expenses_CNY':text(values['research_expenses']),'visibility_mode':'RECONSTRUCTED_PUBLICATION_DAY_END','historical_arrival_verified':False,'investment_factor_admitted':False}


def audit_intents(targets,intents,days,holdings,orders,quotes):
    need(len(intents)==len(targets) and len({i['execution_session'] for i in intents})==len(targets),'all unique monthly intentions')
    ledger={r['session']:r for r in days};positions=defaultdict(dict);planned={}
    for r in holdings:
        need(r['instrument'] not in positions[r['session']],'unique prior held source');positions[r['session']][r['instrument']]=float(r['normalized_units'])
    for intent in intents:
        day=intent['execution_session'];target=targets[day];previous=target['as_of'];held=positions.get(previous,{})
        equity=1000000. if previous<'2024-01-02' else float(ledger[previous]['account_value'])
        near(intent['equity_at_decision'],equity,'intent uses exact prior account equity')
        need(intent['target_weights']==target['weights'] and set(intent['holdings_at_decision'])==set(held),'frozen target and prior inventory identity')
        for c,q in held.items():near(intent['holdings_at_decision'][c],q,'prior-close actual held amount')
        need(aware(intent['as_of_close_convention'])==datetime.combine(date.fromisoformat(previous),time(15,5),ZoneInfo('Asia/Shanghai'))
            and intent['latest_decision_price_read']==previous and intent['execution_exchange_queried_for_decision'] is False,'no execution-day decision input')
        expected=[]
        for code in sorted(set(held)|set(target['weights'])):
            quantity=held.get(code,0.);weight=target['weights'].get(code,0.)
            if quantity>0 and weight==0:
                expected.append({'instrument':code,'side':'SELL','normalized_units':quantity,'known_normalized_close':None,'known_factor':None,'as_of':previous,'quantity_basis':'KNOWN_INVENTORY_FULL_EXIT'});continue
            price=quotes.value(code,'close',previous,as_of=previous);factor=quotes.value(code,'factor',previous,as_of=previous)
            need(price is not None and factor is not None and price>0 and factor>0,'visible decision close/factor')
            desired=math.floor(equity*weight/price*factor/100+1e-10)*100/factor;difference=desired-quantity
            if difference>1e-8*max(1.,quantity,desired):amount=math.floor(difference*factor/100+1e-10)*100/factor;side='BUY'
            elif difference< -1e-8*max(1.,quantity,desired):amount=quantity-desired;side='SELL'
            else:continue
            if amount>0:expected.append({'instrument':code,'side':side,'normalized_units':amount,'known_normalized_close':price,'known_factor':factor,'as_of':previous,'quantity_basis':'PRIOR_CLOSE_TARGET'})
        expected.sort(key=lambda r:(r['side']!='SELL',r['instrument']));need(len(expected)==len(intent['orders']),'all intended prior-close orders')
        for actual,want in zip(intent['orders'],expected):
            need(set(actual)==set(want),'complete intended order fields')
            for k,v in want.items():
                if type(v) in (int,float):near(actual[k],v,'independent intention '+k)
                else:need(actual[k]==v,'independent intention '+k)
            planned[(day,want['instrument'],want['side'])]=want['normalized_units']
    represented=set()
    for order in orders:
        key=(order['session'],order['instrument'],order['side']);need(key in planned and key not in represented,'indicator order belongs to unique frozen intention');represented.add(key)
        near(float(order['requested_normalized_units']),planned[key]*(1 if key[2]=='BUY' else -1),'submitted amount equals intended prior-close amount')
    return {'intents_checked':len(intents),'intended_orders_checked':len(planned),'indicator_orders_linked':len(represented),
            'intentions_without_indicator_row':len(set(planned)-represented)}


def audit_formations(base,req,out,quotes):
    cohort=req['cohort'];documents=req['documents'];by_key={d['capture_key']:d for d in documents};members=defaultdict(list)
    for line in (base/PROVIDER/'instruments/csi500.txt').read_text().splitlines():
        c,a,b=line.split();members[c].append((a,b))
    receipts=read(out/'formation_receipts.json');targets=read(out/'targets.json');need(len(receipts)==len(req['formations'])==24 and set(targets)==set(NAMES),'24formations and only registered families')
    checked=0;formation_rows=[]
    for q,receipt in zip(req['formations'],receipts):
        execution=q['execution_session'];previous=q['as_of'][:10];clock=aware(q['as_of']);view=read(base/SOURCE/(execution+'-RECONSTRUCTED_PUBLICATION_DAY_END.json'))
        need(aware(view['as_of'])==clock and view['visibility_mode']=='RECONSTRUCTED_PUBLICATION_DAY_END' and [r['instrument'] for r in view['classifications']]==cohort,'complete original conditional view')
        active={c for c in cohort if any(a<=previous<=b for a,b in members[c])};minimum=int(previous[:4])-(2 if previous[5:7]<='06' else 1)
        visible=defaultdict(list)
        for d in documents:
            if public(d)<=clock:visible[d['instrument']].append(d)
        scores={};evidence={};admission=[]
        for row in view['classifications']:
            code=row['instrument'];reason=None;candidates=visible[code]
            if candidates:
                latest=max((d['effective_fiscal_year'],d['day']) for d in candidates)
                editions=sorted((d for d in candidates if (d['effective_fiscal_year'],d['day'])==latest),key=lambda d:(int(d['announcement_id']),d['capture_key']))
                if len({d['source_sha256'] for d in editions})>1:need(row['annual_status']=='AMBIGUOUS_LATEST_SAME_DAY_EDITIONS' and 'selected_capture_key' not in row,'same-day ambiguity blocks old values')
                else:need(row.get('selected_capture_key')==editions[0]['capture_key'],'independent latest filing precedes support checks')
            else:need(row['annual_status']=='NO_VISIBLE_ANNUAL_REPORT' and 'selected_capture_key' not in row,'no future filing selection')
            if code not in active:reason='NOT_IN_FORMATION_MEMBERSHIP'
            elif row['industry_status']!='NONFINANCIAL_IN_SOURCE_VINTAGE':reason='NOT_NONFINANCIAL_IN_2021_SOURCE'
            elif 'selected_capture_key' not in row:reason=row['annual_status']
            elif row['latest_fiscal_year']<minimum:reason='STALE_ANNUAL_SOURCE'
            elif row['effective_source_status']=='STILL_UNSUPPORTED':reason='LATEST_STILL_UNSUPPORTED'
            if reason is None:
                key=row['selected_capture_key'];doc=by_key[key];case=read(base/SOURCE/(key+'.json'))
                old=read(base/LEGACY/(key+'.json'))['operating_report'] if case['effective_source_status']=='UNCHANGED_LEGACY_OPERATING_SOURCE_SUPPORTED' else None
                need(case['effective_source_status']==row['effective_source_status'] and case['effective_record_id']==row['effective_record_id']
                    and doc['source_sha256']==row['selected_source_sha256'] and doc['effective_fiscal_year']==row['latest_fiscal_year'],'same metadata source pointer')
                observation=source_score(doc,case,old,req['approved_record_ids'][key],clock.isoformat())
                values=[quotes.value(code,f,previous,as_of=previous) for f in ('close','volume','factor')]
                if any(v is None or v<=0 for v in values):reason='NO_POSITIVE_FORMATION_QUOTE'
                else:scores[code]=Fraction(observation['score_fraction']);evidence[code]=observation;reason='CONDITIONALLY_RANKABLE_NOT_INVESTMENT_ADMITTED';checked+=1
            admission.append({'instrument':code,'reason':reason})
        need(len(scores)>=100,'independent minimum100 source/price names')
        n=len(scores)//10;selected={PRIMARY:sorted(scores,key=lambda c:(-scores[c],c))[:n],'eligible_equal_weight':sorted(scores),LOW:sorted(scores,key=lambda c:(scores[c],c))[:n]}
        need(receipt['cohort_admission']==admission and receipt['ranked_source']==evidence and receipt['selections']==selected
            and receipt['eligible']==len(scores) and receipt['formation_members']==len(active) and receipt['minimum_fiscal_year']==minimum
            and receipt['latest_factor_price_read']==previous and receipt['admission_counts']==dict(Counter(r['reason'] for r in admission)),'independent complete source/rank receipt')
        for name,names in selected.items():
            t=targets[name][execution];need(t['as_of']==previous and list(t['weights'])==names,'only independently selected prior-close target names')
            for w in t['weights'].values():near(w,.95/len(names),'95percent equal target weights')
        need(read(out/'formations'/(execution+'.json'))=={'targets':{n:targets[n][execution] for n in NAMES},'receipt':receipt},'complete formation prefix artifact')
        false_flags(receipt);formation_rows.append({'execution_session':execution,'eligible':len(scores),'primary_names':selected[PRIMARY],'admission_counts':dict(Counter(r['reason'] for r in admission))})
    return {'formation_count':24,'cohort_formation_rows_checked':len(cohort)*24,'exact_source_ratios_checked':checked,'formations':formation_rows}


def audit(base,root,membership,request,expected_sha):
    need(sha(request)==expected_sha and sha(root/NATIVE)==NATIVE_SHA,'frozen request and independently implemented native checker')
    spec=importlib.util.spec_from_file_location('original_native_gp_audit',root/NATIVE);native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    req=read(request);need(req['status']=='FROZEN_BEFORE_ONE_OPERATING_PROFITABILITY_DEVELOPMENT_SCREEN' and req['output_subdir']==OUTPUT
        and req['candidate']==PRIMARY and req['controls']==['eligible_equal_weight',LOW] and req['candidate_budget']==req['operating_family_trial']==1
        and req['account_window']==['2024-01-02','2025-12-31'] and req['capital_CNY']==1000000 and req['extra_bps']==[20,40]
        and req['target_exposure']==.95 and req['minimum_eligible']==100 and req['minimum_active_cohort_fraction'] is None
        and req['network_permitted'] is False and req['2026_financial_or_market_values_permitted'] is False,'independent one-candidate development scope')
    need(sha(root/SOURCE_REQUEST)==SOURCE_SHA and sha(root/PROOF)==PROOF_SHA and sha(root/COVERAGE)==COVERAGE_SHA
        and sha(root/ENGINE_REQUEST)==ENGINE_SHA,'fixed original source and account authorities')
    old,source,proof,coverage=read(root/ENGINE_REQUEST),read(root/SOURCE_REQUEST),read(root/PROOF),read(root/COVERAGE)
    need(req['documents']==source['documents'] and req['cohort']==source['cohort']==old['cohort'] and req['formations']==source['formations']==old['formations']
        and req['approved_record_ids']=={c['capture_key']:c['effective_record_id'] for c in coverage['case_rows']},'complete original corpus/cohort/formations/approved IDs')
    expected_methods=set(old['method_sha256'])|{'src/stock_rsi/annual_operating.py','src/stock_rsi/operating_source_bridge.py',
        'src/stock_rsi/asset_geometry.py','src/stock_rsi/operating_factor.py','src/stock_rsi/operating_monthly.py',
        'scripts/run_qlib_operating_pre2026.py','scripts/audit_operating_pre2026.py',NATIVE}
    need(set(req['method_sha256'])==expected_methods and all(req['input_sha256'].get('repo/'+p)==h for p,h in req['method_sha256'].items()),'independent complete new method bindings')
    for parent in (old,source):
        for k,h in parent['input_sha256'].items():need(req['input_sha256'].get(k)==h,'all original input closure retained')
    for k,h in proof['all_output_sha256'].items():need(req['input_sha256'].get('source/'+SOURCE+'/'+k)==h,'all independently proved source outputs bound')
    need(inventory(base/SOURCE)==proof['all_output_sha256'],'source recovery inventory unchanged')
    paths=native.input_paths(req,root,base,membership,request);expected={**req['input_sha256'],'frozen_request':expected_sha}
    for k,p in paths.items():need(sha(p)==expected[k],'audit input before '+k)
    out=base/OUTPUT;before=inventory(out);summary=read(out/'summary.json');terminal=read(out/'terminal.json')
    wanted={'input-before.json','targets.json','formation_receipts.json','case_results.json','input-postcheck.json','terminal.json','summary.json'}
    wanted|={'formations/'+q['execution_session']+'.json' for q in req['formations']}
    for extra in (20,40):
        for name in NAMES:
            wanted|={str(extra)+'/'+name+'/'+f for f in ('metrics.json','report.pkl','positions.pkl','days.csv','orders.csv','holdings.csv','decision_intents.json','suspension_mark_audit.json')}
    need(set(before)==wanted and len(before)==79 and read(out/'input-before.json')==expected and terminal['completed'] is True
        and not terminal['pending_profiles'] and terminal['original_error'] is None and terminal['postcheck']['all_inputs_unchanged'] is True
        and not terminal['persistence_errors'],'complete unchanged six-profile experiment')
    quotes=native.QuoteReader(base/PROVIDER);formations=audit_formations(base,req,out,quotes);targets=read(out/'targets.json')
    states={}
    for p in (base/native.GAPS/'codes').glob('*.json'):
        packet=read(p);states[packet['instrument']]={r['date']:r for r in packet['rows']}
    accounts={};intent_checks={};need(read(out/'case_results.json')==summary['results_by_extra_bps_and_family'],'complete individual/aggregate metrics')
    for extra in (20,40):
        for name in NAMES:
            label=str(extra)+'/'+name;folder=out/label;metrics=read(folder/'metrics.json')
            need(metrics==summary['results_by_extra_bps_and_family'][label] and metrics['artifact_sha256']=={k:h for k,h in inventory(folder).items() if k!='metrics.json'},'exact original engine artifacts/metrics')
            accounts[label]=native.audit_account(folder,quotes,extra,metrics,states)
            intent_checks[label]=audit_intents(targets[name],read(folder/'decision_intents.json'),native.rows(folder/'days.csv'),native.rows(folder/'holdings.csv'),native.rows(folder/'orders.csv'),quotes)
    p=accounts['40/'+PRIMARY];lead=PRIMARY if min(p['2024_return_pct'],p['2025_return_pct'])>0 and p['average_exposure_pct']>=90 and p['unverified_held_marks']==0 else None
    need(summary['selected_development_lead']==lead and summary['targets_sha256']==sha(out/'targets.json')
        and summary['formation_receipts_sha256']==sha(out/'formation_receipts.json'),'fixed primary-only development gate/artifact pointers');false_flags(summary)
    for k,p in paths.items():need(sha(p)==expected[k],'audit input after '+k)
    need(before==inventory(out),'all outputs unchanged through independent audit')
    return {'status':'PASS_SEPARATE_OPERATING_SOURCE_RANKS_INTENTS_AND_SIX_NATIVE_ACCOUNTS_NOT_RAW_CONFIRMATION',
        'request_sha256':expected_sha,'audit_code_sha256':sha(Path(__file__)),'all_input_sha256':expected,'all_output_sha256':before,
        'formation_audit':formations,'account_audits':accounts,'intent_audits':intent_checks,'native_unique_scalar_quotes_read':len(quotes.cache),
        'all_inputs_outputs_unchanged':True,'no_new_producer_imports':True,'shared_source_and_researcher_provenance':True,
        'historical_arrival_verified':False,'raw_share_execution_verified':False,'investment_factor_admitted':False,
        '2026_financial_or_market_values_read':False,'sealed_evidence':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','membership-file','request','expected-request-sha256','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();target=Path(a.output);need(not target.exists(),'fresh independent operating proof')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.membership_file).resolve(),Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with target.open('x') as f:json.dump({'status':'FAILED_OPERATING_DEVELOPMENT_INDEPENDENT_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,ensure_ascii=False,indent=2)
        raise
    with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],result['formation_audit']['exact_source_ratios_checked'],flush=True)


if __name__=='__main__':main()
