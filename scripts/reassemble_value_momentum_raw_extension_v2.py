"""Local-only, separately frozen raw packet reassembly; no SDK or account calls.

123 V1 packets are copied byte-for-byte. Only four rejected packets are rebuilt
from immutable responses. Their coordinate revisions must satisfy an exact,
bounded rational rounding proof; economic entitlements are never inferred here.
"""
import argparse
import copy
import json
import re
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from scripts.capture_value_momentum_raw_extension import (
    authenticate_request, METHOD_FILES as V1_METHODS, OLD, OUTPUT as V1,
)
from scripts.value_momentum_raw_extension_sources import (
    START, PRE_END, END, compose_packet, expected_sessions, fetch_packet,
    financial_core, validate_bars, day,
)
from scripts.capture_illiquidity_raw_development import unwrap_vendor_response
from scripts.fundamental_query_journal import digest, file_sha, write_packet_once

REJECTED = ('SZ000563', 'SZ000783', 'SZ002608', 'SZ002756')
PRIMARY = 'szse-value-momentum-primary-2026-gaps-20261021'
REVIEW = 'experiments/qlib/szse-value-momentum-primary-2026-seven-content-review.json'
PROTOCOL = 'docs/research/szse-value-momentum-raw-reassembly-v2-plan-2026-10-21.md'
OUTPUT = 'szse-value-momentum-raw-full-v2-20261021'
DAILY = 'szse-value-momentum-raw-daily-dev-20261021'
INTRADAY = 'szse-value-momentum-intraday-dev-20261021'
METHOD_FILES = (*V1_METHODS, 'scripts/reassemble_value_momentum_raw_extension_v2.py')
PUBLIC_FILES = (REVIEW, PROTOCOL)
LOCAL_FILES = tuple(f'{V1}/{n}' for n in (
    'request.json', 'manifest.json', 'calendar.json', 'errors.json', 'cleanup.json',
    'source-postcheck.json', 'login-reserved-1.json', 'login-response-1.json',
)) + (f'{PRIMARY}/manifest.json', f'{DAILY}/summary.json', f'{INTRADAY}/summary.json')
NOTICE_CODES = ('SZ000563', 'SZ000783', 'SZ002131', 'SZ002608', 'SZ002756', 'SZ002812', 'SZ003031')
HALF_UNIT = Fraction(1, 2000000)


def read(path):
    return json.loads(Path(path).read_text())


def safe(root, name):
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('safe relative frozen source path required')
    path = Path(root) / name
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('source symlink escapes bound root')
    return path


