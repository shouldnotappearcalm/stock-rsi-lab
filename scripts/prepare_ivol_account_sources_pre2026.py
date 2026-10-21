"""Frozen pre2026 IVOL evaluator sources; no network, strategy or account replay.

Preflight authenticates bytes and builds proof objects only. Compilation is a
separate explicit post-freeze invocation. No lifecycle exception proves flat
inventory, and no unknown tax basis/exemption is granted by this projection.
"""
import argparse
import copy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler_v2 import CONTRACT as CASH_CONTRACT
from stock_rsi.primary_event_components import CONTRACT, compile_primary_event_components
from stock_rsi.lifecycle_source_rows import source_rows_on
from scripts.run_low_risk_raw_share_validation import validate_source_coverage

START, END = '2023-12-29', '2025-12-31'
CANDIDATE = 'low_market_residual_vol_1m'
RAW = 'low-market-residual-vol1m-raw-pre2026-20261021'
PRIMARY = 'low-market-residual-vol1m-primary-pre2026-20261021'
DEVELOPMENT = 'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
OUTPUT = 'low-market-residual-vol1m-account-source-events-pre2026-20261021'
STATUS = 'FROZEN_IVOL_PRE2026_SOURCE_EVENT_PROJECTION_NO_ROI'
PROTOCOL = 'docs/research/low-market-residual-vol1m-event-source-protocol-2026-10-21.md'
PREFIX = 'experiments/qlib/low-market-residual-vol1m-'
METHOD_FILES = ('scripts/prepare_ivol_account_sources_pre2026.py',
 'src/stock_rsi/primary_event_components.py', 'src/stock_rsi/distribution_event_compiler_v2.py',
 'src/stock_rsi/distribution_event_compiler.py', 'src/stock_rsi/lifecycle_source_rows.py',
 'scripts/run_low_risk_raw_share_validation.py', 'src/stock_rsi/stock_distribution_account.py',
 'src/stock_rsi/raw_share_account.py', 'src/stock_rsi/broker.py', 'src/stock_rsi/calendar.py',
 'src/stock_rsi/data.py', 'src/stock_rsi/models.py', 'src/stock_rsi/time.py')
PUBLIC_FILES = tuple(PREFIX+n+'.json' for n in (
 'raw-source-independent-audit', 'raw-source-verification', 'primary-source-capture-manifest',
 'primary-source-independent-audit', 'primary-source-verification',
 'primary-content-independent-review', 'primary-completion-proposal',
 'primary-completion-proposal-independent-check', 'primary-event-components-independent-review',
 'pre2026-corporate-cache-inventory')) + ('experiments/qlib/illiquidity-lifecycle-source-evidence.json',)
LOCAL_FILES = (RAW+'/manifest.json', RAW+'/calendar.json', DEVELOPMENT+'/targets.json',
 DEVELOPMENT+'/summary.json', PRIMARY+'/manifest.json',
 'price-delay-corporate-reviewed-20261021/reviewed-manifest.json',
 'low-beta60-corporate-reviewed-20261021/reviewed-manifest.json',
 'szse-value-momentum-account-sources-20261021/reviewed-manifest.json',
 'budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json',
 'illiquidity-corporate-reviewed-20261020/reviewed-manifest.json',
 'illiquidity-source-events-20261020/initial_listing_classification.json',
 'illiquidity-source-events-20261020/summary.json')
UNKNOWN = {'SH600580|2025-06-27', 'SH600763|2024-07-05', 'SH603290|2024-05-23',
 'SH603688|2024-05-22', 'SH603927|2024-05-21', 'SZ000403|2025-06-04'}
OLD_PROOFS = {('capital_tax', k) for k in ('SH600885|2025-06-19','SH600998|2024-06-07',
 'SH601128|2024-05-29','SH601128|2025-06-05','SZ002984|2024-04-19','SZ003031|2024-06-11')} | {
 ('stock_dividend_tax_bases','SH603826|2024-06-27'), ('cash_overrides','SZ001914|2025-08-13'),
 ('primary_cash_supplement','SZ002508|2024-01-10')}


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def bound_path(root, relative):
    root=Path(root).resolve(); value=Path(relative)
    if value.is_absolute() or not relative or '..' in value.parts:
        raise ValueError('relative contained source artifact required')
    result=(root/value).resolve()
    if not result.is_relative_to(root):raise ValueError('source path escapes registered root')
    return result


