"""Authenticate one vendor release, extract fixed identities, and cap two views."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import tarfile

from scripts.prepare_published_strategy_data import CODES, FIELDS

END = '2026-10-27'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def inventory(root):
    root = Path(root)
    if any(p.is_symlink() for p in root.rglob('*')): raise ValueError('no source symlinks')
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def write(path, value):
    with Path(path).open('x') as f: f.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def selected_files():
    return {'calendars/day.txt', 'calendars/day_future.txt', 'instruments/all.txt'} | {
        'features/' + code.lower() + '/' + field + '.day.bin' for code in CODES for field in FIELDS}


def extract(archive, manifest, out):
    archive, out = Path(archive), Path(out)
    if out.exists(): raise ValueError('fresh extraction required')
    if archive.stat().st_size != manifest['archive_size_bytes'] or sha(archive) != manifest['archive_sha256'].removeprefix('sha256:'):
        raise ValueError('vendor archive hash or size mismatch')
    out.mkdir(parents=True); wanted = selected_files(); found = set()
    with tarfile.open(archive, mode='r|gz') as tar:
        for member in tar:
            name = member.name.removeprefix('./').removeprefix('qlib_bin/')
            if name not in wanted: continue
            if name in found or not member.isfile() or '..' in PurePosixPath(name).parts or member.size > 16 * 1024 * 1024:
                raise ValueError('invalid or duplicate selected source member')
            f = tar.extractfile(member)
            if f is None: raise ValueError('missing archive stream')
            data = f.read(member.size + 1)
            if len(data) != member.size: raise ValueError('truncated selected member')
            target = out / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data); found.add(name)
    if found != wanted: raise ValueError('archive lacks original source identity files: ' + str(sorted(wanted - found)))
    write(out / 'extraction.json', {'archive_sha256': manifest['archive_sha256'], 'files': inventory(out)})


def dates(text):
    from datetime import date
    values = text.splitlines()
    if not values or values != sorted(set(values)) or any(date.fromisoformat(d).isoformat() != d for d in values):
        raise ValueError('explicit sorted actual source sessions required')
    return values


def prepare_view(extracted, out, end):
    extracted, out = Path(extracted), Path(out)
    if out.exists(): raise ValueError('fresh provider required')
    source_days = dates((extracted / 'calendars/day.txt').read_text())
    future = dates((extracted / 'calendars/day_future.txt').read_text())
    day = [d for d in source_days if d <= end]
    following = sorted({d for d in source_days + future if d > end})
    if not day or day[-1] != end or not following: raise ValueError('actual final and next source sessions required')
    out.mkdir(parents=True); (out / 'calendars').mkdir(); (out / 'instruments').mkdir()
    (out / 'calendars/day.txt').write_text('\n'.join(day) + '\n')
    (out / 'calendars/day_future.txt').write_text('\n'.join(day + following[:1]) + '\n')
    instruments = []
    for line in (extracted / 'instruments/all.txt').read_text().splitlines():
        code, first, last = line.split()
        if code.upper() in CODES: instruments.append((code.upper(), first, min(last, end)))
    if {i[0] for i in instruments} != set(CODES): raise ValueError('all original symbols required')
    (out / 'instruments/all.txt').write_text(''.join('\t'.join(i) + '\n' for i in sorted(instruments)))
    last_index = len(day) - 1; features = {}
    for rel in sorted(selected_files()):
        if not rel.startswith('features/'): continue
        path = extracted / rel
        with path.open('rb') as f:
            header = f.read(4)
            if len(header) != 4: raise ValueError('missing feature header')
            start_value = struct.unpack('<f', header)[0]; start = int(start_value)
            if start != start_value or not 0 <= start <= last_index: raise ValueError('invalid source feature origin')
            count = min(last_index - start + 1, path.stat().st_size // 4 - 1)
            raw = header + f.read(count * 4)
        if len(raw) != 4 * (count + 1) or start + count - 1 > last_index: raise ValueError('feature exceeds capped calendar')
        target = out / rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        features[rel] = {'sha256': sha(target), 'last_quote_date': source_days[start + count - 1]}
    result = {'status': 'ONE_VENDOR_VERSION_FIXED_RECIPE_QUOTES', 'end': end, 'next_clock_session': following[0],
              'symbols': list(CODES), 'per_feature': features, 'all_output_sha256': inventory(out),
              'evidence': 'ADJUSTED_DAILY_ENGINEERING_SAMPLE_NOT_RAW_SHARE_OR_HISTORICAL_ARRIVAL_QUALIFICATION'}
    write(out / 'manifest.json', result)
    return result


def compare_history(old, new):
    old, new = Path(old), Path(new)
    rows = {}
    for rel in sorted(selected_files()):
        if not rel.startswith('features/'): continue
        original = (old / rel).read_bytes()
        with (new / rel).open('rb') as f: prefix = f.read(len(original))
        rows[rel] = {'old_sha256': hashlib.sha256(original).hexdigest(), 'new_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
                     'identical': original == prefix, 'original_bytes': len(original)}
    return rows


def main():
    p = argparse.ArgumentParser()
    for n in ('archive', 'vendor-manifest', 'old-provider', 'out'): p.add_argument('--' + n, required=True)
    a = p.parse_args(); out = Path(a.out)
    if out.exists(): raise ValueError('fresh full data stage required')
    manifest = json.loads(Path(a.vendor_manifest).read_text())
    if manifest['target_trade_date'] != END: raise ValueError('one predeclared release only')
    out.mkdir(parents=True)
    extract(a.archive, manifest, out / 'extracted')
    pre = prepare_view(out / 'extracted', out / 'pre2026', '2025-12-31')
    horizon = prepare_view(out / 'extracted', out / 'through2026', END)
    comparison = compare_history(a.old_provider, out / 'pre2026')
    result = {'vendor_manifest_sha256': sha(a.vendor_manifest), 'archive_sha256': manifest['archive_sha256'],
              'pre2026_manifest_sha256': sha(out / 'pre2026/manifest.json'), 'horizon_manifest_sha256': sha(out / 'through2026/manifest.json'),
              'all_old_quote_prefixes_identical': all(r['identical'] for r in comparison.values()), 'old_prefix_comparison': comparison,
              'data_versions_spliced': False, '2026_portfolio_returns_computed': False}
    write(out / 'preparation.json', result)
    print(json.dumps({'status': 'TWO_CAPPED_VIEWS_PREPARED', 'end': END, 'all_24_old_prefixes_identical': result['all_old_quote_prefixes_identical']}))


if __name__ == '__main__': main()
