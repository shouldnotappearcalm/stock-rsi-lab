"""Copy only pre2026 byte prefixes for stocks fixed in a 2017 source recipe."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from stock_rsi.published_signals import SYMBOLS

FIELDS = ('open', 'high', 'low', 'close', 'volume', 'factor')
CODES = (*SYMBOLS, 'SH000905')
END = '2025-12-31'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(source, out):
    source, out = Path(source), Path(out)
    if out.exists():
        raise ValueError('fresh capped provider only')
    dates = (source / 'calendars/day.txt').read_text().splitlines()
    if dates != sorted(set(dates)) or any(len(d) != 10 for d in dates):
        raise ValueError('explicit ordered source sessions required')
    capped = [d for d in dates if d <= END]
    if not capped or capped[-1] != END:
        raise ValueError('source must contain actual final 2025 session; no invented sessions')
    last_index = len(capped) - 1
    selected = []
    for line in (source / 'instruments/all.txt').read_text().splitlines():
        code, first, last = line.split()
        if code.upper() in CODES and first <= END:
            selected.append((code.upper(), first, min(last, END)))
    if {x[0] for x in selected} != set(CODES):
        raise ValueError('all original source stock identities required')
    out.mkdir(parents=True)
    (out / 'calendars').mkdir(); (out / 'instruments').mkdir()
    (out / 'calendars/day.txt').write_text('\n'.join(capped) + '\n')
    # Future simulator clocks contain no additional sessions/quotes.
    (out / 'calendars/day_future.txt').write_text('\n'.join(capped) + '\n')
    (out / 'instruments/all.txt').write_text(''.join('\t'.join(x) + '\n' for x in sorted(selected)))
    receipts = {}
    for code in CODES:
        folder = out / 'features' / code.lower(); folder.mkdir(parents=True)
        for field in FIELDS:
            rel = 'features/' + code.lower() + '/' + field + '.day.bin'
            original = source / rel
            with original.open('rb') as stream:
                header = stream.read(4)
                if len(header) != 4:
                    raise ValueError('missing feature start')
                number = struct.unpack('<f', header)[0]; start = int(number)
                if number != start or not 0 <= start <= last_index:
                    raise ValueError('feature unavailable in development period')
                count = min(last_index - start + 1, original.stat().st_size // 4 - 1)
                prefix = header + stream.read(count * 4)
            if len(prefix) != 4 * (count + 1) or start + count - 1 > last_index:
                raise ValueError('malformed pre2026 source prefix')
            (out / rel).write_bytes(prefix)
            receipts[rel] = {'sha256': hashlib.sha256(prefix).hexdigest(), 'copied_values': count,
                             'last_source_date': dates[start + count - 1], 'source_prefix_bytes': len(prefix)}
    manifest = {'status': 'PHYSICAL_PRE2026_PUBLISHED_RECIPE_PREFIXES', 'source_root': str(source.resolve()),
                'end': END, 'symbols_from_2017_source': list(SYMBOLS), 'source_class': 'ARCHIVED_QLIB_ADJUSTED_DAILY_ENGINEERING_SAMPLE',
                '2026_quote_values_read': False, 'per_feature': receipts,
                'all_output_sha256': {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source', required=True); p.add_argument('--out', required=True); a = p.parse_args()
    result = prepare(a.source, a.out)
    print(json.dumps({'status': result['status'], 'end': result['end'], 'price_files': len(result['per_feature'])}))


if __name__ == '__main__':
    main()
