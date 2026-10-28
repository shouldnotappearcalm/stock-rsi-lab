"""Only cross-process original NAV comparison changes; forward prefix stays exact."""
from pathlib import Path
from unittest.mock import patch
from scripts import run_published_strategies_2026 as original
from scripts.published_replay_float_comparison import compare_original

BASE_RUN = original.run
BASE_COMPARE = original.compare_prefix


def run(root, data, old_run, request, expected, out):
    def compare(short, long):
        if Path(short).resolve().is_relative_to(Path(old_run).resolve()): return compare_original(short, long)
        return BASE_COMPARE(short, long)
    with patch.object(original, 'compare_prefix', compare):
        return BASE_RUN(root, data, old_run, request, expected, out)


def main():
    original.run = run
    original.NEW_METHODS = (*original.NEW_METHODS, 'scripts/published_replay_float_comparison.py',
        'scripts/run_published_strategies_2026_replay.py', 'scripts/audit_published_strategies_2026_replay.py',
        'tests/test_published_replay_float_comparison.py', 'docs/research/published-strategies-2026-replay-fix-2026-10-28.md')
    original.PROFILE = {**original.PROFILE, 'status': 'FROZEN_MACD_RSI_FORWARD_CROSS_PROCESS_REPLAY_CHECK',
        'original_replay_float_policy': 'NAV_WEIGHT_ONLY_8ULP_EXACT_MARKET_AND_TRADES',
        'same_process_baseline_forward_prefix_policy': 'EXACT_ALL_FIELDS_AND_SNAPSHOT_HASHES'}
    original.main()


if __name__ == '__main__': main()
