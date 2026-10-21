"""Physically retain only pre2026 binary prefixes; no market calls or returns."""
import argparse
import bisect
from datetime import date
import json
import math
from pathlib import Path
import struct

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_qlib_low_risk_pre2026 import input_hashes, parse_memberships

END = '2025-12-31'
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'factor', 'amount', 'adjclose')
METHOD_FILES = ('scripts/prepare_price_delay_provider_pre2026.py', 'scripts/run_qlib_low_risk_pre2026.py',
    'scripts/run_cninfo_orj_signal_pre2026.py', 'scripts/prepare_qlib_master_market_pre2026.py')


def clip_feature(source, target, cutoff_index, calendar_length):
    source, target = Path(source), Path(target)
    if target.exists(): raise ValueError('preserve existing clipped feature')
    size = source.stat().st_size
    if size < 8 or size % 4: raise ValueError('invalid source feature length')
    with source.open('rb') as stream:
        header = stream.read(4); raw_start = struct.unpack('<f', header)[0]
        if not math.isfinite(raw_start) or raw_start != int(raw_start):
            raise ValueError('integer feature offset required')
        start = int(raw_start); count = size//4-1
        if start < 0 or start+count > calendar_length or not 0 <= cutoff_index < calendar_length:
            raise ValueError('feature extent outside explicit calendar')
        if start > cutoff_index: return None
        keep = min(count, cutoff_index-start+1)
        # Read only the retained byte prefix. Never unpack a future float.
        payload = stream.read(keep*4)
        if len(payload) != keep*4: raise ValueError('source shortened during prefix copy')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream: stream.write(header+payload)
    return {'start_index': start, 'last_index': start+keep-1, 'copied_values': keep,
        'source_values': count, 'sha256': sha256_file(target)}


def clipped_intervals(text, codes, cutoff=END):
    rows = []
    for line in text.splitlines():
        if not line: continue
        code, first, last = line.split()
        if date.fromisoformat(first) > date.fromisoformat(last): raise ValueError('inverted source interval')
        if code.upper() in codes and first <= cutoff:
            rows.append('\t'.join((code, first, min(last, cutoff))))
    return '\n'.join(rows)+'\n'


def main():
    p = argparse.ArgumentParser()
    for n in ('provider-uri', 'request', 'expected-request-sha256', 'output-dir'):
        p.add_argument('--'+n, required=True)
    a = p.parse_args(); source = Path(a.provider_uri); out = Path(a.output_dir); repo = Path(__file__).resolve().parents[1]
    if out.exists() or sha256_file(a.request) != a.expected_request_sha256:
        raise ValueError('unused output and frozen preparation request required')
    request = json.loads(Path(a.request).read_bytes())
    if (request['status'] != 'FROZEN_PHYSICAL_PRE2026_PROVIDER_PREFIX'
        or request['end'] != END or request['fields'] != list(FIELDS)
        or set(request['method_code_sha256']) != set(METHOD_FILES)):
        raise ValueError('fixed date and feature copy contract required')
    for n, h in request['method_code_sha256'].items():
        if sha256_file(repo/n) != h: raise ValueError('prefix preparation method changed')
    if sha256_file(repo/'docs/research/price-delay-pre2026-design-2026-10-21.md') != request['design_sha256']:
        raise ValueError('registered research scope changed')
    memberships = parse_memberships((source/'instruments/csi500.txt').read_text())
    if input_hashes(source, memberships) != request['source_input_sha256']:
        raise ValueError('original provider source identity changed')
    codes = sorted(c for c, spans in memberships.items() if any(first <= END and last >= '2023-12-29' for first, last in spans))
    if codes != request['codes'] or len(codes) < 200: raise ValueError('fixed historical research universe changed')
    calendar = (source/'calendars/day.txt').read_text().splitlines()
    if calendar != sorted(set(calendar)): raise ValueError('explicit unique source sessions required')
    cut = bisect.bisect_right(calendar, END)-1
    if cut < 0 or calendar[cut] != END: raise ValueError('actual final2025 source session required')
    names = sorted(set(codes)|{'SH000905'})
    out.mkdir(parents=True); (out/'calendars').mkdir(); (out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(calendar[:cut+1])+'\n')
    for name in ('all.txt', 'csi500.txt'):
        (out/'instruments'/name).write_text(clipped_intervals((source/'instruments'/name).read_text(), set(names)))
    files = {}
    for code in names:
        for field in (('close', 'adjclose') if code == 'SH000905' else FIELDS):
            relative = f'features/{code.lower()}/{field}.day.bin'
            meta = clip_feature(source/relative, out/relative, cut, len(calendar))
            if meta is None: raise ValueError('registered historical instrument has only future features')
            meta['source_sha256'] = sha256_file(source/relative)
            meta['last_date'] = calendar[meta['last_index']]; files[relative] = meta
    if input_hashes(source, memberships) != request['source_input_sha256']:
        raise ValueError('source changed during prefix preparation; retain partial output')
    output_memberships = parse_memberships((out/'instruments/csi500.txt').read_text())
    manifest = {'status': 'PHYSICAL_PRE2026_PROVIDER_PREFIX_NO_RETURNS', 'request_sha256': a.expected_request_sha256,
        'source_input_sha256': request['source_input_sha256'], 'output_input_sha256': input_hashes(out, output_memberships),
        'source_calendar_end': calendar[-1], 'output_calendar_end': calendar[cut], 'equity_names': len(codes),
        'per_feature': files, 'source_tail_bytes_hashed_for_identity_not_decoded_as_prices': True,
        'all_output_values_at_or_before': END, 'original_source_modified': False, 'network_queries': 0,
        'portfolio_returns_computed': False, 'historical_arrival_verified': False, 'strict_OS_isolation': False}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('physically capped', len(codes), 'equities;', len(files), 'binary fields; final session', calendar[cut])


if __name__ == '__main__': main()