def authenticate(path, expected, watched):
    path=Path(path).resolve()
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected) or file_sha(path)!=expected:
        raise ValueError('frozen artifact bytes changed: '+str(path))
    key=str(path)
    if key in watched and watched[key]!=expected:raise ValueError('conflicting source hash binding')
    watched[key]=expected


def recheck_inputs(watched):
    for name,h in watched.items():
        if file_sha(name)!=h:raise ValueError('source mutated during projection: '+name)


def add_document(documents, doc):
    name=doc['file'];sha=doc['sha256']
    if (not isinstance(name,str) or Path(name).name!=name or '\\' in name
            or not re.fullmatch('[0-9a-f]{64}',sha)
            or not re.fullmatch('(SH|SZ)[0-9]{6}',doc['instrument'])
            or date.fromisoformat(doc['day']).isoformat()!=doc['day'] or doc['day']>END):
        raise ValueError('canonical pre-cutoff primary document identity required')
    prior=documents.get(name)
    if prior is not None:
        if any(prior[k]!=doc[k] for k in ('sha256','instrument','day')):
            raise ValueError('document filename/security/hash collision')
        return
    if any(d['sha256']==sha for d in documents.values()):raise ValueError('document SHA alias collision')
    documents[name]=copy.deepcopy(doc)


def event_key(row, code):
    return code+'|'+row['dividOperateDate']


def proof_economics(kind, proof):
    if kind=='primary_cash_supplement':
        r=proof['record']
        return (proof['instrument'], *(r[k] for k in ('dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate')),
                *(Decimal(r[k]) for k in ('dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs')))
    if kind=='capital_tax':return (proof.get('verified_exempt') is True,)
    if kind=='stock_dividend_tax_bases':
        return (proof.get('verified') is True,Decimal(proof['expected_stock_per_original_share']),Decimal(proof['taxable_income_per_original_share']))
    if kind=='cash_overrides':
        return (proof.get('verified') is True,proof['kind'],proof['source_row_sha256'],
                Decimal(proof['expected_vendor_cash_per_share']),Decimal(proof['effective_cash_per_share']))
    raise ValueError('unsupported inherited proof type')


def _literal(manifest, kind, key):
    if kind=='primary_cash_supplement':
        values=[s for s in manifest.get('supplementary_distributions',[]) if event_key(s['record'],s['instrument'])==key]
        if len(values)!=1:raise ValueError('unique original cached supplement required')
        return values[0]
    return manifest.get(kind,{}).get(key)


