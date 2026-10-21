"""Independent stdlib-only IVOL pre2026 source-event output audit.

No project imports, production compiler, account replay or portfolio return.
Actual output is read only after --terminal-confirmed and frozen method checks.
Events/receipt IDs are reconstructed from authenticated source rows and primary
literals. Adjustments are used exclusively for coverage, never entitlements.
"""
from pathlib import Path
from datetime import date
from decimal import Decimal as D, ROUND_DOWN
from fractions import Fraction
from collections import Counter
import argparse, copy, hashlib, json, re, subprocess

START,END='2023-12-29','2025-12-31'
RAW='low-market-residual-vol1m-raw-pre2026-20261021'
PRIMARY='low-market-residual-vol1m-primary-pre2026-20261021'
DEVELOPMENT='low-market-residual-vol1m-budgeted-pre2026-development-20261021'
OUTPUT='low-market-residual-vol1m-account-source-events-pre2026-20261021'
PREFIX='experiments/qlib/low-market-residual-vol1m-'
CONTRACT='PRIMARY_EVENT_COMPONENT_COMPLETION_V1'
BODY=('effective_proofs.json','derived_events.json','event_source_receipts.json','lifecycles.json',
      'initial_listing_classification.json','coverage_validation.json')
UNKNOWN={'SH600580|2025-06-27','SH600763|2024-07-05','SH603290|2024-05-23',
         'SH603688|2024-05-22','SH603927|2024-05-21','SZ000403|2025-06-04'}
OLD_TYPES={('capital_tax',k) for k in ('SH600885|2025-06-19','SH600998|2024-06-07',
 'SH601128|2024-05-29','SH601128|2025-06-05','SZ002984|2024-04-19','SZ003031|2024-06-11')}|{
 ('stock_dividend_tax_bases','SH603826|2024-06-27'),('cash_overrides','SZ001914|2025-08-13'),
 ('primary_cash_supplement','SZ002508|2024-01-10')}
LIFE={'SH603341':('LISTING_BEGIN','2024-03-01',38), 'SZ002505':('DELISTING_END','2024-08-30',323)}