def rational6(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+\.[0-9]{6}', value):
        raise ValueError('positive six-decimal published factor required')
    result = Fraction(Decimal(value))
    if result <= HALF_UNIT:
        raise ValueError('factor rounding interval must be positive')
    return result


def ratio_text(value):
    return f'{value.numerator}/{value.denominator}'


def indexed(rows, field):
    keys = [r[field] for r in rows]
    if keys != sorted(set(keys)):
        raise ValueError('ordered unique row identities required')
    return dict(zip(keys, rows))


def validate_notice(review, code, ex_date):
    required = {'instrument', 'file', 'sha256', 'publication_day', 'record_date', 'ex_date',
                'cash_payment_date', 'cash_per_original_share_CNY', 'stock_per_original_share',
                'capital_per_original_share', 'primary_pages'}
    if not required <= set(review) or review['instrument'] != code or review['ex_date'] != ex_date:
        raise ValueError('primary cash notice issuer/ex-date mismatch')
    if (Path(review['file']).name != review['file'] or not re.fullmatch('[0-9a-f]{64}', review['sha256'])
            or not review['primary_pages'] or any(type(p) is not int or p < 1 for p in review['primary_pages'])
            or not '2026-01-01' <= day(review['publication_day']) <= day(review['record_date'])
            < day(review['ex_date']) <= END or day(review['cash_payment_date']) < review['ex_date']):
        raise ValueError('primary cash notice date/page/source identity invalid')
    amounts = [Decimal(review[k]) for k in ('cash_per_original_share_CNY', 'stock_per_original_share', 'capital_per_original_share')]
    if any(not x.is_finite() for x in amounts) or amounts[0] <= 0 or amounts[1:] != [0, 0]:
        raise ValueError('only verified positive cash-only notice allowed')


def verify_coordinate_transition(fresh, cached, review):
    """Compare 2026 common rows; retain all old prefix coordinates separately.

    Each six-decimal published quantity x bounds its true value by x +/- 0.5e-6.
    Test interval intersection using Fraction, without float or Decimal context
    rounding. This establishes coordinate consistency, not the economic cause.
    """
    code = fresh['instrument']
    if cached['instrument'] != code or fresh['window'] != ['2026-01-01', END]:
        raise ValueError('fixed incremental issuer/window required')
    lo, hi = max(fresh['window'][0], cached['window'][0]), min(END, cached['window'][1])
    if hi != '2026-10-16':
        raise ValueError('registered conflict cache must end Oct16')
    left = indexed(fresh['bars'], 'date')
    right = indexed([r for r in cached['bars'] if lo <= r['date'] <= hi], 'date')
    if {d for d in left if lo <= d <= hi} != set(right):
        raise ValueError('common raw dates missing or added')
    for d, row in right.items():
        if financial_core(left[d]) != financial_core(row) or left[d].get('adjustflag') != row.get('adjustflag'):
            raise ValueError('raw financial core changed')
    old_div = [r for r in cached['distributions'] if lo <= r['dividOperateDate'] <= hi]
    # The fixed four responses have no new distribution row. Keep their exact
    # source rows; primary supplements belong to a later separate event compiler.
    if fresh['distributions'] != old_div:
        raise ValueError('dividend fields, ordering or row membership changed')
    old = indexed([r for r in cached['adjustments'] if lo <= r['dividOperateDate'] <= hi], 'dividOperateDate')
    new = indexed(fresh['adjustments'], 'dividOperateDate')
    if not old or {d for d in new if d <= hi} != set(old):
        raise ValueError('common adjustment dates missing or added')
    added = [r for d, r in new.items() if d > hi]
    if len(added) != 1:
        raise ValueError('exactly one new primary-backed adjustment date required')
    validate_notice(review, code, added[0]['dividOperateDate'])
    old_latest, new_latest = old[max(old)], new[max(new)]
    if old_latest['foreAdjustFactor'] != '1.000000' or new_latest['foreAdjustFactor'] != '1.000000':
        raise ValueError('latest factor coordinates must be one')
    old_back, new_back = rational6(old_latest['backAdjustFactor']), rational6(new_latest['backAdjustFactor'])
    if new_back <= old_back:
        raise ValueError('positive cash-only coordinate requires increased latest back factor')
    ratio = old_back / new_back
    ratio_low = (old_back-HALF_UNIT)/(new_back+HALF_UNIT)
    ratio_high = (old_back+HALF_UNIT)/(new_back-HALF_UNIT)
    proofs = []
    for d, before in old.items():
        after = new[d]
        if {k:v for k,v in before.items() if k != 'foreAdjustFactor'} != {k:v for k,v in after.items() if k != 'foreAdjustFactor'}:
            raise ValueError('nonfore adjustment field changed')
        a, b = rational6(before['foreAdjustFactor']), rational6(after['foreAdjustFactor'])
        for row in (before, after):
            rational6(row['backAdjustFactor']); rational6(row['adjustFactor'])
        lower, upper = (a-HALF_UNIT)*ratio_low, (a+HALF_UNIT)*ratio_high
        if lower > b+HALF_UNIT or upper < b-HALF_UNIT:
            raise ValueError('fore coordinate exceeds exact six-decimal rounding bound')
        proofs.append({'date':d, 'cached_fore':before['foreAdjustFactor'], 'fresh_fore':after['foreAdjustFactor'],
                       'predicted_interval':[ratio_text(lower),ratio_text(upper)],
                       'fresh_rounding_interval':[ratio_text(b-HALF_UNIT),ratio_text(b+HALF_UNIT)],
                       'nonfore_fields_exact':True})
    for k in ('foreAdjustFactor', 'backAdjustFactor', 'adjustFactor'):
        rational6(added[0][k])
    if added[0]['code'] != old_latest['code'] or added[0]['adjustFactor'] != added[0]['backAdjustFactor']:
        raise ValueError('new adjustment code/back coordinate mismatch')
    if not any(r['cached_fore'] != r['fresh_fore'] for r in proofs):
        raise ValueError('registered rejected packet must contain a fore revision')
    return {'instrument':code, 'comparison_window':[lo,hi], 'common_daily_rows':len(right),
            'common_distribution_rows':len(old_div), 'old_latest_back':old_latest['backAdjustFactor'],
            'new_latest_back':new_latest['backAdjustFactor'], 'ratio_exact':ratio_text(ratio),
            'ratio_rounding_interval':[ratio_text(ratio_low),ratio_text(ratio_high)],
            'common_fore_coordinate_checks':proofs, 'new_adjustment_row':copy.deepcopy(added[0]),
            'primary_notice':copy.deepcopy(review), 'economic_cause_inferred_from_factors':False}


def verify_original_prefix(packet, original):
    for key, date_field in (('bars','date'), ('distributions','dividOperateDate'), ('adjustments','dividOperateDate')):
        if [r for r in packet[key] if r[date_field] <= PRE_END] != original[key]:
            raise ValueError('literal original pre2026 rows changed: '+key)


class ReadOnlyJournal:
    """Read captured bytes only. The callback is deliberately never invoked."""
    def __init__(self, root):
        self.root = Path(root)

    def query(self, identity, fetch=None):
        key = digest(identity); folder = self.root/'queries'/key
        if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'request.json','reserved-1.json','response-1.json'}:
            raise ValueError('complete single-attempt saved query required; no fallback')
        request, reserved, response = (folder/n for n in ('request.json','reserved-1.json','response-1.json'))
        r, a, v = read(request), read(reserved), read(response)
        if (r != identity or digest(r) != key or a['identity_sha256'] != key or a['attempt'] != 1
                or v['identity_sha256'] != key or v['reservation_sha256'] != file_sha(reserved)
                or v['status'] != 'CAPTURED' or digest(v['payload']) != v['payload_sha256']):
            raise ValueError('saved identity/reservation/response payload chain changed')
        unwrap_vendor_response(v['payload'])
        return v['payload'], {k+'_file':str(p.relative_to(self.root)) for k,p in
            (('request',request),('reserved',reserved),('response',response))} | {
            k+'_sha256':file_sha(p) for k,p in (('request',request),('reserved',reserved),('response',response))}