def build_effective_proofs(inventory, proposal, packets, read, auth):
    """Preserve first registered literal and all aliases; never compile here."""
    if any(proposal.get(f) for f in ('capital_tax','stock_dividend_tax_bases','cash_overrides','component_precision_overrides')):
        raise ValueError('new primary component proposal cannot grant tax/precision proofs')
    effective={'documents':[], 'capital_tax':{}, 'stock_dividend_tax_bases':{},
        'cash_override_contract':CASH_CONTRACT, 'cash_overrides':{},'supplementary_distributions':[],
        'primary_event_component_contract':CONTRACT,
        'primary_event_components':copy.deepcopy(proposal['primary_event_components'])}
    docs={};selected={};receipts=[]
    for index,c in enumerate(inventory['proof_candidates']):
        key,kind=c['event_key'],c['proof_type'];identity=(kind,key)
        auth(c['reviewed_manifest'],c['reviewed_manifest_sha256']);manifest=read(c['reviewed_manifest'])
        literal=_literal(manifest,kind,key)
        if literal!=c['proof_literal']:raise ValueError('cached proof literal changed')
        auth(c['pdf_path'],c['pdf_sha256'])
        matches=[d for d in manifest['documents'] if d['file']==literal['source_file']]
        if len(matches)!=1:raise ValueError('cached proof document metadata missing or duplicate')
        doc=matches[0];code,ex=key.split('|')
        if (doc['sha256']!=literal['source_sha256'] or doc['sha256']!=c['pdf_sha256']
                or doc['instrument']!=code or Path(c['pdf_path']).name!=doc['file']):
            raise ValueError('cached original PDF/issuer/filename chain differs')
        rows=[r for r in packets[code]['distributions'] if r['dividOperateDate']==ex]
        if kind=='primary_cash_supplement':
            if rows:raise ValueError('supplement duplicates original vendor event')
            if doc['day']!=literal['record']['dividPlanDate']:raise ValueError('supplement announcement mismatch')
        elif len(rows)!=1 or rows[0]['dividPlanDate']!=doc['day']:
            raise ValueError('cached proof not bound to one current original vendor row')
        elif kind=='capital_tax' and (Decimal(rows[0]['dividReserveToStockPs'])<=0 or literal.get('verified_exempt') is not True):
            raise ValueError('capital proof must remain applicable to positive original capital')
        elif kind=='stock_dividend_tax_bases' and Decimal(rows[0]['dividStocksPs'])!=Decimal(literal['expected_stock_per_original_share']):
            raise ValueError('stock proof ratio differs from original row')
        elif kind=='cash_overrides' and literal['source_row_sha256']!=digest(rows[0]):
            raise ValueError('cash precision original row hash changed')
        alias={'inventory_index':index,'reviewed_manifest':c['reviewed_manifest'],
            'reviewed_manifest_sha256':c['reviewed_manifest_sha256'],'pdf_path':c['pdf_path'],
            'pdf_sha256':c['pdf_sha256'],'proof_literal_sha256':digest(literal)}
        if identity in selected:
            prior=selected[identity]
            if proof_economics(kind,literal)!=proof_economics(kind,prior['literal']):
                raise ValueError('registered aliases disagree economically')
            prior['receipt']['aliases'].append(alias);continue
        add_document(docs,doc)
        receipt={'event_key':key,'proof_type':kind,'chosen_inventory_index':index,
            'chosen_original_proof_literal_sha256':digest(literal),'aliases':[alias],
            'actual_zero_ownership_proof_transferred':False,'tax_evidence_scope_strengthened':False}
        selected[identity]={'literal':copy.deepcopy(literal),'receipt':receipt};receipts.append(receipt)
        if kind=='primary_cash_supplement':effective['supplementary_distributions'].append(copy.deepcopy(literal))
        else:effective[kind][key]=copy.deepcopy(literal)
    for doc in proposal['documents']:add_document(docs,doc)
    for supplement in proposal['supplementary_distributions']:
        code=supplement['instrument'];ex=supplement['record']['dividOperateDate']
        if any(r['dividOperateDate']==ex for r in packets[code]['distributions']):
            raise ValueError('new supplement duplicates vendor distribution')
        if any(event_key(s['record'],s['instrument'])==code+'|'+ex for s in effective['supplementary_distributions']):
            raise ValueError('duplicate primary supplement')
        effective['supplementary_distributions'].append(copy.deepcopy(supplement))
    effective['documents']=list(docs.values())
    effective.update(status='IVOL_EVALUATOR_PROOFS_NO_ACCOUNT_ADMISSION',inherited_proof_receipts=receipts,
        strict_statutory_capital_tax_certification=False, actual_zero_ownership_verified=False,
        source_admitted_for_account_replay=False,portfolio_returns_computed=False)
    return effective,receipts


def _zero_findings(value):
    return type(value) is int and value==0 or type(value) is list and not value


def _evidence_path(path, base, repo):
    p=Path(path).resolve()
    if not (p.is_relative_to(base) or p.is_relative_to(repo)):
        raise ValueError('evidence outside registered source/repository roots')
    return p


