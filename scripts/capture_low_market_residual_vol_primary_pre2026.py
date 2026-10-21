"""Eight frozen pre2026 implementation notices: source bytes, never admission.

Only the existing bounded CNINFO query/immutable HTTP journal handles transport.
A fresh directory is required; failure, interruption and postcheck are terminal.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.audit_cninfo_report_admission import CNINFO, publication_date, query
from scripts.capture_budgeted_corporate_notices_pre2026 import journaled_bytes, read_wire
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json, sha256_file
from scripts.fundamental_query_journal import QueryJournal, write_packet_once

RAW = 'low-market-residual-vol1m-raw-pre2026-20261021'
OUTPUT = 'low-market-residual-vol1m-primary-pre2026-20261021'
PROTOCOL = 'docs/research/low-market-residual-vol1m-primary-source-plan-2026-10-21.md'
PUBLIC_FILES = (
    'experiments/qlib/low-market-residual-vol1m-raw-source-independent-audit.json',
    'experiments/qlib/low-market-residual-vol1m-raw-source-capture-manifest.json',
    'experiments/qlib/low-market-residual-vol1m-pre2026-corporate-questions.json',
)
LOCAL_FILES = (RAW+'/manifest.json', 'cninfo-csi500-reports-20261017/plan.json')
METHOD_FILES = (
    'scripts/capture_low_market_residual_vol_primary_pre2026.py',
    'scripts/capture_budgeted_corporate_notices_pre2026.py',
    'scripts/audit_cninfo_report_admission.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py',
    'scripts/fundamental_query_journal.py',
)
CASE_SCOPE = (
    ('SH600763', '2024-07-01', '2024-07-05', 'NONCASH'),
    ('SH603290', '2024-05-16', '2024-05-23', 'NONCASH'),
    ('SH603688', '2024-05-16', '2024-05-22', 'NONCASH'),
    ('SH603927', '2024-05-15', '2024-05-21', 'NONCASH'),
    ('SZ000403', '2025-05-27', '2025-06-04', 'NONCASH'),
    ('SH601966', '2024-06-07', '2024-06-14', 'CONFLICTING_CASH_ROWS'),
    ('SH601966', '2025-10-16', '2025-10-23', 'MISSING_CASH_SOURCE_QUESTION'),
    ('SZ000728', '2025-01-14', '2025-01-21', 'MISSING_CASH_SOURCE_QUESTION'),
)


def read(path):
    return json.loads(Path(path).read_bytes())


def safe(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('source path must stay inside its registered root')
    result = (Path(root)/path).resolve()
    if not result.is_relative_to(Path(root).resolve()):
        raise ValueError('source symlink escaped registered root')
    return result


def verify_inputs(known):
    for name, expected in known.items():
        if not Path(name).is_file() or sha256_file(name) != expected:
            raise ValueError('immutable input changed: '+name)


def check_scope(request):
    fixed = {
        'status': 'FROZEN_LOW_MARKET_RESIDUAL_VOL1M_EIGHT_PRIMARY_PRE2026',
        'candidate': 'low_market_residual_vol_1m',
        'window': ['2023-12-29', '2025-12-31'],
        'protocol_file': PROTOCOL, 'output_relative': OUTPUT,
        'maximum_http_query_reservations': 24, 'max_pages_per_exact_day': 2,
        'max_attempts_per_identity': 1, 'minimum_interval_seconds': .3,
        'maximum_consecutive_failed_cases': 3,
    }
    if any(type(request.get(k)) is not type(v) or request[k] != v for k,v in fixed.items()):
        raise ValueError('fixed eight-case primary protocol changed')
    for field, expected in (('method_code_sha256',METHOD_FILES),
                            ('public_evidence_sha256',PUBLIC_FILES),
                            ('local_source_sha256',LOCAL_FILES)):
        if set(request[field]) != set(expected):
            raise ValueError('complete exact source/method binding set required')
    scope = [(c['instrument'],c['publication_day'],c['ex_date'],c['kind']) for c in request['cases']]
    if scope != list(CASE_SCOPE):
        raise ValueError('exact ordered eight primary questions required')


def build_source_cases(packets, orgs, *, packet_hashes=None):
    """Preserve conflicting rows; a reference-price gap never becomes cash."""
    cases = []
    for code, pub, ex, kind in CASE_SCOPE:
        packet = packets[code]
        if packet['instrument'] != code or packet['window'] != ['2023-12-29','2025-12-31']:
            raise ValueError('case packet issuer/window changed')
        organization = orgs[code]
        if not isinstance(organization,str) or not re.fullmatch('[A-Za-z0-9]+',organization):
            raise ValueError('registered issuer organization required')
        rows = [r for r in packet['distributions'] if r['dividOperateDate']==ex]
        adjustments = [r for r in packet['adjustments'] if r['dividOperateDate']==ex]
        if len(adjustments)!=1 or any(r['code'] != code[:2].lower()+'.'+code[2:] for r in rows+adjustments):
            raise ValueError('source adjustment identity missing or ambiguous')
        if kind == 'NONCASH':
            if (len(rows)!=1 or rows[0]['dividPlanDate']!=pub
                    or sum(Decimal(rows[0][k] or '0') for k in ('dividStocksPs','dividReserveToStockPs'))<=0):
                raise ValueError('one original noncash row and publication required')
        elif kind == 'CONFLICTING_CASH_ROWS':
            if (len(rows)!=2 or any(r['dividPlanDate']!=pub for r in rows)
                    or {r['dividCashPsBeforeTax'] for r in rows}!={'0.286','0.091'}
                    or any(Decimal(r[k] or '0')!=0 for r in rows for k in ('dividStocksPs','dividReserveToStockPs'))):
                raise ValueError('both conflicting original cash rows must remain literal')
        elif rows:
            raise ValueError('missing-cash question already has a vendor row')
        bars = packet['bars'];days = [r['date'] for r in bars]
        if days!=sorted(set(days)) or any(not '2023-12-29'<=d<='2025-12-31' for d in days):
            raise ValueError('unique bounded source bar dates required')
        if ex not in days or days.index(ex)==0:
            raise ValueError('source reference pair required')
        pair = bars[days.index(ex)-1:days.index(ex)+1]
        if any(r['code']!=code[:2].lower()+'.'+code[2:] or r['adjustflag']!='3' for r in pair):
            raise ValueError('raw reference issuer/units changed')
        if kind == 'MISSING_CASH_SOURCE_QUESTION':
            if (any(r['tradestatus']!='1' for r in pair)
                    or abs(Decimal(pair[0]['close'])-Decimal(pair[1]['preclose']))<=Decimal('.005')):
                raise ValueError('missing cash query requires actual traded reference gap')
        case = dict(case_id=code+'|'+ex,instrument=code,publication_day=pub,ex_date=ex,
                    kind=kind,organization_id=organization,source_distributions=rows,
                    source_adjustments=adjustments,reference_gap_bars=pair)
        if packet_hashes is not None:case['source_packet_sha256']=packet_hashes[code]
        cases.append(case)
    return cases


def bind_financial_inputs(source, audit, target_sha):
    """Hash-only preservation of the old target and six cases; never read ROI."""
    root=Path(source)/'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
    expected={f'{extra}/{family}/{name}' for extra in (20,40)
        for family in ('eligible_equal_weight','low_total_vol_1m_control','low_market_residual_vol_1m')
        for name in ('days.csv','decision_intents.json','holdings.csv','orders.csv',
                     'positions.pkl','report.pkl','suspension_mark_audit.json')}
    mapping=audit['old42_financial_sha256']
    if set(mapping)!=expected:raise ValueError('exact42 old financial artifacts required')
    known={str(safe(root,n)):h for n,h in mapping.items()}
    known[str(safe(root,'targets.json'))]=target_sha
    verify_inputs(known)
    return known


def load_inputs(repo, source, request):
    repo, source = Path(repo).resolve(), Path(source).resolve()
    check_scope(request);known={}
    def bind(path, expected):
        if sha256_file(path)!=expected:raise ValueError('frozen input checksum changed: '+str(path))
        known[str(path)]=expected
    for field, root in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',source)):
        for relative, expected in request[field].items():bind(safe(root,relative),expected)
    bind(safe(repo,PROTOCOL),request['protocol_sha256'])
    manifest=read(source/LOCAL_FILES[0]);audit=read(repo/PUBLIC_FILES[0]);questions=read(repo/PUBLIC_FILES[2])
    manifest_sha=request['local_source_sha256'][LOCAL_FILES[0]]
    if ((repo/PUBLIC_FILES[1]).read_bytes()!=(source/LOCAL_FILES[0]).read_bytes()
            or audit['status']!='PASS_INDEPENDENT_SOURCE_CAPTURE_AUDIT'
            or audit['manifest_sha256']!=manifest_sha or audit['capture_complete'] is not True
            or audit['critical_or_important_findings']
            or manifest['status']!='LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE'
            or manifest['capture_complete'] is not True or manifest['errors_sha256'] or manifest['pending_codes']
            or manifest['abnormal_exit'] is not None or manifest['names']!=361
            or manifest['query_reservations_consumed']!=240 or manifest['window']!=['2023-12-29','2025-12-31']
            or len(manifest['per_code_sha256'])!=361 or manifest['per_code_sha256']!=audit['packet_sha256']
            or questions['manifest_sha256']!=manifest_sha
            or questions['source_audit']['sha256']!=request['public_evidence_sha256'][PUBLIC_FILES[0]]
            or questions['raw_request_sha256']!=manifest['request_sha256']
            or questions['counts']['authenticated_packets']!=361):
        raise ValueError('actual terminal sources/audit/questions not bound')
    known.update(bind_financial_inputs(source,audit,manifest['target_sha256']))
    # All raw packet bytes are immutable, not just the seven queried issuers.
    packets={}
    for code,h in manifest['per_code_sha256'].items():
        if not re.fullmatch('(SH|SZ)[0-9]{6}',code):raise ValueError('unsafe issuer code')
        path=source/RAW/'codes'/(code+'.json');bind(path,h)
        if code in {c[0] for c in CASE_SCOPE}:packets[code]=read(path)
    bind(source/RAW/'calendar.json',manifest['calendar_sha256'])
    sessions=read(source/RAW/'calendar.json')['sessions']
    if len(sessions)!=486 or sessions!=sorted(set(sessions)) or sessions[0]!='2023-12-29' or sessions[-1]!='2025-12-31':
        raise ValueError('explicit pre2026 calendar required')
    orgs=read(source/LOCAL_FILES[1])['org_by_code']
    cases=build_source_cases(packets,orgs,packet_hashes=manifest['per_code_sha256'])
    if request['cases']!=cases:raise ValueError('source rows/bar pairs/org mapping changed')
    for case in cases:
        key=case['case_id'];code=case['instrument'];ex=case['ex_date']
        if case['kind']=='NONCASH':
            matches=[r for r in questions['noncash_vendor_events'] if r['event_key']==key]
            if (len(matches)!=1 or matches[0]['vendor_row']!=case['source_distributions'][0]
                    or matches[0]['packet_sha256']!=case['source_packet_sha256']
                    or key not in questions['noncash_missing_event_specific_tax_or_basis']):
                raise ValueError('noncash question and literal source disagree')
        elif case['kind']=='CONFLICTING_CASH_ROWS':
            matches=[r for r in questions['duplicate_vendor_event_groups'] if r['event_key']==key]
            if len(matches)!=1 or [r['vendor_row'] for r in matches[0]['raw_rows']]!=case['source_distributions']:
                raise ValueError('both duplicate source rows required by original question')
        else:
            matches=[r for r in questions['contiguous_traded_preclose_anomalies'] if r['instrument']==code and r['day']==ex]
            pair=case['reference_gap_bars'];index=sessions.index(ex)
            if (len(matches)!=1 or pair[0]['date']!=sessions[index-1]
                    or [matches[0]['previous_bar'],matches[0]['current_bar']]!=pair
                    or matches[0]['packet_sha256']!=case['source_packet_sha256']
                    or matches[0]['same_date_vendor_event'] is not False
                    or matches[0]['cash_not_derived_from_difference'] is not True):
                raise ValueError('missing cash reference question not source-confirmed')
    verify_inputs(known)
    return {'known_hashes':known,'cases':cases}


def select_implementation_notice(rows, case):
    day=case['publication_day'];code=case['instrument'][2:]
    if not '2024-01-01'<=day<='2025-12-31' or date.fromisoformat(day).isoformat()!=day:
        raise ValueError('pre2026 exact publication date required')
    matches=[]
    for row in rows:
        if row['code']!=code or row['day']!=day:raise ValueError('listing issuer/publication changed')
        title=re.sub(r'<[^>]*>','',row['title']).strip()
        if (re.search(r'(?:权益分派|利润分配)实施(?:的)?公告$',title)
                and not re.search('预案|更正|补充|提示|摘要|取消',title)):
            matches.append(row)
    if len(matches)!=1:raise ValueError('one unique original implementation notice required')
    row=matches[0];identifier=row['announcement_id']
    if (not isinstance(identifier,str) or not re.fullmatch('[0-9]+',identifier)
            or not isinstance(row['pdf_path'],str)
            or row['pdf_path'].lower()!=('finalpage/'+day+'/'+identifier+'.PDF').lower()):
        raise ValueError('canonical issuer/day/announcement PDF path required')
    return row


def validate_listing(data, case, page, previous_total):
    total=data.get('totalAnnouncement') if isinstance(data,dict) else None
    rows=data.get('announcements') if isinstance(data,dict) else None
    if type(total) is not int or not 0<=total<=60 or page not in (1,2):
        raise ValueError('bounded typed listing count required')
    if total==0 and rows is None:rows=[]
    expected=max(0,min(30,total-(page-1)*30))
    if (not isinstance(rows,list) or len(rows)!=expected
            or previous_total is not None and previous_total!=total):
        raise ValueError('complete stable listing pages required')
    for row in rows:
        if (row['secCode']!=case['instrument'][2:] or type(row['announcementTime']) is not int
                or publication_date(row['announcementTime'])!=case['publication_day']):
            raise ValueError('listing returned another issuer/publication')
    return total


def capture(request, auth, out, fetch, *, request_bytes, request_sha):
    out=Path(out)
    if out.exists() or out.is_symlink():raise ValueError('existing source capture immutable; no resume')
    verify_inputs(auth['known_hashes'])
    if auth['cases']!=request['cases']:raise ValueError('authenticated cases changed')
    # Enforce the same fixed transport budget even for an injected transport.
    if (request['maximum_http_query_reservations']!=24 or request['max_attempts_per_identity']!=1
            or request['max_pages_per_exact_day']!=2 or request['minimum_interval_seconds']!=.3
            or request['maximum_consecutive_failed_cases']!=3 or len(request['cases'])!=8):
        raise ValueError('fixed primary transport budget required')
    out.mkdir(parents=True);documents={};errors={};terminal=None;post=None;next_request=0.
    ids=[c['case_id'] for c in auth['cases']]
    try:
        (out/'request.json').write_bytes(request_bytes);atomic_json(out/'input-before.json',auth['known_hashes'])
        atomic_json(out/'progress.json',documents);atomic_json(out/'errors.json',errors)
        journal=QueryJournal(out,max_queries=24,max_attempts=1);consecutive=0
        for case in auth['cases']:
            key=case['case_id'];selected_url=None;pages=[];total=None;pdf_requested=False
            def get(url,payload=None):
                nonlocal next_request,pdf_requested
                if payload is None:
                    if url!=selected_url or pdf_requested:raise ValueError('only one selected PDF identity permitted')
                    pdf_requested=True
                else:
                    expected={'pageNum':str(len(pages)+1),'pageSize':'30','column':'szse','tabName':'fulltext','plate':'',
                        'stock':case['instrument'][2:]+','+case['organization_id'],'searchkey':'','secid':'','category':'','trade':'',
                        'seDate':case['publication_day']+'~'+case['publication_day'],'sortName':'','sortType':'','isHLtitle':'true'}
                    if url!=CNINFO+'/new/hisAnnouncement/query' or len(pages)>=2 or payload!=expected:
                        raise ValueError('only two exact issuer/day listing pages permitted')
                identity={'source':'CNINFO_HTTP','url':url,'payload':payload,'notice_request_sha256':request_sha}
                def wire():
                    nonlocal next_request
                    pause=next_request-time.monotonic()
                    if pause>0:time.sleep(pause)
                    try:return fetch(url,payload)
                    finally:next_request=time.monotonic()+.3
                return journaled_bytes(journal,identity,wire)
            def get_json(url,payload):
                nonlocal total
                body,receipt=get(url,dict(payload));data=json.loads(body)
                total=validate_listing(data,case,len(pages)+1,total);pages.append(receipt);return data
            try:
                rows=query(case['organization_id'],case['instrument'][2:],'',case['publication_day'],case['publication_day'],max_pages=2,fetch=get_json)
                row=select_implementation_notice(rows,case);selected_url='https://static.cninfo.com.cn/'+row['pdf_path']
                data,receipt=get(selected_url)
                filename=case['instrument']+'-'+case['publication_day']+'.pdf';path=out/filename
                with path.open('xb') as stream:stream.write(data)
                if not data.startswith(b'%PDF'):raise ValueError('original response is not a PDF')
                documents[key]={'instrument':case['instrument'],'publication_day':case['publication_day'],'source_question_ex_date':case['ex_date'],
                    'file':filename,'sha256':sha256_file(path),'url':selected_url,'listing_row':row,
                    'HTTP_listing_receipts':pages,'HTTP_pdf_receipt':receipt,'capture_route':'JOURNALED_ORIGINAL_PRIMARY_HTTP'}
                atomic_json(out/'progress.json',documents);consecutive=0
            except BaseException as exc:
                error={'case_id':key,'error_type':type(exc).__name__,'error':str(exc),'HTTP_responses_retained':True,'financial_approval_granted':False}
                path=out/('error-'+key.replace('|','-')+'.json');write_packet_once(path,error)
                errors[key]=sha256_file(path);atomic_json(out/'errors.json',errors)
                if not (out/'first-error.json').exists():write_packet_once(out/'first-error.json',error)
                consecutive+=1
                if not isinstance(exc,Exception):raise
            if consecutive>=3:
                write_packet_once(out/'stopped.json',{'reason':'THREE_CONSECUTIVE_FAILED_CASES','last_case_id':key});break
    except BaseException as exc:
        terminal={'error_type':type(exc).__name__,'error':str(exc)}
        write_packet_once(out/'terminal-error.json',terminal)
        if not (out/'first-error.json').exists():write_packet_once(out/'first-error.json',terminal)
    finally:
        try:
            verify_inputs(auth['known_hashes']);post={'source_inputs_unchanged_after_capture':True}
        except BaseException as exc:
            post={'source_inputs_unchanged_after_capture':False,'error_type':type(exc).__name__,'error':str(exc)}
            if not (out/'first-error.json').exists():write_packet_once(out/'first-error.json',post)
        atomic_json(out/'input-postcheck.json',post)
        count=len(list((out/'queries').glob('*/reserved-*.json')))
        complete=len(documents)==8 and not errors and terminal is None and post['source_inputs_unchanged_after_capture'] and count<=24
        manifest={'status':'LOW_MARKET_RESIDUAL_VOL1M_PRIMARY_SOURCES_CAPTURED_REVIEW_SEPARATE',
            'request_sha256':request_sha,'documents':documents,'errors':errors,
            'pending_cases':[k for k in ids if k not in documents and k not in errors],
            'HTTP_query_reservations':count,'maximum_HTTP_query_reservations':24,
            'capture_complete':complete,'abnormal_exit':terminal,
            'source_inputs_unchanged_after_capture':post['source_inputs_unchanged_after_capture'],
            'postcheck_sha256':sha256_file(out/'input-postcheck.json'),
            'artifact_sha256':{str(p.relative_to(out)):sha256_file(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'},
            'content_reviewed':False,'documents_financially_reviewed':False,'admitted_for_account_replay':False,
            'corporate_action_completeness_verified':False,'tax_verified':False,'historical_arrival_verified':False,
            'investment_rule_changed':False,'portfolio_returns_computed':False,'new_2026_queries':False,'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
    return manifest


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+name,required=True)
    p.add_argument('--source-preflight-only',action='store_true');args=p.parse_args(argv)
    base=Path(args.source_root).resolve();out=Path(args.output_dir)
    if out.exists() or out.is_symlink():raise ValueError('existing capture output is immutable')
    if out.resolve()!=base/OUTPUT:raise ValueError('fixed new capture output required')
    path=Path(args.request).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_request_sha256:raise ValueError('external request SHA changed')
    request=json.loads(raw);auth=load_inputs(Path(__file__).resolve().parents[1],base,request)
    auth['known_hashes'][str(path)]=args.expected_request_sha256
    if args.source_preflight_only:
        verify_inputs(auth['known_hashes']);print('primary source-only preflight; no HTTP or output',flush=True);return 0
    result=capture(request,auth,out,read_wire,request_bytes=raw,request_sha=args.expected_request_sha256)
    print('primary source capture',len(result['documents']),'/8; errors',len(result['errors']),flush=True)
    return 0 if result['capture_complete'] else 2

if __name__=='__main__':raise SystemExit(main())
