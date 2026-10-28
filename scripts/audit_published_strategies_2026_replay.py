"""Same-source forward QA, narrow original-process comparison, exact forward prefix."""
from pathlib import Path
from unittest.mock import patch
from scripts import audit_published_strategies_2026 as original
from scripts.published_replay_float_comparison import compare_original

BASE_AUDIT = original.audit
BASE_PREFIX = original.assert_prefix


def audit(root, data, old_run, request, expected, folder):
    comparisons = []
    def compare(short, long):
        if Path(short).resolve().is_relative_to(Path(old_run).resolve()): comparisons.append(compare_original(short, long))
        else: BASE_PREFIX(short, long)
    with patch.object(original, 'assert_prefix', compare):
        result = BASE_AUDIT(root, data, old_run, request, expected, folder)
    return {**result, 'original_cross_process_comparisons': comparisons, 'same_version_forward_historical_prefix_exact': True}


def main():
    original.audit = audit
    original.main()


if __name__ == '__main__': main()
