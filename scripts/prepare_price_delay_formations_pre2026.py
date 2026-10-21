"""Frozen single-candidate formations in a physically pre2026 provider only."""
import argparse
import json
from pathlib import Path

from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from scripts.run_qlib_low_risk_pre2026 import input_hashes, parse_memberships
from stock_rsi.price_delay import START, END, build_targets
from stock_rsi.qlib_snapshot import QlibSnapshot

METHOD_FILES = ('scripts/prepare_price_delay_formations_pre2026.py', 'src/stock_rsi/price_delay.py',
    'src/stock_rsi/prior_close_orders.py', 'src/stock_rsi/qlib_snapshot.py',
    'scripts/run_qlib_low_risk_pre2026.py', 'scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/prepare_qlib_master_market_pre2026.py')
DESIGN = 'docs/research/price-delay-pre2026-design-2026-10-21.md'


def main():
    p = argparse.ArgumentParser()
    for n in ('provider-uri', 'request', 'expected-request-sha256', 'output-dir'):
        p.add_argument('--'+n, required=True)
    a = p.parse_args(); provider, out = Path(a.provider_uri), Path(a.output_dir); repo = Path(__file__).resolve().parents[1]
    if out.exists() or sha256_file(a.request) != a.expected_request_sha256:
        raise ValueError('preserve previous outputs; externally frozen request required')
    r = json.loads(Path(a.request).read_bytes())
    if (r['status'] != 'FROZEN_SINGLE_DELAY_PRE2026_FORMATIONS_ONLY' or r['candidate_budget'] != 1
        or r['window'] != [START, END] or set(r['method_code_sha256']) != set(METHOD_FILES)
        or r['design_sha256'] != sha256_file(repo/DESIGN)):
        raise ValueError('registered single-delay formation rules changed')
    for n, h in r['method_code_sha256'].items():
        if sha256_file(repo/n) != h: raise ValueError('frozen formation code changed')
    if sha256_file(provider/'manifest.json') != r['provider_manifest_sha256']:
        raise ValueError('physical provider manifest changed')
    manifest = json.loads((provider/'manifest.json').read_bytes())
    if manifest['all_output_values_at_or_before'] != END or manifest['output_calendar_end'] != END:
        raise ValueError('physical provider must end2025')
    for n, v in manifest['per_feature'].items():
        if Path(n).is_absolute() or '..' in Path(n).parts or sha256_file(provider/n) != v['sha256'] or v['last_date'] > END:
            raise ValueError('capped feature identity or extent changed')
    memberships = parse_memberships((provider/'instruments/csi500.txt').read_text())
    if input_hashes(provider, memberships) != r['input_sha256']:
        raise ValueError('complete physical pre2026 source changed')
    snapshot = QlibSnapshot(provider)
    if snapshot.calendar[-1].isoformat() != END:
        raise ValueError('date interface contains future sessions')
    out.mkdir(parents=True)
    try:
        targets, receipts = build_targets(snapshot, memberships)
        if len(receipts) != 24 or any(v['latest_measurement_price_read'] > v['measurement_cap']
                or v['latest_formation_price_read'] != v['formation_asof'] for v in receipts):
            raise ValueError('all24 dated formations and strict measurement lag required')
        for name, value in (('targets.json', targets), ('formation_receipts.json', receipts)):
            (out/name).write_text(json.dumps(value, indent=2)+'\n')
        summary = {'status': 'SINGLE_DELAY_PRE2026_FORMATIONS_PREPARED_NO_RETURNS',
            'request_sha256': a.expected_request_sha256, 'provider_manifest_sha256': r['provider_manifest_sha256'],
            'input_sha256': r['input_sha256'], 'formations': len(receipts), 'candidate_budget': 1,
            'eligible_range': [min(v['eligible'] for v in receipts), max(v['eligible'] for v in receipts)],
            'market_paired_weeks_range': [min(v['market_paired_weeks'] for v in receipts), max(v['market_paired_weeks'] for v in receipts)],
            'artifact_sha256': {n: sha256_file(out/n) for n in ('targets.json', 'formation_receipts.json')},
            'source_queries': 0, '2026_market_values_queried': False, 'portfolio_returns_computed': False,
            'historical_arrival_verified': False, 'objective_achieved': False}
        (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print('24 lagged formations prepared; eligible', summary['eligible_range'], 'no portfolioROI', flush=True)
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps({'error_type': type(exc).__name__, 'error': str(exc),
            'request_sha256': a.expected_request_sha256, 'portfolio_returns_computed': False,
            '2026_market_values_queried': False, 'candidate_promoted': False}, indent=2)+'\n')
        raise


if __name__ == '__main__': main()