def load_inputs(source_root, repo_root, request_path, expected_request_sha256):
    base=Path(source_root).resolve();repo=Path(repo_root).resolve();watched={}
    auth=lambda path,h:authenticate(_evidence_path(path,base,repo),h,watched)
    # Request may be a temporary draft during source-only preflight.
    authenticate(request_path,expected_request_sha256,watched);request=read_json(request_path)
    if (request.get('status')!=STATUS or request.get('candidate')!=CANDIDATE or request.get('window')!=[START,END]
            or request.get('output_relative')!=OUTPUT or request.get('portfolio_returns_to_compute') is not False
            or request.get('new_2026_queries_allowed') is not False):raise ValueError('frozen pre2026 projection scope changed')
    if request.get('protocol_file')!=PROTOCOL:raise ValueError('fixed source protocol required')
    auth(bound_path(repo,PROTOCOL),request['protocol_sha256'])
    for field,names,root in (('method_code_sha256',METHOD_FILES,repo),
            ('public_evidence_sha256',PUBLIC_FILES,repo),('local_source_sha256',LOCAL_FILES,base)):
        if set(request[field])!=set(names):raise ValueError('exact frozen method/public/local input maps required')
        for name,h in request[field].items():auth(bound_path(root,name),h)
    public=lambda n:read_json(repo/(PREFIX+n+'.json'))
    raw=base/RAW;primary=base/PRIMARY;manifest=read_json(raw/'manifest.json');rawsha=file_sha(raw/'manifest.json')
    raw_audit=public('raw-source-independent-audit');primary_audit=public('primary-source-independent-audit')
    if (raw_audit['status']!='PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT' or raw_audit['manifest_sha256']!=rawsha
            or raw_audit['capture_complete'] is not True or raw_audit['complete_packets_saved']!=361
            or not _zero_findings(raw_audit['critical_or_important_findings'])
            or manifest['capture_complete'] is not True or manifest['errors_sha256'] or manifest['pending_codes']):
        raise ValueError('successful independent raw source capture authentication required')
    for name,h in raw_audit['whole_capture_tree_sha256'].items():auth(bound_path(raw,name),h)
    financial=raw_audit['old42_financial_sha256']
    if len(financial)!=42:raise ValueError('all42 immutable financial files required')
    summary=read_json(base/DEVELOPMENT/'summary.json')
    summary_financial={case+'/'+name:h for case,v in summary['results_by_extra_bps_and_family'].items()
        for name,h in v['artifact_sha256'].items()}
    if summary_financial!=financial:
        raise ValueError('old financial summary does not bind original42 file hashes')
    for name,h in financial.items():auth(bound_path(base/DEVELOPMENT,name),h)
    sessions=read_json(raw/'calendar.json')['sessions'];targetpath=base/DEVELOPMENT/'targets.json'
    if (len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=[START,END]
            or file_sha(raw/'calendar.json')!=manifest['calendar_sha256']
            or file_sha(targetpath)!=manifest['target_sha256']):raise ValueError('frozen explicit calendar/target changed')
    targets=read_json(targetpath)[CANDIDATE];codes=sorted({c for t in targets.values() for c in t['weights']})
    if (len(targets)!=24 or len(codes)!=361 or set(codes)!=set(manifest['per_code_sha256'])
            or raw_audit['packet_sha256']!=manifest['per_code_sha256']
            or any(day not in sessions or t['as_of'] not in sessions or t['as_of']>=day for day,t in targets.items())):
        raise ValueError('fixed24 formation/361 instrument identity changed')
    packets={}
    for code,h in manifest['per_code_sha256'].items():
        path=raw/'codes'/(code+'.json');auth(path,h);packet=read_json(path)
        days=[r['date'] for r in packet['bars']]
        if (packet['instrument']!=code or packet['window']!=[START,END] or days!=sorted(set(days))
                or not set(days)<=set(sessions)
                or any(not START<=r['dividOperateDate']<=END for f in ('distributions','adjustments') for r in packet[f])):
            raise ValueError('original source issuer/window/calendar changed')
        packets[code]=packet
    if sum(len(p['distributions']) for p in packets.values())!=860 or sum(len(p['adjustments']) for p in packets.values())!=875:
        raise ValueError('original vendor distribution/adjustment counts changed')
    pmanifest=read_json(primary/'manifest.json');pmsha=file_sha(primary/'manifest.json')
    if (primary_audit['status']!='PASS_INDEPENDENT_EIGHT_PRIMARY_CAPTURE_AUDIT'
            or primary_audit['manifest_sha256']!=pmsha or primary_audit['capture_complete'] is not True
            or primary_audit['accepted_documents']!=8 or primary_audit['all42_old_financial_files_and_original_target_byte_unchanged'] is not True
            or not _zero_findings(primary_audit['critical_or_important_findings'])):
        raise ValueError('independent8 original primary source audit required')
    for name,h in primary_audit['artifact_sha256'].items():auth(bound_path(primary,name),h)
    proposal=public('primary-completion-proposal');check=public('primary-completion-proposal-independent-check')
    review=public('primary-content-independent-review');inventory=public('pre2026-corporate-cache-inventory')
    if (check['status']!='PASS_INDEPENDENT_LITERAL_PRIMARY_COMPLETION_PROPOSAL_CHECK_NOT_APPLIED'
            or check['proposal_sha256']!=file_sha(repo/(PREFIX+'primary-completion-proposal.json'))
            or check['primary_content_review_sha256']!=file_sha(repo/(PREFIX+'primary-content-independent-review.json'))
            or check['primary_capture_manifest_sha256']!=pmsha or check['original_raw_manifest_sha256']!=rawsha
            or check['critical_findings'] or check['important_findings'] or check['findings']
            or check['two_typed_components_match_review_and_original_rows'] is not True
            or check['new_tax_maps_empty'] is not True or set(check['six_tax_unknown_event_keys_retained'])!=UNKNOWN
            or proposal['primary_capture_manifest_sha256']!=pmsha
            or proposal['primary_content_review_sha256']!=check['primary_content_review_sha256']
            or review['capture_manifest_sha256']!=pmsha or review['documents_reviewed']!=8
            or inventory['target_sha256']!=manifest['target_sha256']):
        raise ValueError('canonical reviewed primary content/proposal/independent check unbound')
    for doc in proposal['documents']:
        auth(primary/doc['file'],doc['sha256']);entry=pmanifest['documents'][doc['original_manifest_case_id']]
        case=review['cases'][doc['original_manifest_case_id']]
        if any(entry[k]!=doc[k] for k in ('file','sha256','instrument')) or case['pdf_sha256']!=doc['sha256']:
            raise ValueError('original8 PDF metadata/content chain changed')
    for code,binding in check['original_raw_packet_bindings'].items():auth(raw/'codes'/(code+'.json'),binding['sha256'])
    effective,inheritance=build_effective_proofs(inventory,proposal,packets,read_json,auth)
    if {(r['proof_type'],r['event_key']) for r in inheritance}!=OLD_PROOFS:
        raise ValueError('exact9 inherited proof types required')
    if (len(effective['capital_tax'])!=6 or len(effective['stock_dividend_tax_bases'])!=1
            or len(effective['cash_overrides'])!=1 or len(effective['supplementary_distributions'])!=3
            or len(effective['primary_event_components'])!=2
            or UNKNOWN & (set(effective['capital_tax'])|set(effective['stock_dividend_tax_bases']))):
        raise ValueError('reviewed economic/tax proof scope changed')
    # Preserve primary lifecycle literals, independently authenticate their PDFs.
    lifecycles={};docs={d['file']:copy.deepcopy(d) for d in effective['documents']}
    for candidate in inventory['lifecycle_candidates']:
        auth(candidate['reviewed_manifest'],candidate['reviewed_manifest_sha256'])
        old=read_json(candidate['reviewed_manifest']);code=candidate['instrument'];proof=candidate['proof_literal']
        if old['lifecycles'].get(code)!=proof:raise ValueError('original lifecycle literal changed')
        auth(candidate['pdf_path'],proof['primary_document_sha256'])
        doc=next(d for d in old['documents'] if d['file']==proof['source_file'])
        if doc['instrument']!=code or doc['sha256']!=proof['primary_document_sha256']:
            raise ValueError('lifecycle PDF issuer/identity mismatch')
        add_document(docs,doc);lifecycles[code]=copy.deepcopy(proof)
    expected={'SH603341':('LISTING_BEGIN','2024-03-01',38),'SZ002505':('DELISTING_END','2024-08-30',323)}
    if set(lifecycles)!=set(expected):raise ValueError('exact two original lifecycle boundaries required')
    for code,packet in packets.items():
        days=[r['date'] for r in packet['bars']];missing=[d for d in sessions if d not in set(days)]
        if code not in expected:
            if missing:raise ValueError('unexpected source calendar gap: '+code)
            continue
        kind,boundary,count=expected[code];proof=lifecycles[code]
        allowed=[d for d in sessions if (d<boundary if kind=='LISTING_BEGIN' else d>boundary)]
        if (proof['kind']!=kind or proof['effective_date']!=boundary or proof['verified_primary_boundary'] is not True
                or missing!=allowed or len(missing)!=count):raise ValueError('lifecycle source gap differs from exact primary boundary')
    initialpath=base/'illiquidity-source-events-20261020/initial_listing_classification.json'
    prior=read_json(base/'illiquidity-source-events-20261020/summary.json')
    auth(initialpath,prior['artifact_sha256']['initial_listing_classification.json']);initial=read_json(initialpath)
    if file_sha(initialpath)!='ce202a33cf791b0047db3ced19ae7ddf3e450606fd9d49da391545dd2f1d6c57' or len(initial)!=1:
        raise ValueError('original listing classification anchor changed')
    effective['documents']=list(docs.values());effective['lifecycles']=copy.deepcopy(lifecycles)
    recheck_inputs(watched)
    return {'packets':packets,'effective_proofs':effective,'lifecycles':lifecycles,
        'initial_listing_classification':initial,'calendar':TradingCalendar(sessions),'sessions':sessions,
        'targets':targets,'input_sha256':watched,'request':request,'request_sha256':expected_request_sha256,
        'raw_manifest_sha256':rawsha,'primary_capture_manifest_sha256':pmsha,
        'target_sha256':manifest['target_sha256'],'old42_financial_sha256':financial}