def check(v,label):
    if not v:raise AssertionError(label)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def number(s):
    check(isinstance(s,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',s) is not None,'plain nonnegative source amount')
    v=D(s);check(v.is_finite() and v>=0,'finite source amount');return v
def day(s):
    check(isinstance(s,str) and date.fromisoformat(s).isoformat()==s and s<=END,'canonical pre2026 date');return s
def inside(root,rel):
    root=Path(root).resolve();v=Path(rel);p=(root/v).resolve()
    check(not v.is_absolute() and '..' not in v.parts and p.is_relative_to(root),'contained relative input path');return p

def alias_economics(kind,p):
    if kind=='primary_cash_supplement':
        r=p['record'];return (p['instrument'],*(r[k] for k in ('dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate')),
                              *(D(r[k]) for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs')))
    if kind=='capital_tax':return (p.get('verified_exempt') is True,)
    if kind=='stock_dividend_tax_bases':return (p.get('verified') is True,D(p['expected_stock_per_original_share']),D(p['taxable_income_per_original_share']))
    check(kind=='cash_overrides','known original proof type')
    return (p.get('verified') is True,p['kind'],p['source_row_sha256'],D(p['expected_vendor_cash_per_share']),D(p['effective_cash_per_share']))

def project_components(packets,proofs):
    """Independently compose two literal cash rows or complete blank capital0."""
    check(not proofs.get('component_precision_overrides'),'unsupported V3 precision absent')
    result=copy.deepcopy(packets);records={};docs={d['file']:d for d in proofs['documents']}
    dates={'publication_day':'dividPlanDate','record_date':'dividRegistDate','ex_date':'dividOperateDate','cash_payment_date':'dividPayDate','stock_listing_date':'dividStockMarketDate'}
    for key,p in proofs['primary_event_components'].items():
        code,ex=key.split('|');rows=[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
        check(p['verified'] is True and type(p['version']) is int and p['version']==1 and p['instrument']==code and p['ex_date']==ex,'typed component identity')
        doc=docs[p['source_file']];check(doc['sha256']==p['source_sha256'] and doc['instrument']==code and doc['day']==p['publication_day'],'component primary binding')
        check(p['primary_pages']==sorted(set(p['primary_pages'])) and p['primary_pages'] and all(type(n) is int and n>0 for n in p['primary_pages']),'positive unique component pages')
        for r in rows:
            check(r['code']==code[:2].lower()+'.'+code[2:],'component row issuer')
            for a,b in dates.items():check(p[a]==(r[b] or None),'component date literal')
        if p['kind']=='PRIMARY_TWO_CASH_COMPONENT_SUM':
            check(len(rows)==2 and len({digest(r) for r in rows})==2,'two distinct cash rows')
            c=p['components'];check(len(c)==2 and {r['source_row_sha256'] for r in c}=={digest(r) for r in rows},'cash row component bindings')
            by={r['source_row_sha256']:r for r in c};amounts=[]
            for r in rows:
                a=number(r['dividCashPsBeforeTax']);check(a>0 and a==number(by[digest(r)]['cash_per_original_share']),'cash component literal amount')
                check(number(r['dividStocksPs'])==0 and number(r['dividReserveToStockPs'] or '0')==0 and not r['dividStockMarketDate'],'cash-only component')
                amounts.append(Fraction(a))
            check(sum(amounts,Fraction(0))==Fraction(number(p['combined_cash_per_original_share'])),'exact rational component sum')
            check(number(p['stock_per_original_share'])==number(p['capital_per_original_share'])==0 and p['stock_listing_date'] is None,'combined cash no shares')
            derived=copy.deepcopy(rows[0]);derived.update(dividCashPsBeforeTax=p['combined_cash_per_original_share'],dividReserveToStockPs='0',dividCashStock='PRIMARY_NOTICE_TWO_CASH_COMPONENT_SUM')
            if 'dividCashPsAfterTax' in derived:derived['dividCashPsAfterTax']=''
        else:
            check(p['kind']=='PRIMARY_STOCK_ZERO_CAPITAL' and len(rows)==1,'one stock-zero-capital component')
            r=rows[0];check(digest(r)==p['source_row_sha256'] and r['dividReserveToStockPs']=='','literal blank capital only')
            check(number(p['capital_per_original_share'])==0 and number(r['dividStocksPs'])==number(p['stock_per_original_share'])>0 and number(r['dividCashPsBeforeTax'])==number(p['cash_per_original_share']),'stock/cash invariant under zero completion')
            check(p['stock_listing_date'] is not None,'positive stock listing date');derived=copy.deepcopy(r);derived['dividReserveToStockPs']='0'
        receipt={'contract':CONTRACT,'version':1,'event_key':key,'source_kind':p['kind'],
            'original_source_row_sha256':[digest(r) for r in rows],'derived_source_row_sha256':digest(derived),
            'primary_source_sha256':doc['sha256'],'source_file':doc['file'],'primary_pages':copy.deepcopy(p['primary_pages']),
            'primary_component_proof_sha256':digest(p),'original_source_rows_modified':False,'stock_tax_basis_granted':False,'capital_tax_exemption_granted':False}
        if p['kind']=='PRIMARY_TWO_CASH_COMPONENT_SUM':receipt.update(combined_cash_per_original_share=p['combined_cash_per_original_share'],cash_settlement_contract='ONE_COMBINED_PER_REGISTERED_SHARE_EVENT_ACCOUNT_EXISTING_AGGREGATE_ROUNDING',separate_component_cent_settlement_equivalence_certified=False)
        records[key]=receipt
        output=[];emitted=False
        for r in result[code]['distributions']:
            if r['dividOperateDate']!=ex:output.append(r)
            elif not emitted:output.append(derived);emitted=True
        result[code]['distributions']=output
    return result,records

def reconstruct_events(packets,proofs,sessions):
    projected,compositions=project_components(packets,proofs);documents={d['file']:d for d in proofs['documents']}
    rows=[(c,r,'VENDOR_DISTRIBUTION',None) for c in sorted(projected) for r in projected[c]['distributions']]
    rows += [(s['instrument'],s['record'],'PRIMARY_NOTICE_SUPPLEMENT',s) for s in proofs['supplementary_distributions']]
    result=[];receipts=[];seen=set();consumed={k:set() for k in ('capital_tax','stock_dividend_tax_bases','cash_overrides')}
    def bind(p,c,r):
        d=documents[p['source_file']];check(d['sha256']==p['source_sha256'] and d['instrument']==c and d['day']==r['dividPlanDate'],'primary source economics binding');return d['sha256']
    for code,row,kind,supplement in rows:
        key=code+'|'+row['dividOperateDate'];check(key not in seen,'unique event date');seen.add(key);check(row['code']==code[:2].lower()+'.'+code[2:],'event issuer')
        cash=number(row['dividCashPsBeforeTax']);stock=number(row['dividStocksPs']);income=D(0);capital_verified=False;stock_verified=False
        primary=[bind(supplement,code,row)] if supplement else []
        p=proofs['stock_dividend_tax_bases'].get(key)
        if p:
            check(p['verified'] is True and stock>0 and stock==number(p['expected_stock_per_original_share']),'original verified stock basis applies')
            income=number(p['taxable_income_per_original_share']);check(income>0,'positive stock taxable income');stock_verified=True;primary.append(bind(p,code,row));consumed['stock_dividend_tax_bases'].add(key)
        text=row['dividReserveToStockPs']
        if not text:
            display=row.get('dividCashStock','');cashonly=cash>0 and stock==0 and display.startswith('10派') and not any(x in display for x in ('送','转')) and not row['dividStockMarketDate']
            stockonly=stock_verified and display.startswith('10送') and '转' not in display
            check(cashonly or stockonly,'blank capital requires literal supported classification');text='0'
        capital=number(text);p=proofs['capital_tax'].get(key)
        if p:
            check(p['verified_exempt'] is True and capital>0,'original positive capital proof applies');primary.append(bind(p,code,row));capital_verified=True;consumed['capital_tax'].add(key)
        announced,recorded,ex=[day(row[k]) for k in ('dividPlanDate','dividRegistDate','dividOperateDate')];paid=day(row['dividPayDate']) if row['dividPayDate'] else None;listed=day(row['dividStockMarketDate']) if row['dividStockMarketDate'] else None
        check(announced<recorded<ex and recorded in sessions and ex in sessions,'event timing and observed source dates')
        check(not cash or paid is not None and paid>=ex,'cash payment timing');check(not(capital or stock) or listed is not None and listed>=ex,'share listing timing')
        identity={'instrument':code,'source_kind':kind,'source_distribution':row,'primary_source_sha256':sorted(set(primary)),
            'effective_stock_taxable_income_per_original_share':str(income),'capital_tax_exempt_verified':capital_verified,'stock_tax_basis_verified':stock_verified}
        eid=digest(identity);e={'event_id':eid,'instrument':code,'announced':announced,'recorded':recorded,'ex_date':ex,'pay_date':paid,'listed':listed,'cash_per_share':str(cash),'capital_per_share':str(capital),'capital_tax_exempt_verified':capital_verified,'stock_per_share':str(stock),'stock_taxable_income_per_share':str(income),'stock_tax_basis_verified':stock_verified}
        r={'event_id':eid,'instrument':code,'ex_date':ex,'source_kind':kind,'source_row_sha256':digest(row),'primary_source_sha256':sorted(set(primary)),'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not capital_verified or stock>0 and not stock_verified)}
        p=proofs['cash_overrides'].get(key)
        if p:
            check(kind=='VENDOR_DISTRIBUTION' and p['verified'] is True and p['kind']=='PRIMARY_NOTICE_CASH_PRECISION' and p['source_row_sha256']==digest(row),'literal precision proof binding')
            check(stock==capital==0 and listed is None,'cash-only precision');docsha=bind(p,code,row);effective=number(p['effective_cash_per_share']);expected=number(p['expected_vendor_cash_per_share']);quantum=D(1).scaleb(cash.as_tuple().exponent)
            check(cash==expected>0 and effective>cash and effective.quantize(quantum,rounding=ROUND_DOWN)==cash,'precision-only source completion')
            change={'original_event_id':eid,'source_kind':'PRIMARY_CASH_PRECISION_CORRECTION','source_row_sha256':digest(row),'primary_source_sha256':docsha,'cash_precision_proof_sha256':digest(p),'vendor_cash_per_share':str(cash),'effective_cash_per_share':str(effective)}
            eid=digest(change);e.update(event_id=eid,cash_per_share=str(effective));r.update(event_id=eid,original_event_id=change['original_event_id'],source_kind=change['source_kind'],primary_source_sha256=sorted(set(primary+[docsha])),vendor_cash_per_share=str(cash),effective_cash_per_share=str(effective),cash_precision_proof_sha256=digest(p));consumed['cash_overrides'].add(key)
        if key in compositions:
            comp=compositions[key];check(r['source_kind']=='VENDOR_DISTRIBUTION' and r['source_row_sha256']==comp['derived_source_row_sha256'] and not stock_verified and not capital_verified and income==0,'component composition grants no tax flag')
            canonical=e['event_id'];eid=digest({'source_kind':comp['source_kind'],'canonical_derived_event_id':canonical,'projection_receipt_sha256':digest(comp)})
            e['event_id']=eid;r.update(event_id=eid,source_kind=comp['source_kind'],canonical_derived_event_id=canonical,original_source_row_sha256=comp['original_source_row_sha256'],derived_source_row_sha256=comp['derived_source_row_sha256'],primary_source_sha256=sorted(set(r['primary_source_sha256']+[comp['primary_source_sha256']])),projection_receipt_sha256=digest(comp),projection_receipt=copy.deepcopy(comp))
        result.append(e);receipts.append(r)
    for k,v in consumed.items():check(v==set(proofs[k]),'all source proofs consumed once')
    check(len(result)==len(receipts)==len({e['event_id'] for e in result})==862,'862unique independent event IDs')
    check({e['instrument']+'|'+e['ex_date'] for e in result if D(e['capital_per_share'])>0 and not e['capital_tax_exempt_verified'] or D(e['stock_per_share'])>0 and not e['stock_tax_basis_verified']}==UNKNOWN,'six unknown tax guards')
    check(sum(e['capital_tax_exempt_verified'] for e in result)==6 and sum(e['stock_tax_basis_verified'] for e in result)==1,'unaltered tax flags')
    return result,receipts


def independent_coverage(packets,events,initial,lifecycles,sessions):
    view=copy.deepcopy(packets);exdates={c:set() for c in packets}
    for e in events:exdates[e['instrument']].add(e['ex_date'])
    check(len(initial)==1,'one original listing anchor')
    for item in initial:
        c=item['instrument'];p=view[c];at=item['effective_date'];proof=lifecycles[c];matches=[r for r in p['adjustments'] if r['dividOperateDate']==at]
        check(item['classification']=='INITIAL_LISTING_NORMALIZATION_NOT_DISTRIBUTION' and item['factor_used_to_infer_cash_or_shares'] is False,'listing anchor is not distribution')
        check(proof['kind']=='LISTING_BEGIN' and proof['effective_date']==at and proof['primary_document_sha256']==item['primary_document_sha256'],'listing primary source binding')
        check(p['bars'][0]['date']==at and matches==[item['source_adjustment']] and at not in exdates[c],'one initial observed nonentitlement adjustment')
        check(D(matches[0]['backAdjustFactor'])==D(matches[0]['adjustFactor'])==1 and D(matches[0]['foreAdjustFactor'])>0,'unit listing adjustment')
        p['adjustments']=[r for r in p['adjustments'] if r!=matches[0]]
    adjacent=[]
    for c,p in view.items():
        for item in p['quarantine']:
            at=item['record'].get('dividOperateDate','');check(item['reason']=='AFTER_CAPTURE_CUTOFF' and at>END or item['reason']=='BEFORE_CAPTURE_WINDOW' and at and at<START,'only outside-window quarantines')
        previous=None;indices={r['date']:i for i,r in enumerate(p['bars'])}
        for row in p['bars']:
            ref=D(row['preclose']) if row['preclose'] else None
            check(previous is None or ref is None or ref<=0 or abs(ref-previous)<=D('.005') or row['date'] in exdates[c],'source reference continuity beside event')
            if row['close'] and D(row['close'])>0:previous=D(row['close'])
        for a in p['adjustments']:
            at=a['dividOperateDate'];check(at in indices,'observed adjustment date');i=indices[at]
            check(at in exdates[c] or i>0 and p['bars'][i-1]['date'] in exdates[c],'adjustment matched same or preceding source event')
            if at not in exdates[c]:adjacent.append({'instrument':c,'adjustment_day':at,'preceding_event_day':p['bars'][i-1]['date'],'source_adjustment_sha256':digest(a)})
    intervals=[]
    for at in sessions:
        for c in sorted(packets):
            rows={r['date']:r for r in packets[c]['bars']};proof=lifecycles.get(c);present=at in rows;reason=None
            if proof and proof['kind']=='LISTING_BEGIN' and at<proof['effective_date']:
                check(not present,'no prelisting source bars');reason='BEFORE_PRIMARY_LISTING_BOUNDARY'
            elif proof and proof['kind']=='DELISTING_END' and at>=proof['effective_date']:reason='AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY'
            if reason:intervals.append({'instrument':c,'session':at,'reason':reason,'original_row_present':present,'primary_document_sha256':proof['primary_document_sha256'],'synthetic_price_created':False})
            else:check(present,'no unexplained source gap')
    check(sum(not r['original_row_present'] for r in intervals)==361,'38+323 missing source sessions')
    return intervals,adjacent


def expected_projection(base,repo,requestfile,expected_sha,freeze):
    check(sha(requestfile)==expected_sha,'external frozen source plan SHA');p=read(requestfile)
    check(p['status']=='FROZEN_IVOL_PRE2026_SOURCE_EVENT_PROJECTION_NO_ROI' and p['candidate']=='low_market_residual_vol_1m' and p['window']==[START,END] and p['output_relative']==OUTPUT,'fixed source plan scope')
    check(p['portfolio_returns_to_compute'] is False and p['new_2026_queries_allowed'] is False,'source-only boundary')
    watched={}
    def bind(path,h):
        path=Path(path).resolve();check(path.is_relative_to(base) or path.is_relative_to(repo) or path==Path(requestfile).resolve(),'bounded source path');check(sha(path)==h,'actual input hash '+str(path));watched[str(path)]=h
    bind(requestfile,expected_sha)
    # Frozen code/protocol/request identities are checked against Git blobs.
    if freeze:
        for name,h in {**p['method_code_sha256'],p['protocol_file']:p['protocol_sha256']}.items():
            blob=subprocess.check_output(['git','show',freeze+':'+name],cwd=repo);check(hashlib.sha256(blob).hexdigest()==h,'frozen method/protocol '+name)
        if Path(requestfile).resolve().is_relative_to(repo):
            name=str(Path(requestfile).resolve().relative_to(repo));check(hashlib.sha256(subprocess.check_output(['git','show',freeze+':'+name],cwd=repo)).hexdigest()==expected_sha,'frozen request blob')
    for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for name,h in p[field].items():bind(inside(parent,name),h)
    bind(repo/p['protocol_file'],p['protocol_sha256'])
    public=lambda tail:read(repo/(PREFIX+tail+'.json'))
    manifest=read(base/RAW/'manifest.json');rawaudit=public('raw-source-independent-audit');primary=read(base/PRIMARY/'manifest.json');primaryaudit=public('primary-source-independent-audit')
    check(rawaudit['status']=='PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT' and rawaudit['capture_complete'] is True and rawaudit['manifest_sha256']==sha(base/RAW/'manifest.json'),'original independent raw audit')
    check(primaryaudit['status']=='PASS_INDEPENDENT_EIGHT_PRIMARY_CAPTURE_AUDIT' and primaryaudit['capture_complete'] is True and primaryaudit['manifest_sha256']==sha(base/PRIMARY/'manifest.json'),'original independent primary audit')
    for name,h in rawaudit['whole_capture_tree_sha256'].items():bind(inside(base/RAW,name),h)
    financial=rawaudit['old42_financial_sha256'];check(len(financial)==42,'old42 financial map')
    old=read(base/DEVELOPMENT/'summary.json');check({case+'/'+n:h for case,r in old['results_by_extra_bps_and_family'].items() for n,h in r['artifact_sha256'].items()}==financial,'old summary actual42 binding')
    for name,h in financial.items():bind(inside(base/DEVELOPMENT,name),h)
    sessions=read(base/RAW/'calendar.json')['sessions'];check(len(sessions)==486 and sessions==sorted(set(sessions)) and [sessions[0],sessions[-1]]==[START,END],'486 source calendar')
    targets=read(base/DEVELOPMENT/'targets.json')['low_market_residual_vol_1m'];check(len(targets)==24 and sha(base/DEVELOPMENT/'targets.json')==manifest['target_sha256'],'24frozen targets')
    packets={}
    for c,h in manifest['per_code_sha256'].items():
        f=base/RAW/'codes'/(c+'.json');bind(f,h);v=read(f);check(v['instrument']==c and v['window']==[START,END],'raw issuer/window')
        check([r['date'] for r in v['bars']]==sorted({r['date'] for r in v['bars']}) and all(r['date'] in sessions for r in v['bars']),'bounded unique raw dates');packets[c]=v
    check(len(packets)==361 and set(packets)=={c for t in targets.values() for c in t['weights']},'361 primary target/source universe')
    check(sum(len(v['distributions']) for v in packets.values())==860 and sum(len(v['adjustments']) for v in packets.values())==875,'original vendor row counts')
    for name,h in primaryaudit['artifact_sha256'].items():bind(inside(base/PRIMARY,name),h)
    proposal=public('primary-completion-proposal');verified=public('primary-completion-proposal-independent-check');inventory=public('pre2026-corporate-cache-inventory');content=public('primary-content-independent-review')
    check(verified['proposal_sha256']==sha(repo/(PREFIX+'primary-completion-proposal.json')) and verified['primary_content_review_sha256']==sha(repo/(PREFIX+'primary-content-independent-review.json')),'proposal literal review binding')
    check(verified['critical_findings']==verified['important_findings']==verified['findings']==[],'no primary completion review findings')
    check(proposal['capital_tax']==proposal['stock_dividend_tax_bases']==proposal['cash_overrides']=={} and proposal['actual_source_projection_run'] is False,'new proposal grants no tax flag')
    for d in proposal['documents']:
        bind(base/PRIMARY/d['file'],d['sha256']);case=content['cases'][d['original_manifest_case_id']];original=primary['documents'][d['original_manifest_case_id']]
        check(d['day']==case['capture_publication_day']==original['publication_day'] and d['sha256']==case['pdf_sha256']==original['sha256'],'publication day and primary PDF bytes')
    effective={'documents':[],'capital_tax':{},'stock_dividend_tax_bases':{},'cash_override_contract':'PRIMARY_NOTICE_CASH_PRECISION_V1','cash_overrides':{},'supplementary_distributions':[], 'primary_event_component_contract':CONTRACT,'primary_event_components':copy.deepcopy(proposal['primary_event_components'])}
    docs={};chosen={};inheritance=[]
    def add_doc(d):
        name=d['file'];check(Path(name).name==name and d['day']<=END,'pre2026 primary filename/day')
        if name in docs:check(all(docs[name][k]==d[k] for k in ('sha256','instrument','day')),'literal document alias identity')
        else:check(d['sha256'] not in {x['sha256'] for x in docs.values()},'unique selected document SHA alias');docs[name]=copy.deepcopy(d)
    for index,c in enumerate(inventory['proof_candidates']):
        bind(c['reviewed_manifest'],c['reviewed_manifest_sha256']);m=read(c['reviewed_manifest']);kind,key=c['proof_type'],c['event_key'];code,ex=key.split('|')
        values=[s for s in m.get('supplementary_distributions',[]) if s['instrument']+'|'+s['record']['dividOperateDate']==key] if kind=='primary_cash_supplement' else [m[kind][key]]
        check(len(values)==1 and values[0]==c['proof_literal'],'chosen original proof literal');literal=values[0];bind(c['pdf_path'],c['pdf_sha256'])
        dd=[d for d in m['documents'] if d['file']==literal['source_file']];check(len(dd)==1,'one cached original document metadata');d=dd[0]
        check(d['instrument']==code and d['sha256']==literal['source_sha256']==c['pdf_sha256'] and Path(c['pdf_path']).name==d['file'],'cached primary bytes and issuer')
        rr=[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
        if kind=='primary_cash_supplement':check(not rr and d['day']==literal['record']['dividPlanDate'],'primary supplement absent vendor row')
        else:check(len(rr)==1 and rr[0]['dividPlanDate']==d['day'],'cached proof exact current vendor event')
        alias={'inventory_index':index,'reviewed_manifest':c['reviewed_manifest'],'reviewed_manifest_sha256':c['reviewed_manifest_sha256'],'pdf_path':c['pdf_path'],'pdf_sha256':c['pdf_sha256'],'proof_literal_sha256':digest(literal)}
        ident=(kind,key)
        if ident in chosen:
            check(alias_economics(kind,literal)==alias_economics(kind,chosen[ident]),'proof aliases equal economic meaning');next(x for x in inheritance if (x['proof_type'],x['event_key'])==ident)['aliases'].append(alias);continue
        chosen[ident]=copy.deepcopy(literal);add_doc(d)
        inheritance.append({'event_key':key,'proof_type':kind,'chosen_inventory_index':index,'chosen_original_proof_literal_sha256':digest(literal),'aliases':[alias],'actual_zero_ownership_proof_transferred':False,'tax_evidence_scope_strengthened':False})
        if kind=='primary_cash_supplement':effective['supplementary_distributions'].append(copy.deepcopy(literal))
        else:effective[kind][key]=copy.deepcopy(literal)
    check(set(chosen)==OLD_TYPES,'exact9 inherited proof types')
    for d in proposal['documents']:add_doc(d)
    for s in proposal['supplementary_distributions']:
        check(not any(r['dividOperateDate']==s['record']['dividOperateDate'] for r in packets[s['instrument']]['distributions']),'new supplement not vendor rewrite');effective['supplementary_distributions'].append(copy.deepcopy(s))
    life={}
    for c in inventory['lifecycle_candidates']:
        bind(c['reviewed_manifest'],c['reviewed_manifest_sha256']);m=read(c['reviewed_manifest']);proof=c['proof_literal'];code=c['instrument'];check(m['lifecycles'][code]==proof,'original lifecycle literal')
        bind(c['pdf_path'],proof['primary_document_sha256']);d=next(d for d in m['documents'] if d['file']==proof['source_file']);check(d['sha256']==proof['primary_document_sha256'] and d['instrument']==code,'primary lifecycle PDF identity');add_doc(d);life[code]=copy.deepcopy(proof)
    check(set(life)==set(LIFE),'two primary lifecycle boundaries')
    for code,packet in packets.items():
        missing=[d for d in sessions if d not in {r['date'] for r in packet['bars']}]
        if code not in LIFE:check(not missing,'other names full source calendar');continue
        kind,boundary,count=LIFE[code];check(life[code]['kind']==kind and life[code]['effective_date']==boundary and life[code]['verified_primary_boundary'] is True,'fixed primary listing/delisting dates')
        allowed=[d for d in sessions if d<boundary] if kind=='LISTING_BEGIN' else [d for d in sessions if d>boundary]
        check(missing==allowed and len(missing)==count,'exact primary source missing interval')
    effective['documents']=list(docs.values());effective.update(status='IVOL_EVALUATOR_PROOFS_NO_ACCOUNT_ADMISSION',inherited_proof_receipts=inheritance,strict_statutory_capital_tax_certification=False,actual_zero_ownership_verified=False,source_admitted_for_account_replay=False,portfolio_returns_computed=False,lifecycles=copy.deepcopy(life))
    initialpath=base/'illiquidity-source-events-20261020/initial_listing_classification.json';prior=read(base/'illiquidity-source-events-20261020/summary.json');bind(initialpath,prior['artifact_sha256']['initial_listing_classification.json']);check(sha(initialpath)=='ce202a33cf791b0047db3ced19ae7ddf3e450606fd9d49da391545dd2f1d6c57','original initial listing classifier');initial=read(initialpath)
    events,receipts=reconstruct_events(packets,effective,sessions);intervals,adjacent=independent_coverage(packets,events,initial,life,sessions)
    coverage={'compiled_event_count':862,'source_kind_counts':dict(sorted(Counter(r['source_kind'] for r in receipts).items())),'known_tax_unknown_event_keys':sorted(UNKNOWN),'coverage_validated_on_copy':True,'original_source_packets_modified':False,'initial_listing_normalizations':1,'source_gap_sessions':361,'actual_lifecycle_flat_verified':False,'factor_values_used_to_infer_entitlements':False,'historical_arrival_verified':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False}
    expected={'effective_proofs.json':effective,'derived_events.json':events,'event_source_receipts.json':receipts,'lifecycles.json':{'boundaries':life,'source_intervals':intervals,'actual_flat_inventory_verified':False,'missing_rows_filled':False},'initial_listing_classification.json':initial,'coverage_validation.json':coverage}
    return p,watched,financial,expected,adjacent,packets,sessions


def semantic_negative_controls(expected,packets,sessions):
    rejected={}
    def must_reject(name,call):
        try:call()
        except (AssertionError,ValueError,KeyError):rejected[name]=True
        else:raise AssertionError('semantic negative accepted: '+name)
    def compare(x):check(x==expected,'independent full semantic reconstruction equality')
    for mode in ('lost_event','wrong_record_date','coherent_unknown_tax_upgrade','price_reference_cash','component_receipt_rewrite','alias_literal_rewrite','lifecycle_flat_upgrade','listing_anchor_entitlement'):
        changed=copy.deepcopy(expected)
        if mode=='lost_event':changed['derived_events.json'].pop();changed['event_source_receipts.json'].pop()
        elif mode=='wrong_record_date':changed['derived_events.json'][0]['recorded']='2024-01-01'
        elif mode=='coherent_unknown_tax_upgrade':
            e=next(e for e in changed['derived_events.json'] if e['instrument']+'|'+e['ex_date'] in UNKNOWN);e['capital_tax_exempt_verified']=True
            next(r for r in changed['event_source_receipts.json'] if r['event_id']==e['event_id'])['requires_zero_record_ownership_if_tax_unverified']=False
        elif mode=='price_reference_cash':next(e for e in changed['derived_events.json'] if e['instrument']=='SH601966' and e['ex_date']=='2024-06-14')['cash_per_share']='0.37444'
        elif mode=='component_receipt_rewrite':next(r for r in changed['event_source_receipts.json'] if r['source_kind']=='PRIMARY_TWO_CASH_COMPONENT_SUM')['projection_receipt']['capital_tax_exemption_granted']=True
        elif mode=='alias_literal_rewrite':changed['effective_proofs.json']['inherited_proof_receipts'][0]['chosen_original_proof_literal_sha256']='0'*64
        elif mode=='lifecycle_flat_upgrade':changed['lifecycles.json']['actual_flat_inventory_verified']=True
        else:changed['initial_listing_classification.json'][0]['factor_used_to_infer_cash_or_shares']=True
        must_reject(mode,lambda x=changed:compare(x))
    proof=copy.deepcopy(expected['effective_proofs.json']);proof['primary_event_components']['SH601966|2024-06-14']['combined_cash_per_original_share']='0.37444'
    must_reject('wrong_sum_rejected_without_hash_gate',lambda:project_components(packets,proof))
    raw=copy.deepcopy(packets);raw['SH601966']['distributions']=[r for r in raw['SH601966']['distributions'] if digest(r)!=expected['effective_proofs.json']['primary_event_components']['SH601966|2024-06-14']['components'][1]['source_row_sha256']]
    must_reject('lost_original_cash_component_rejected_without_hash_gate',lambda:project_components(raw,expected['effective_proofs.json']))
    raw=copy.deepcopy(packets);initial=copy.deepcopy(expected['initial_listing_classification.json']);item=initial[0];code=item['instrument'];day0=item['effective_date'];r=next(r for r in raw[code]['adjustments'] if r['dividOperateDate']==day0);r['backAdjustFactor']='1.01';item['source_adjustment']=copy.deepcopy(r)
    must_reject('coherently_rebound_nonunit_listing_anchor',lambda:independent_coverage(raw,expected['derived_events.json'],initial,expected['lifecycles.json']['boundaries'],sessions))
    return rejected


def self_test():
    row={'code':'sh.600001','dividPlanDate':'2024-01-01','dividRegistDate':'2024-01-02','dividOperateDate':'2024-01-03','dividPayDate':'2024-01-03','dividStockMarketDate':'','dividCashPsBeforeTax':'0.286','dividStocksPs':'0','dividReserveToStockPs':''}
    other={**row,'dividCashPsBeforeTax':'0.091'};key='SH600001|2024-01-03';p={'kind':'PRIMARY_TWO_CASH_COMPONENT_SUM','verified':True,'version':1,'instrument':'SH600001','publication_day':'2024-01-01','record_date':'2024-01-02','ex_date':'2024-01-03','cash_payment_date':'2024-01-03','stock_listing_date':None,'source_file':'fake.pdf','source_sha256':'a'*64,'primary_pages':[1],'stock_per_original_share':'0','capital_per_original_share':'0','components':[{'source_row_sha256':digest(row),'cash_per_original_share':'0.286'},{'source_row_sha256':digest(other),'cash_per_original_share':'0.091'}],'combined_cash_per_original_share':'0.377'}
    raw={'SH600001':{'distributions':[row,other]}};proof={'documents':[{'file':'fake.pdf','instrument':'SH600001','day':'2024-01-01','sha256':'a'*64}],'primary_event_components':{key:p}}
    projected,receipts=project_components(raw,proof);check(projected['SH600001']['distributions'][0]['dividCashPsBeforeTax']=='0.377' and len(receipts)==1,'synthetic exact sum')
    proof['primary_event_components'][key]['combined_cash_per_original_share']='0.37444'
    try:project_components(raw,proof)
    except AssertionError:pass
    else:raise AssertionError('synthetic wrong cash sum accepted')
    print('Independent stdlib synthetic component sum/negative control passed; no actual sources read')


def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','repo-root','request','expected-request-sha256','source-dir','output','freeze-commit'):a.add_argument('--'+name)
    a.add_argument('--terminal-confirmed',action='store_true');a.add_argument('--self-test-only',action='store_true');args=a.parse_args(argv)
    if args.self_test_only:self_test();return 0
    check(args.terminal_confirmed,'actual compile terminal confirmation required')
    check(all(getattr(args,n.replace('-','_')) for n in ('source-root','repo-root','request','expected-request-sha256','source-dir','output','freeze-commit')),'complete bounded audit invocation')
    base,repo,root,out=map(lambda s:Path(s).resolve(),(args.source_root,args.repo_root,args.source_dir,args.output));check(root==base/OUTPUT and not out.exists() and not out.is_relative_to(base) and not out.is_relative_to(repo),'fixed source directory and external new audit output')
    p,watched,financial,expected,adjacent,packets,sessions=expected_projection(base,repo,Path(args.request).resolve(),args.expected_request_sha256,args.freeze_commit)
    summary=read(root/'summary.json');manifest=read(root/'manifest.json');check(manifest=={'summary_sha256':sha(root/'summary.json'),'projection_complete':True,'error':None},'source terminal manifest')
    check(summary['projection_complete'] is True and summary['error'] is None and summary['status']=='IVOL_PRE2026_SOURCE_EVENTS_COMPILED_INDEPENDENT_AUDIT_PENDING','successful source-only compile')
    check(summary['request_sha256']==args.expected_request_sha256 and summary['input_sha256']==watched and summary['old42_financial_sha256']==financial,'actual summary audited inputs consumed')
    check(set(summary['artifact_sha256'])==set(BODY),'exact6body artifacts plus summary and independent postcheck')
    hashes={'summary.json':sha(root/'summary.json')}
    for name in BODY:
        check(sha(root/name)==summary['artifact_sha256'][name],'actual source artifact hash');check(read(root/name)==expected[name],'independent event source semantic reconstruction '+name);hashes[name]=sha(root/name)
    post=read(root/'source-postcheck.json');check(post=={'all_bound_inputs_unchanged':True,'changed_inputs':{}} and sha(root/'source-postcheck.json')==summary['postcheck_sha256'],'source actual byte postcheck')
    for name,h in watched.items():check(sha(name)==h,'input unchanged after independent reconstruction')
    check(summary['raw_manifest_sha256']==sha(base/RAW/'manifest.json') and summary['primary_capture_manifest_sha256']==sha(base/PRIMARY/'manifest.json') and summary['target_sha256']==sha(base/DEVELOPMENT/'targets.json'),'summary actual raw/primary/target anchors')
    for k in ('source_packets_modified','source_admitted_for_account_replay','event_compilation_independently_verified','actual_lifecycle_flat_verified','strict_statutory_capital_tax_certification','actual_FIFO_tax_liability_verified','historical_arrival_verified','portfolio_returns_computed','new_2026_queries','objective_achieved'):check(summary[k] is False,'source boundary '+k)
    check(summary['source_names']==361 and summary['source_sessions']==486 and summary['monthly_targets']==24,'source scope summary')
    for k,v in expected['coverage_validation.json'].items():check(summary[k]==v,'coverage summary '+k)
    negatives=semantic_negative_controls(expected,packets,sessions)
    report={'status':'PASS_INDEPENDENT_PRE2026_EVENT_SOURCE_AUDIT','source_summary_sha256':sha(root/'summary.json'),'source_manifest_sha256':sha(root/'manifest.json'),'source_plan_sha256':args.expected_request_sha256,'source_artifact_sha256':hashes,'source_postcheck_sha256':sha(root/'source-postcheck.json'),'source_summary_body_artifact_sha256':summary['artifact_sha256'],'all862_events_independently_reconstructed':True,'all_source_receipts_independently_reconstructed':True,'coverage_independently_reconstructed':True,'six_unknown_tax_states_preserved':True,'known_tax_unknown_event_keys':sorted(UNKNOWN),'source_kind_counts':expected['coverage_validation.json']['source_kind_counts'],'inherited_original_proof_types':9,'inherited_proof_aliases':sum(len(r['aliases']) for r in expected['effective_proofs.json']['inherited_proof_receipts']),'primary_typed_components':2,'primary_cash_supplements':3,'primary_lifecycle_missing_sessions':361,'lifecycle_source_interval_records':len(expected['lifecycles.json']['source_intervals']),'adjacent_source_adjustment_explanations':adjacent,'old42_financial_sha256':financial,'all_bound_input_sha256':watched,'freeze_commit':subprocess.check_output(['git','rev-parse',args.freeze_commit],cwd=repo,text=True).strip(),'imports_project_code':False,'production_compiler_called':False,'audit_code_sha256':sha(__file__),'semantic_negative_controls_rejected':negatives,'negative_controls_use_hash_gate':False,'critical_or_important_findings':[],'account_replay_admitted':False,'portfolio_returns_computed':False,'2026_values_read':False,'network_used':False,'source_or_repository_modified_by_audit':False,'limitations':['Source/event reconstruction only; proof scope follows existing limited primary evidence and6unknown tax guards. No statutory tax upgrade or actualFIFO liability certification.','Lifecycle gaps/listing anchor are coverage-only and do not establish actual flat inventory or create prices/entitlements.','No account replay, intraday execution, historicalPIT arrival, investment promotion or portfolio/2026outcome validation.']}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'report':str(out),'report_sha256':sha(out),'audit_code_sha256':report['audit_code_sha256'],'source_summary_sha256':report['source_summary_sha256'],'events':862,'negative_controls':len(negatives)}));return 0
if __name__=='__main__':raise SystemExit(main())
