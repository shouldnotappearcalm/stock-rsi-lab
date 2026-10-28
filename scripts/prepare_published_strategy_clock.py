"""V2 metadata-only Qlib clock repair; immutable V1 price prefixes preserved."""
import argparse
import json
from pathlib import Path
import shutil
from scripts.prepare_price_delay_clock_pre2026 import clock_calendar
from scripts.prepare_published_strategy_data import sha


def prepare(source, source_calendar, out):
    source, source_calendar, out = Path(source), Path(source_calendar), Path(out)
    if out.exists() or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('fresh physical copy required')
    original = json.loads((source / 'manifest.json').read_text())
    actual = {str(p.relative_to(source)): sha(p) for p in sorted(source.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    if actual != original['all_output_sha256']:
        raise ValueError('original V1 source prefixes changed')
    future = clock_calendar((source / 'calendars/day.txt').read_text(), source_calendar.read_text())
    shutil.copytree(source, out)
    (out / 'calendars/day_future.txt').write_text(future)
    for name, expected in actual.items():
        if name != 'calendars/day_future.txt' and sha(out / name) != expected:
            raise ValueError('clock repair changed a price, identity or simulated session')
    manifest = {**original, 'status': 'PUBLISHED_RECIPE_V2_ACTUAL_NEXT_SESSION_CLOCK_ONLY',
        'original_manifest_sha256': sha(source / 'manifest.json'),
        'clock_boundary': {'session': future.splitlines()[-1], 'additional_quote_values': 0,
            'additional_simulated_sessions': 0, 'source_calendar': str(source_calendar.resolve()),
            'source_calendar_sha256': sha(source_calendar), 'original_output_sha256': actual},
        'all_output_sha256': {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'manifest.json'}}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    p = argparse.ArgumentParser()
    for key in ('source', 'source-calendar', 'out'): p.add_argument('--' + key, required=True)
    a = p.parse_args(); result = prepare(a.source, a.source_calendar, a.out)
    print(json.dumps({'status': result['status'], 'next_session_clock_only': result['clock_boundary']['session'], 'additional_quote_values': 0}))


if __name__ == '__main__': main()