def coverage_view(packets, events, initial, lifecycles):
    view=copy.deepcopy(packets)
    for code,p in view.items():
        p['distributions']=[{'dividOperateDate':e.ex_date.isoformat()} for e in events if e.instrument==code]
    for item in initial:
        code=item['instrument'];proof=lifecycles[code];row=item['source_adjustment'];day=item['effective_date']
        matches=[r for r in view[code]['adjustments'] if r['dividOperateDate']==day]
        if (item['classification']!='INITIAL_LISTING_NORMALIZATION_NOT_DISTRIBUTION'
                or item['factor_used_to_infer_cash_or_shares'] is not False
                or proof['kind']!='LISTING_BEGIN' or proof['effective_date']!=day
                or proof['primary_document_sha256']!=item['primary_document_sha256']
                or view[code]['bars'][0]['date']!=day or matches!=[row]
                or Decimal(row['backAdjustFactor'])!=1 or Decimal(row['adjustFactor'])!=1
                or Decimal(row['foreAdjustFactor'])<=0
                or any(e.instrument==code and e.ex_date.isoformat()==day for e in events)):
            raise ValueError('initial listing normalization not separately supported')
        view[code]['adjustments']=[r for r in view[code]['adjustments'] if r!=row]
    return view


def validate_compiled(events, receipts, packets, *, expected_count=862, expected_unknown=UNKNOWN):
    if (len(events)!=expected_count or len(receipts)!=len(events)
            or len({e.event_id for e in events})!=len(events)
            or any(r['event_id']!=e.event_id or r['instrument']!=e.instrument
                or r['ex_date']!=e.ex_date.isoformat() for e,r in zip(events,receipts))):
        raise ValueError('complete unique paired event/receipt identities required')
    unknown={e.instrument+'|'+e.ex_date.isoformat() for e in events
        if e.stock_per_share>0 and not e.stock_tax_basis_verified or e.capital_per_share>0 and not e.capital_tax_exempt_verified}
    receipt_unknown={r['instrument']+'|'+r['ex_date'] for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']}
    if unknown!=set(expected_unknown) or receipt_unknown!=unknown:
        raise ValueError('exact original six unknown tax guards required')
    if sum(e.capital_tax_exempt_verified for e in events)!=6 or sum(e.stock_tax_basis_verified for e in events)!=1:
        raise ValueError('inherited tax flags changed')


def compile_inputs(inputs):
    """Post-freeze only; no source queries, strategies, prices or account replay."""
    packets=inputs['packets'];before=digest(packets)
    events,receipts=compile_primary_event_components(packets,inputs['effective_proofs'],inputs['calendar'])
    validate_compiled(events,receipts,packets)
    view=coverage_view(packets,events,inputs['initial_listing_classification'],inputs['lifecycles'])
    validate_source_coverage(view)
    bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()};exceptions=[]
    for day in inputs['calendar'].days:
        _,records=source_rows_on(bars,day,(),inputs['lifecycles']);exceptions.extend(records)
    if sum(not r['original_row_present'] for r in exceptions)!=361 or digest(packets)!=before:
        raise ValueError('source rows mutated or lifecycle gaps changed')
    kinds={k:sum(r['source_kind']==k for r in receipts) for k in sorted({r['source_kind'] for r in receipts})}
    return {'effective_proofs.json':inputs['effective_proofs'],'derived_events.json':[asdict(e) for e in events],
        'event_source_receipts.json':list(receipts),
        'lifecycles.json':{'boundaries':inputs['lifecycles'],'source_intervals':exceptions,
            'actual_flat_inventory_verified':False,'missing_rows_filled':False},
        'initial_listing_classification.json':inputs['initial_listing_classification'],
        'coverage_validation.json':{'compiled_event_count':len(events),'source_kind_counts':kinds,
            'known_tax_unknown_event_keys':sorted(UNKNOWN),'coverage_validated_on_copy':True,
            'original_source_packets_modified':False,'initial_listing_normalizations':1,
            'source_gap_sessions':361,'actual_lifecycle_flat_verified':False,
            'factor_values_used_to_infer_entitlements':False,'historical_arrival_verified':False,
            'source_admitted_for_account_replay':False,'portfolio_returns_computed':False}}


