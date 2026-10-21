"""One immutable LFS batch + at most two object GETs; source comparisons only."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from stock_rsi.archive_minute_probe import compare_session, selected_parquet_rows, validate_pairs, need

REPO = 'neigezhu/china-a-share-1min-ohlcv'
REV = 'ba589a11534825044fe5a6b84838f50ba8d8d188'
ADMISSION = 'experiments/qlib/illiquidity-development-minute-admission.json'
BATCH = 'https://huggingface.co/datasets/' + REPO + '.git/info/lfs/objects/batch'
OUTPUT = 'illiquidity-hf-archive-probe-20261021'
RAW = {code: 'illiquidity-raw-source-continuation-20261020/codes/' + code + '.json'
       for code in ('SH603056', 'SZ002505')}
METHODS = ('src/stock_rsi/archive_minute_probe.py', 'scripts/probe_hf_illiquidity_minutes_pre2026.py')
OBJECTS = {
 'SH603056': {'file': 'data/stock_1m/SH/603056.parquet', 'oid': '7495f3cab60517b6e4122a57c7223c3b105ebdafde2bbc9f51081d26f0e4a09d', 'size': 5822238},
 'SZ002505': {'file': 'data/stock_1m/SZ/002505.parquet', 'oid': '9a4e48cb3a2d1308be015a665d6856a99aff7d69295c52c2899a979e7e318cf7', 'size': 8725631}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False, default=lambda v: v.isoformat())
        f.write('\n')


def validate_request(plan, repo):
    need(plan['dataset'] == REPO and plan['revision'] == REV and plan['objects'] == OBJECTS
         and plan['maximum_logical_requests'] == 3 and type(plan['maximum_logical_requests']) is int
         and type(plan['max_attempts_per_identity']) is int and plan['max_attempts_per_identity'] == 1
         and plan['portfolio_replay_allowed'] is False
         and plan['output_relative'] == OUTPUT, 'exact frozen two-object source-only budget required')
    need(plan['raw_packet_relative'] == RAW and set(RAW.values()) <= set(plan['source_file_sha256']),
         'both original daily packets must be explicitly bound')
    validate_pairs(plan['pairs'])
    need(set(plan['method_code_sha256']) == set(METHODS), 'complete method identity required')
    for n, h in plan['method_code_sha256'].items():
        need(sha(repo / n) == h, 'frozen archive method changed')
    admission = json.loads((repo / ADMISSION).read_text())
    need(sha(repo / ADMISSION) == plan['admission_sha256'], 'old rejected-source evidence changed')
    expected = sorted([[x['instrument'], x['day']] for x in admission['exceptions']])
    need(plan['pairs'] == expected and len(expected) == 29, 'exact existing29 source gaps required')


def safe_error(error):
    return {'error_type': type(error).__name__,
            'error': re.sub(r'https?://\S+', '[redacted source URL]', str(error), flags=re.IGNORECASE)}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class SourceResponseFailure(RuntimeError):
    def __init__(self, status, body, truncated=False):
        super().__init__('source HTTP status or byte budget failure: ' + str(status))
        self.body, self.truncated = body, truncated


def preserve_response_failure(out, label, error):
    if isinstance(error, SourceResponseFailure):
        path = out / ('private-' + label + '-error-response.bin')
        try:
            with path.open('xb') as stream:
                stream.write(error.body)
            return {'file': path.name, 'sha256': sha(path), 'bytes': len(error.body),
                    'truncated_at_byte_limit': error.truncated}
        except BaseException as persistence_error:
            return {'persistence_error': safe_error(persistence_error)}


def read_bytes(request, limit):
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            payload = response.read(limit + 1)
    except HTTPError as error:
        body = error.read(limit + 1)
        raise SourceResponseFailure(error.code, body, len(body) > limit) from None
    if len(payload) > limit:
        raise SourceResponseFailure(200, payload, True)
    return payload


def main(argv=None):
    p = argparse.ArgumentParser()
    for key in ('source-root', 'request', 'expected-request-sha256', 'output-dir'):
        p.add_argument('--' + key, required=True)
    args = p.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    base, request_path, out = Path(args.source_root).resolve(), Path(args.request).resolve(), Path(args.output_dir)
    need(not out.exists() and not out.is_symlink() and out.resolve() == base / OUTPUT, 'fresh fixed source output required')
    need(sha(request_path) == args.expected_request_sha256, 'external request changed')
    plan = json.loads(request_path.read_text());validate_request(plan, repo)
    known = {str(repo / n): h for n, h in plan['method_code_sha256'].items()}
    known.update({str(repo / ADMISSION): plan['admission_sha256'], str(request_path): args.expected_request_sha256})
    for path, h in plan['source_file_sha256'].items():
        full = base / path
        need(full.resolve().is_relative_to(base) and sha(full) == h, 'source metadata/raw input changed')
        known[str(full)] = h
    bars = {}
    for code in OBJECTS:
        packet = json.loads((base / plan['raw_packet_relative'][code]).read_text())
        bars[code] = {r['date']: r for r in packet['bars'] if '2024-01-01' <= r['date'] <= '2025-12-31'}
    out.mkdir();attempts=[];errors=[];results=[];top_error=None
    def reserve(identity):
        need(len(attempts) < 3, 'fixed source request budget exhausted')
        attempts.append(identity)
        write(out / ('reserved-' + str(len(attempts)) + '.json'), identity)
    try:
        write(out / 'input-before.json', known)
        body = {'operation': 'download', 'transfers': ['basic'], 'ref': {'name': REV},
                'objects': [{'oid': v['oid'], 'size': v['size']} for v in OBJECTS.values()]}
        reserve({'method': 'LFS_BATCH_DOWNLOAD', 'url': BATCH, 'body': body})
        raw = read_bytes(Request(BATCH, data=json.dumps(body).encode(), method='POST',
                    headers={'Content-Type': 'application/vnd.git-lfs+json', 'Accept': 'application/vnd.git-lfs+json'}), 2000000)
        # Local only: this may contain temporary signed download URLs. Public
        # receipts expose only hashes and never action URLs/header values.
        (out / 'private-batch-response.json').write_bytes(raw)
        batch = json.loads(raw);objects = {o['oid']: o for o in batch['objects']}
        need(set(objects) == {v['oid'] for v in OBJECTS.values()} and len(batch['objects']) == 2,
             'batch response must contain exactly both frozen objects')
        for code, spec in OBJECTS.items():
            item = {'instrument': code, 'file': spec['file'], 'expected_sha256': spec['oid']}
            try:
                obj = objects[spec['oid']];need(obj['size'] == spec['size'] and 'error' not in obj, 'LFS object error or size mismatch')
                action = obj['actions']['download'];url = action['href'];parts = urlsplit(url)
                need(parts.scheme == 'https' and parts.hostname and
                     (parts.hostname == 'huggingface.co' or parts.hostname.endswith(('.huggingface.co', '.hf.co'))),
                     'unrecognized source download authority')
                reserve({'method': 'PINNED_OBJECT_GET', 'instrument': code, 'oid': spec['oid'],
                         'size': spec['size'], 'download_authority': parts.hostname})
                data = read_bytes(Request(url, headers=action.get('header', {})), spec['size'])
                path = out / (code + '.parquet');path.write_bytes(data)
                need(len(data) == spec['size'] and sha(path) == spec['oid'], 'immutable LFS content hash/length mismatch')
                wanted = [pair for pair in plan['pairs'] if pair[0] == code]
                rows = selected_parquet_rows(path, wanted)
                write(out / (code + '-selected-development-rows.json'), rows)
                for _, day in wanted:
                    try:
                        result = compare_session(code, day, [r for r in rows if r['timestamp'].date().isoformat() == day], bars[code][day])
                        result['status'] = 'SOURCE_COMPARISON_COMPLETE'
                    except Exception as error:
                        result = {'instrument': code, 'day': day, 'status': 'SOURCE_COMPARISON_FAILED', **safe_error(error)}
                    results.append(result)
                item['status'] = 'OBJECT_VERIFIED_SELECTED_DEVELOPMENT_COMPARISON_COMPLETE'
            except Exception as error:
                item.update(status='SOURCE_OBJECT_OR_PARSER_FAILURE', **safe_error(error))
                item['source_error_response'] = preserve_response_failure(out, code, error)
            write(out / (code + '-receipt.json'), item)
            if item['status'] == 'SOURCE_OBJECT_OR_PARSER_FAILURE':errors.append(item)
    except BaseException as error:
        top_error = safe_error(error)
        top_error['source_error_response'] = preserve_response_failure(out, 'batch', error)
        write(out / 'terminal-error.json', top_error)
    finally:
        post = {}
        for n, h in known.items():
            try:
                post[n] = sha(Path(n)) == h
            except BaseException:
                post[n] = False
        write(out / 'input-postcheck.json', post)
    summary = {'status': 'HF_ARCHIVE_SOURCE_PROBE_COMPLETE' if top_error is None and not errors and all(post.values()) else 'HF_ARCHIVE_SOURCE_PROBE_INCOMPLETE',
               'request_sha256': args.expected_request_sha256, 'dataset': REPO, 'revision': REV,
               'logical_requests_reserved': len(attempts), 'source_failures': errors, 'terminal_error': top_error,
               'session_comparisons': results, 'all_bound_inputs_unchanged': all(post.values()),
               'raw_objects_can_include_later_years': True, 'reader_can_internally_decode_mixed_year_groups': True,
               'later_year_quote_rows_exposed_by_filtered_reader': False,
               'source_intervals_shifted_or_prices_rounded': False, 'prior_rejected_sources_modified': False,
               'admitted_for_reconstructed_execution': False, 'historical_arrival_verified': False,
               'new_alpha_candidates': 0, 'portfolio_returns_computed': False, 'objective_achieved': False}
    write(out / 'summary.json', summary)
    print(json.dumps({'status': summary['status'], 'logical_requests_reserved': len(attempts), 'session_comparisons': len(results)}))
    return 0 if summary['status'] == 'HF_ARCHIVE_SOURCE_PROBE_COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
