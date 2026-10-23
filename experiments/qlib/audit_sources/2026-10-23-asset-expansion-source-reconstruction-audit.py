"""Separate source-only reconstruction using stdlib/Decimal and native PDF readers."""
import argparse,base64,copy,hashlib,json,re
from datetime import date,datetime,timedelta
from decimal import Decimal
from pathlib import Path

BAR=('date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST')
DIV=('code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate','dividRegistDate',
     'dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax','dividCashPsAfterTax',
     'dividStocksPs','dividCashStock','dividReserveToStockPs')
ADJ=('code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor')
NUM={'bars':('open','high','low','close','preclose','volume','amount'),
     'distributions':('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs'),
     'adjustments':ADJ[2:]}
START,END='2023-12-29','2026-10-21'
RAW='asset-expansion-raw-extension-20261023';PRIMARY='asset-expansion-SH603056-delisting-original-20261023'
FIELDS={'bars':BAR,'distributions':DIV,'adjustments':ADJ}


def need(x,msg):
    if not x:raise ValueError(msg)

def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jd(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def day(d):need(date.fromisoformat(d).isoformat()==d,'canonical date');return d

def numeric(v):
    n=Decimal(v);need(n.is_finite() and n>=0,'finite nonnegative amount');return n

def normalized(row,field):
    return {k:numeric(v) if k in NUM[field] and v else v for k,v in row.items()}

def rows(data,fields):
    need(data['fields']==list(fields),'native schema')
    need(all(type(r) is list and len(r)==len(fields) and all(type(v) is str for v in r) for r in data['rows']),'native row shape')
    return [dict(zip(fields,r)) for r in data['rows']]

def check_packet(actual,original,observed,sessions,boundary=None):
    code=original['instrument'];symbol=code[:2].lower()+'.'+code[2:];old_end=original['window'][1]
    active=[d for d in sessions if boundary is None or d<boundary['effective_date']]
    need(active and active[0]==START,'active sessions')
    tail=rows(observed['daily'],BAR);annual=rows(observed['dividend2026'],DIV);adjust=rows(observed['adjustments'],ADJ)
    need(all(old_end<day(r['date'])<=active[-1] for r in tail),'bounded raw tail')
    need(all(old_end<day(r['dividOperateDate'])<=active[-1] for r in adjust),'bounded adjustment tail')
    need(all(r['dividOperateDate'] and day(r['dividOperateDate']).startswith('2026') and r['dividOperateDate']<=active[-1] for r in annual),'unresolved distribution date/window')
    prior=[normalized(r,'distributions') for r in original['distributions'] if r['dividOperateDate'].startswith('2026')]
    need(prior==[normalized(r,'distributions') for r in annual if r['dividOperateDate']<=old_end],'annual source overlap')
    expected={'instrument':code,'window':[START,active[-1]],'bars':original['bars']+tail,
        'distributions':original['distributions']+[r for r in annual if r['dividOperateDate']>old_end],
        'adjustments':original['adjustments']+adjust,'quarantine':original['quarantine']}
    need(not expected['quarantine'],'unresolved quarantine')
    need(all(actual[k]==v for k,v in expected.items()),'packet does not equal original plus source rows')
    for field,fields in FIELDS.items():
        key='date' if field=='bars' else 'dividOperateDate';dates=[]
        for r in expected[field]:
            need(set(r)==set(fields) and all(type(v) is str for v in r.values()),'complete row fields')
            need(r['code']==symbol and day(r[key]) in active,'issuer/session identity')
            normalized(r,field);dates.append(r[key])
            if field=='bars':
                need(r['adjustflag']=='3' and r['tradestatus'] in ('0','1') and r['isST'] in ('0','1'),'market state')
                if r['tradestatus']=='1':
                    need(all(r[k] and numeric(r[k])>0 for k in ('open','high','low','close','preclose','volume')),'trading prices/volume')
                    need(numeric(r['low'])<=min(numeric(r['open']),numeric(r['close']))<=max(numeric(r['open']),numeric(r['close']))<=numeric(r['high']),'OHLC')
            if field=='adjustments':need(all(r[k] and numeric(r[k])>0 for k in ADJ[2:]),'adjustment positivity')
        need(dates==sorted(set(dates)),'unique chronological events')
        if field=='bars':need(dates==active,'complete active source coverage')
    need([r['date'] for r in original['bars']]==[d for d in active if d<=old_end],'unchanged original complete prefix')
    coverage={'active_source_sessions':len(active),'active_end':active[-1],'global_session_count':len(sessions),
        'post_exit_sessions_not_synthesized':len(sessions)-len(active)}
    if boundary is not None:coverage.update(effective_date=boundary['effective_date'],primary_document_sha256=boundary['primary_document_sha256'])
    return coverage


def query(root,identity):
    key=jd(identity);p=root/'queries'/key
    need(load(p/'request.json')==identity,'query identity')
    need(sorted(v.name for v in p.iterdir())==['request.json','reserved-1.json','response-1.json'],'one source attempt')
    reservation=load(p/'reserved-1.json');r=load(p/'response-1.json')
    need(reservation['identity_sha256']==key and reservation['attempt']==1,'reservation identity')
    need(r['identity_sha256']==key and r['reservation_sha256']==sha(p/'reserved-1.json') and r['status']=='CAPTURED','response chain')
    need(r['payload_sha256']==jd(r['payload']),'response payload hash')
    at=datetime.fromisoformat(reservation['reserved_at_utc']);end=datetime.fromisoformat(r['payload']['captured_at_utc'])
    need(at.tzinfo is not None and end.tzinfo is not None and at<=end,'aware capture order')
    need(r['payload']['fields']==['provider_response'] and len(r['payload']['rows'])==1,'SDK envelope')
    native=r['payload']['rows'][0]
    need(native['initial_error_code']==native['final_error_code']=='0' and native['iteration_error_type'] is None,'complete SDK native response')
    receipt={}
    for k,f in [('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')]:
        receipt[k+'_file']=str((p/f).relative_to(root));receipt[k+'_sha256']=sha(p/f)
    return {'fields':native['fields'],'rows':native['rows']},receipt


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();repo=Path(__file__).resolve().parents[3];base=Path(a.source_root);out=Path(a.output);request=Path(a.request)
    need(not out.exists() and sha(request)==a.expected_request_sha256,'fresh output and frozen request')
    r=load(request);inputs={str(request.resolve()):a.expected_request_sha256,str(Path(__file__).resolve()):sha(Path(__file__))}
    for name,h in r['bound_sha256'].items():
        kind,n=name.split('/',1);root={'repo':repo,'source':base}[kind];path=root/n
        need(not Path(n).is_absolute() and '..' not in Path(n).parts and sha(path)==h,'original input hash')
        inputs[str(path.resolve())]=h
    reconstructed=base/r['output_directory'];m=load(reconstructed/'manifest.json');ext=load(base/RAW/'request.json')
    need(m['reconstruction_complete'] and m['names']==47 and not m['pending_codes'] and not m['original_error'] and not m['changed_inputs'] and not m['persistence_errors'],'complete reconstruction')
    need(m['request_sha256']==a.expected_request_sha256,'manifest request')
    outputs={str(f):sha(f) for f in reconstructed.rglob('*') if f.is_file()};need(len(outputs)==100,'complete100 retained outputs')
    actual_before=load(reconstructed/'inputs-before.json');need(actual_before=={k:v for k,v in inputs.items() if k!=str(Path(__file__).resolve())},'all817 bound reconstruction inputs')
    need(load(reconstructed/'inputs-after.json')=={'unchanged':True,'changed_or_missing':[],'consumed_files':817},'original posthash')
    native={};receipts={}
    need(len(list((base/RAW/'queries').iterdir()))==142 and len(ext['query_whitelist'])==142,'all142 source identities')
    for q in ext['query_whitelist']:
        key=(q['instrument'],q['component']);need(key not in native,'unique source identity')
        native[key],receipts[key]=query(base/RAW,{'source':'BaoStock',**q,'asset_expansion_extension_request_sha256':sha(base/RAW/'request.json')})
    cal=native['CN_STOCK_CALENDAR','calendar'];need(cal['fields']==['calendar_date','is_trading_day'],'calendar fields')
    lo,hi=map(date.fromisoformat,(START,END));labels=[(lo+timedelta(days=i)).isoformat() for i in range((hi-lo).days+1)]
    need(all(len(row)==2 and row[1] in ('0','1') for row in cal['rows']) and [row[0] for row in cal['rows']]==labels,'full observed calendar')
    sessions=[d for d,flag in cal['rows'] if flag=='1'];need(len(sessions)==677 and sessions[0]==START and sessions[-1]==END,'677 explicit sessions')
    need(load(reconstructed/'calendar.json')['sessions']==sessions,'stored calendar')
    for name in load(repo/'experiments/qlib/asset-expansion-2026-raw-cache-inventory.json')['cache_manifests']:
        old=load(base/name/'calendar.json')['sessions'];need([d for d in sessions if d<=old[-1]]==old,'all13 original calendar prefixes')
    for n in ('login-response-1.json','logout-response.json'):need(load(base/RAW/n)['error_code']=='0','admin outcome')
    need(len(list((base/RAW).glob('login-reserved-*.json')))==1,'one login')
    primary=base/PRIMARY/'SH603056-original.pdf';pdfsha=sha(primary)
    from pypdf import PdfReader
    from pdfminer.high_level import extract_text
    reader=PdfReader(primary);need(len(reader.pages)==4,'primary page count')
    for page in (0,1):
        for text in (reader.pages[page].extract_text(),extract_text(str(primary),page_numbers=[page])):
            text=re.sub(r'\s+','',text)
            checks=('603056','2026-037','德邦物流股份有限公司','终止上市暨摘牌日为2026年3月31日') if page==0 else ('第四节终止上市暨摘牌日期','公司股票将于2026年3月31日终止上市暨摘牌')
            need(all(v in text for v in checks),'independent literal primary exit evidence')
    life={'SH603056':{'kind':'DELISTING_END','effective_date':'2026-03-31','verified_primary_boundary':True,'primary_document_sha256':pdfsha}}
    need(load(reconstructed/'lifecycles.json')==r['lifecycle']==life,'evaluator-only exact primary proof')
    target=load(repo/'experiments/qlib/asset-expansion-2026-targets.json')['low_asset_expansion_decile_conditional']
    codes=sorted({c for t in target.values() for c in t['weights']});need(codes==r['codes']==sorted(m['per_code_sha256']) and len(codes)==47 and len(target)==34,'unchanged full47 dependencies')
    totals={'bars':0,'distributions':0,'adjustments':0};cache={};prefixes=0
    for code in codes:
        route=ext['reuse_routes'][code];original=load(base/route['cache']/'codes'/(code+'.json'))
        path=reconstructed/'codes'/(code+'.json');actual=load(path)
        need(sha(path)==m['per_code_sha256'][code],'new packet hash')
        observed={k:native[code,k] for k in ('daily','dividend2026','adjustments')}
        c=check_packet(actual,original,observed,sessions,life.get(code))
        need(c==m['coverage'][code]==load(reconstructed/'coverage'/(code+'.json')),'exact per-issuer source coverage')
        need(actual['source_query_receipts']=={k:receipts[code,k] for k in observed},'all packet source receipts')
        need(actual['request_sha256']==sha(base/RAW/'request.json'),'packet original request')
        need(actual['original_packet_semantic_sha256']==hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'original semantic identity')
        if code!='SH603056':need(path.read_bytes()==(base/RAW/'codes'/(code+'.json')).read_bytes(),'46 successful original bytes');prefixes+=1
        for k in totals:totals[k]+=len(actual[k])
        cache[code]=(actual,original,observed)
    controls=[]
    probe=next(c for c,(p,_,_) in cache.items() if p['distributions'] and c!='SH603056')
    def reject(label,code,mutate):
        actual,old,obs=copy.deepcopy(cache[code]);mutate(actual)
        try:check_packet(actual,old,obs,sessions,life.get(code))
        except (ValueError,KeyError):controls.append(label)
        else:raise ValueError('semantic control accepted: '+label)
    reject('wrong_tail_close',probe,lambda p:p['bars'][-1].update(close='1'))
    reject('altered_original_ST',probe,lambda p:p['bars'][0].update(isST='1'))
    reject('duplicate_tail_bar',probe,lambda p:p['bars'].append(p['bars'][-1]))
    reject('wrong_gross_cash',probe,lambda p:p['distributions'][0].update(dividCashPsBeforeTax='999'))
    reject('altered_after_tax_literal',probe,lambda p:p['distributions'][0].update(dividCashPsAfterTax='forged'))
    reject('missing_active_exit_bar','SH603056',lambda p:p['bars'].pop())
    reject('invented_post_exit_bar','SH603056',lambda p:p['bars'].append({**p['bars'][-1],'date':'2026-03-31'}))
    need(prefixes==46 and totals['bars']==31683 and m['coverage']['SH603056']['post_exit_sessions_not_synthesized']==136,'full source count and classified gap')
    need(all(sha(Path(n))==h for n,h in inputs.items()) and all(sha(Path(n))==h for n,h in outputs.items()),'original/output posthash')
    result={'status':'SEPARATE_ALL142_QUERIES_ALL47_SOURCE_ROWS_AND_PRIMARY_EXIT_CHECKED_ACCOUNT_CLEARANCE_PENDING',
        'audit_code_sha256':sha(Path(__file__)),'request_sha256':a.expected_request_sha256,'reconstruction_manifest_sha256':sha(reconstructed/'manifest.json'),
        'names':47,'source_query_chains_checked':142,'global_sessions':677,'source_totals':totals,'successful_original_packets_byte_identical':46,
        'exit_active_sessions':541,'post_exit_prices_not_synthesized':136,'primary_pdf_sha256':pdfsha,'primary_two_extractors_pages_checked':[0,1],
        'semantic_negative_controls_rejected':controls,'all_consumed_input_sha256':inputs,'all_reconstruction_output_sha256':outputs,
        'all_inputs_and_outputs_unchanged':True,'account_owned_pending_and_claims_verified':False,'admitted_for_account_replay':False,
        'historical_arrival_verified':False,'portfolio_returns_computed':False,'objective_achieved':False}
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('separate QA all47,142chains,31683bars,7semantic negatives; account clearance pending',flush=True)


if __name__=='__main__':main()