def _write(path, value):
    def encode(v):
        if isinstance(v,(date,Decimal)):return str(v)
        raise TypeError('unsupported source artifact type')
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False,default=encode);stream.write('\n')


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('source-root','request','expected-request-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--repo-root',default=str(Path(__file__).resolve().parents[1]));p.add_argument('--output-dir')
    p.add_argument('--source-preflight-only',action='store_true');a=p.parse_args(argv)
    out=Path(a.source_root).resolve()/OUTPUT
    if a.output_dir and Path(a.output_dir).resolve()!=out:raise ValueError('fixed new output directory required')
    if out.exists():raise ValueError('preserve existing projection; no resume/overwrite')
    inputs=load_inputs(a.source_root,a.repo_root,a.request,a.expected_request_sha256)
    recheck_inputs(inputs['input_sha256'])
    if a.source_preflight_only:
        print('source-only authentication/proof preflight complete; compiler not called; no output written',flush=True);return 0
    out.mkdir();artifacts={};error=None
    try:
        for name,value in compile_inputs(inputs).items():_write(out/name,value);artifacts[name]=file_sha(out/name)
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)}
        _write(out/'error.json',error)
    finally:
        changed={}
        for name,h in inputs['input_sha256'].items():
            try:unchanged=file_sha(name)==h
            except OSError:unchanged=False
            if not unchanged:changed[name]=h
        post={'all_bound_inputs_unchanged':not changed,'changed_inputs':changed}
        _write(out/'source-postcheck.json',post)
        complete=error is None and not changed
        summary={'status':'IVOL_PRE2026_SOURCE_EVENTS_COMPILED_INDEPENDENT_AUDIT_PENDING' if complete else 'IVOL_SOURCE_PROJECTION_FAILED_PRESERVED',
            'request_sha256':inputs['request_sha256'],'raw_manifest_sha256':inputs['raw_manifest_sha256'],
            'primary_capture_manifest_sha256':inputs['primary_capture_manifest_sha256'],'target_sha256':inputs['target_sha256'],
            'input_sha256':inputs['input_sha256'],'artifact_sha256':artifacts,'postcheck_sha256':file_sha(out/'source-postcheck.json'),
            'projection_complete':complete,'error':error,'source_names':361,'source_sessions':486,'monthly_targets':24,
            'old42_financial_sha256':inputs['old42_financial_sha256'],'source_packets_modified':False,
            'source_admitted_for_account_replay':False,'event_compilation_independently_verified':False,
            'actual_lifecycle_flat_verified':False,'strict_statutory_capital_tax_certification':False,
            'actual_FIFO_tax_liability_verified':False,'historical_arrival_verified':False,
            'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
        if 'coverage_validation.json' in artifacts:summary.update(read_json(out/'coverage_validation.json'))
        _write(out/'summary.json',summary);_write(out/'manifest.json',{'summary_sha256':file_sha(out/'summary.json'),'projection_complete':complete,'error':error})
    if error is not None or changed:raise ValueError('source projection failed; error/postcheck/manifest preserved')
    print('862 source events compiled; no account admission or portfolio returns',flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