def expected_identities(codes, baselines, cached, request_sha):
    result = []
    for code in codes:
        if code in cached:
            continue
        start = '2026-01-01' if code in baselines else START
        params = [('daily', {'start_date':start,'end_date':END,'frequency':'d','adjustflag':'3'})]
        params += [('dividend'+str(y), {'year':str(y),'yearType':'operate'}) for y in ((2026,) if code in baselines else (2024,2025,2026))]
        params += [('adjustments', {'start_date':start,'end_date':END})]
        result.extend({'source':'BaoStock','instrument':code,'component':component,'parameters':parameters,
                       'composite_raw_extension_request_sha256':request_sha} for component,parameters in params)
    return result


def tree_hashes(root):
    return {str(p.relative_to(root)):file_sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()}


def verify_map(root, mapping):
    for name, h in mapping.items():
        if file_sha(safe(root,name)) != h:
            raise ValueError('immutable input bytes changed: '+name)


def financial_hashes(base):
    result = {}
    for directory, key, profiles, files in (
        (DAILY,'results_by_extra_bps',{'20','40'}, {'daily.csv','intents.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}),
        (INTRADAY,'results_by_profile',{f'{p}/{b}' for p in (100,500,1000) for b in (20,40)}, {'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}),
    ):
        values = read(base/directory/'summary.json')[key]
        if set(values) != profiles:
            raise ValueError('original financial profile set changed')
        for profile,v in values.items():
            if set(v['artifact_sha256']) != files:
                raise ValueError('all original financial files required')
            result.update({f'{directory}/{profile}/{name}':h for name,h in v['artifact_sha256'].items()})
    verify_map(base,result)
    return result


def authenticate_v2(base, repo, request_path, expected_sha):
    if file_sha(request_path) != expected_sha:
        raise ValueError('frozen V2 request changed')
    plan = read(request_path)
    if (plan['status'] != 'FROZEN_COMPOSITE_RAW_EXTENSION_LOCAL_REASSEMBLY_V2'
            or plan['candidate'] != 'szse_value_momentum_equal' or plan['window'] != [START,END]
            or plan['output_directory'] != OUTPUT or plan['reassembled_codes'] != list(REJECTED)
            or plan['maximum_new_source_queries'] != 0 or plan['coordinate_rule'] != 'SIX_DECIMAL_HALF_UNIT_RATIONAL_INTERVAL'
            or plan['copied_packets'] != 123 or plan['expected_names'] != 127):
        raise ValueError('fixed local-only V2 scope changed')
    for field, files, root in (('method_code_sha256',METHOD_FILES,repo), ('public_evidence_sha256',PUBLIC_FILES,repo), ('local_source_sha256',LOCAL_FILES,base)):
        if set(plan[field]) != set(files):
            raise ValueError('exact V2 frozen binding set required: '+field)
        verify_map(root,plan[field])
    old_request = base/V1/'request.json'; original_sha = plan['local_source_sha256'][f'{V1}/request.json']
    context = authenticate_request(old_request,original_sha,repo,base)
    original,codes,sessions,baselines,cached,overlaps,lifecycles,lineage = context
    v1 = base/V1; manifest = read(v1/'manifest.json')
    if (manifest['request_sha256'] != original_sha or manifest['status'] != 'COMPOSITE_RAW_EXTENSION_CAPTURED_ADMISSION_SEPARATE'
            or manifest['names'] != 123 or manifest['requested_names'] != 127 or manifest['pending_codes']
            or manifest['abnormal_exit'] is not None or manifest['query_reservations_consumed'] != 362
            or manifest['source_inputs_unchanged_after_capture'] is not True
            or set(manifest['errors_sha256']) != set(REJECTED)
            or set(manifest['per_code_sha256']) != set(codes)-set(REJECTED)
            or read(v1/'errors.json') != manifest['errors_sha256']
            or read(v1/'calendar.json')['sessions'] != sessions or file_sha(v1/'calendar.json') != manifest['calendar_sha256']):
        raise ValueError('exact immutable123-plus4 terminal capture required')
    if tree_hashes(v1) != plan['v1_artifact_sha256']:
        raise ValueError('complete original capture tree changed')
    for c,h in manifest['errors_sha256'].items():
        err = v1/'errors'/(c+'.json')
        if file_sha(err) != h or read(err) != {'instrument':c,'error_type':'ValueError',
                'error':'registered cached corporate/adjustment conflict: adjustments',
                'request_sha256':original_sha,'source_responses_retained':True}:
            raise ValueError('original rejection evidence changed')
    for c,h in manifest['per_code_sha256'].items():
        if file_sha(v1/'codes'/(c+'.json')) != h:
            raise ValueError('original accepted packet changed')
    for name, field in (('cleanup.json','cleanup_sha256'), ('source-postcheck.json','source_postcheck_sha256')):
        if file_sha(v1/name) != manifest[field]:
            raise ValueError('original cleanup/postcheck evidence changed')
    if (read(v1/'cleanup.json').get('error_code') != '0'
            or read(v1/'source-postcheck.json').get('source_inputs_unchanged_after_capture') is not True
            or read(v1/'login-response-1.json').get('error_code') != '0'
            or read(v1/'login-reserved-1.json') != {'attempt':1,'request_sha256':original_sha}):
        raise ValueError('original administration not complete')
    identities = expected_identities(codes,baselines,cached,original_sha)
    if len(identities) != 362 or {p.name for p in (v1/'queries').iterdir()} != {digest(x) for x in identities}:
        raise ValueError('all and only362 fixed saved queries required')
    journal = ReadOnlyJournal(v1)
    for identity in identities:
        journal.query(identity)
    if financial_hashes(base) != plan['financial_artifact_sha256'] or len(plan['financial_artifact_sha256']) != 54:
        raise ValueError('all42intraday plus12daily original artifacts required')
    primary = read(base/PRIMARY/'manifest.json'); content = read(repo/REVIEW)
    if primary['capture_complete'] is not True or primary['errors'] or primary['pending'] or set(primary['documents']) != set(NOTICE_CODES):
        raise ValueError('complete seven original notice capture required')
    docs = content['documents']
    if len(docs) != 7 or {d['instrument'] for d in docs} != set(NOTICE_CODES):
        raise ValueError('all seven issuer reviews required')
    reviewed = {d['instrument']:d for d in docs}
    for c, doc in primary['documents'].items():
        p = safe(base/PRIMARY,doc['file']); r = reviewed[c]
        if (Path(doc['file']).name != doc['file'] or doc['instrument'] != c or not p.read_bytes().startswith(b'%PDF')
                or file_sha(p) != doc['sha256'] or any(r[k] != doc[k] for k in ('instrument','file','sha256','publication_day'))):
            raise ValueError('review must bind original issuer/publication/PDF bytes')
        for kind in ('request','reserved','response'):
            receipt = doc['pdf_receipt']
            if file_sha(safe(base/PRIMARY,receipt[kind+'_file'])) != receipt[kind+'_sha256']:
                raise ValueError('primary PDF capture receipt changed')
    return plan,context,manifest,journal,reviewed


def prepare_packets(base, context, manifest, journal, reviews):
    original,codes,sessions,baselines,cached,overlaps,lifecycles,lineage = context
    result = {}; coordinate_checks = {}
    for code in codes:
        if code not in REJECTED:
            result[code] = read(base/V1/'codes'/(code+'.json'))
        else:
            if code not in baselines or not overlaps.get(code):
                raise ValueError('registered rejected name must have baseline and caches')
            def forbidden(*args):
                raise AssertionError('local-only reassembly has no source fallback')
            fresh = fetch_packet(journal,code,manifest['request_sha256'],forbidden,baselines[code])
            coordinate_checks[code] = [verify_coordinate_transition(fresh,cache,reviews[code]) for cache in overlaps[code]]
            packet = compose_packet(code,fresh,baselines[code],sessions,caches=(),listed_on=lifecycles.get(code))
            packet['source_query_receipts'] = copy.deepcopy(fresh['source_query_receipts'])
            packet['provenance'] = {'kind':'LOCAL_ONLY_V2_FORE_COORDINATE_REASSEMBLY',
                'source_receipts_relative_to':V1, 'v1_request_sha256':manifest['request_sha256'],
                'v1_error_sha256':manifest['errors_sha256'][code], 'registered_source_lineage':copy.deepcopy(lineage[code]),
                'baseline_provenance':copy.deepcopy(baselines[code].get('provenance')),
                'baseline_source_query_receipts':copy.deepcopy(baselines[code].get('source_query_receipts')),
                'original_prefix_preserved':True, 'coordinate_proof_file':'coordinate_checks.json',
                'primary_notice_sha256':reviews[code]['sha256'], 'factor_values_normalized_or_rewritten':False}
            result[code] = packet
        p = result[code]
        if p['instrument'] != code or p['window'] != [START,END]:
            raise ValueError('full packet issuer/window changed')
        validate_bars(code,p['bars'])
        if [r['date'] for r in p['bars']] != expected_sessions(code,sessions,lifecycles.get(code)):
            raise ValueError('full calendar or sole primary listing exception failed')
        if code in baselines:
            verify_original_prefix(p,baselines[code])
    if len(result) != 127 or len(sessions) != 676 or len(result['SZ001389']['bars']) != 616:
        raise ValueError('complete127/676/616 source scope required')
    return result,coordinate_checks


def copy_exact(source, target, expected_sha):
    content = Path(source).read_bytes()
    if file_sha(source) != expected_sha:
        raise ValueError('source changed before immutable copy')
    with Path(target).open('xb') as f:
        f.write(content)
    if file_sha(target) != expected_sha:
        raise ValueError('copy must remain byte exact')


def main(argv=None):
    parser = argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256','output-dir'):
        parser.add_argument('--'+n,required=True)
    parser.add_argument('--preflight-only',action='store_true')
    args = parser.parse_args(argv); out = Path(args.output_dir)
    if out.exists():
        raise ValueError('preserve existing output; no resume')
    base = Path(args.source_root); repo = Path(__file__).resolve().parents[1]
    if out.resolve() != (base/OUTPUT).resolve():
        raise ValueError('fixed separate V2 output required')
    authenticated = authenticate_v2(base,repo,args.request,args.expected_request_sha256)
    plan,context,manifest,journal,reviews = authenticated
    packets,checks = prepare_packets(base,context,manifest,journal,reviews)
    if args.preflight_only:
        print('local V2 preflight127 packets/362 saved responses/54 old financial files; no output/network/account')
        return 0
    out.mkdir(); (out/'codes').mkdir()
    try:
        copy_exact(args.request,out/'request.json',args.expected_request_sha256)
        copy_exact(base/V1/'calendar.json',out/'calendar.json',manifest['calendar_sha256'])
        write_packet_once(out/'coordinate_checks.json',checks)
        hashes = {}
        for code,p in packets.items():
            destination = out/'codes'/(code+'.json')
            if code in REJECTED:
                write_packet_once(destination,p)
            else:
                copy_exact(base/V1/'codes'/(code+'.json'),destination,manifest['per_code_sha256'][code])
            hashes[code] = file_sha(destination)
        # Recheck all authenticated inputs, including complete V1 tree and all
        #54 financial artifacts, before publishing success. Failures stay visible.
        authenticate_v2(base,repo,args.request,args.expected_request_sha256)
        write_packet_once(out/'manifest.json',{'status':'LOCAL_ONLY_V2_RAW_REASSEMBLED_ADMISSION_SEPARATE',
            'window':[START,END], 'names':127, 'request_sha256':args.expected_request_sha256,
            'v1_manifest_sha256':file_sha(base/V1/'manifest.json'), 'v1_original_errors_preserved':manifest['errors_sha256'],
            'calendar_sha256':file_sha(out/'calendar.json'), 'per_code_sha256':hashes,
            'copied_v1_packets_byte_exact':123, 'reassembled_from_existing_responses':list(REJECTED),
            'source_query_receipts_relative_to':V1, 'coordinate_checks_sha256':file_sha(out/'coordinate_checks.json'),
            'original103_pre2026_rows_literal_equal':True, 'pre2026_baselines_checked':len(context[3]),
            'original42_intraday_and12_daily_hashes_unchanged':True, 'source_inputs_unchanged_after_reassembly':True,
            'primary_manifest_sha256':file_sha(base/PRIMARY/'manifest.json'), 'primary_content_review_sha256':file_sha(repo/REVIEW),
            'source_queries':0, 'original_v1_capture_errors_cleared':False, 'new_cash_entitlement_rows_created':0,
            'admitted_for_account_replay':False, 'historical_arrival_verified':False, 'full_corporate_actions_certified':False,
            'actual_FIFO_tax_liability_verified':False, 'portfolio_returns_computed':False,
            'investment_rules_changed':False, 'objective_achieved':False})
    except BaseException as exc:
        write_packet_once(out/'failure.json',{'error_type':type(exc).__name__,'error':str(exc),
            'status':'V2_REASSEMBLY_FAILED_PRESERVED','admitted_for_account_replay':False,'source_queries':0})
        raise
    print('local-only V2 raw reassembly complete; event/account admission remains separate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
