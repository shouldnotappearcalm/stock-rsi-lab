"""Add an actual next-session clock boundary to a fresh pre2026 quote copy."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil

from scripts.prepare_qlib_master_market_pre2026 import sha256_file


def clock_calendar(capped_text, source_text):
    def rows(text):
        values = text.splitlines()
        if (not values or text != '\n'.join(values)+'\n'
                or values != sorted(set(values))
                or any(date.fromisoformat(day).isoformat() != day for day in values)):
            raise ValueError('canonical actual session table required')
        return values
    capped, source = rows(capped_text), rows(source_text)
    if (capped[-1] != '2025-12-31' or len(source) <= len(capped)
            or source[:len(capped)] != capped):
        raise ValueError('unchanged pre2026 prefix and actual next session required')
    return '\n'.join(source[:len(capped)+1])+'\n'


def main():
    p = argparse.ArgumentParser()
    for key in ('provider-uri', 'source-calendar', 'request', 'expected-request-sha256', 'output-dir'):
        p.add_argument('--'+key, required=True)
    a = p.parse_args(); source = Path(a.provider_uri); out = Path(a.output_dir)
    if out.exists() or sha256_file(a.request) != a.expected_request_sha256:
        raise ValueError('frozen request and unused output required')
    request = json.loads(Path(a.request).read_text())
    if (request['status'] != 'FROZEN_PRE2026_QUOTES_ACTUAL_NEXT_SESSION_CLOCK_ONLY'
            or sha256_file(__file__) != request['method_sha256']
            or sha256_file(source/'manifest.json') != request['provider_manifest_sha256']
            or sha256_file(a.source_calendar) != request['source_calendar_sha256']):
        raise ValueError('frozen source or clock preparation changed')
    future = clock_calendar((source/'calendars/day.txt').read_text(), Path(a.source_calendar).read_text())
    if future.splitlines()[-1] != request['next_session']:
        raise ValueError('actual boundary session changed')
    original = json.loads((source/'manifest.json').read_text())
    if original['all_output_values_at_or_before'] != '2025-12-31':
        raise ValueError('physically capped quote source required')
    expected = set(original['per_feature']) | {'calendars/day.txt', 'instruments/all.txt', 'instruments/csi500.txt', 'manifest.json'}
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
    if actual != expected or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('only registered quote, instrument, calendar and manifest files allowed')
    for name, meta in original['per_feature'].items():
        if sha256_file(source/name) != meta['sha256']:
            raise ValueError('source quote identity changed')
    # Copy files, never link; leave the failed-run V1 provider untouched.
    shutil.copytree(source, out)
    identical = {name: sha256_file(source/name) for name in sorted(expected)}
    if any(sha256_file(out/name) != value for name, value in identical.items()):
        raise ValueError('copied files changed; retain partial output')
    (out/'calendars/day_future.txt').write_text(future)
    manifest = dict(original)
    manifest.update(status='PHYSICAL_PRE2026_QUOTES_WITH_ACTUAL_NEXT_SESSION_CLOCK_BOUNDARY',
        origin_manifest_sha256=request['provider_manifest_sha256'], clock_request_sha256=a.expected_request_sha256,
        copied_original_file_sha256=identical,
        clock_boundary={'session': request['next_session'], 'purpose': 'exclusive right boundary of final2025 daily bar only',
            'calendar_path': 'calendars/day_future.txt', 'sha256': sha256_file(out/'calendars/day_future.txt'),
            'source_calendar_sha256': request['source_calendar_sha256'], 'additional_quote_values': 0,
            'additional_simulated_sessions': 0})
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('4010 quote files unchanged; day calendar ends2025; clock-only next session', request['next_session'])


if __name__ == '__main__': main()
