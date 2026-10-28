"""V2 entry point: same frozen investments; validate clock-only source repair."""
import json
from pathlib import Path
from scripts import run_published_strategies as original
from scripts.prepare_price_delay_clock_pre2026 import clock_calendar
from scripts.prepare_published_strategy_data import sha


def validate_clock(provider):
    provider = Path(provider)
    manifest = json.loads((provider / 'manifest.json').read_text())
    if manifest['status'] != 'PUBLISHED_RECIPE_V2_ACTUAL_NEXT_SESSION_CLOCK_ONLY':
        raise ValueError('registered V2 clock-only provider required')
    clock = manifest['clock_boundary']; source = Path(clock['source_calendar'])
    day = (provider / 'calendars/day.txt').read_text()
    future = (provider / 'calendars/day_future.txt').read_text()
    if (sha(source) != clock['source_calendar_sha256'] or future != clock_calendar(day, source.read_text())
            or clock['session'] != future.splitlines()[-1]
            or clock['additional_quote_values'] != 0 or clock['additional_simulated_sessions'] != 0):
        raise ValueError('actual metadata-only boundary required')
    for name, expected in clock['original_output_sha256'].items():
        if name != 'calendars/day_future.txt' and sha(provider / name) != expected:
            raise ValueError('V1 quote or simulated session changed')


def main():
    previous_bindings = original.bindings
    def bindings(root, provider):
        validate_clock(provider)
        return previous_bindings(root, provider)
    original.bindings = bindings
    original.METHODS = (*original.METHODS, 'scripts/run_published_strategies_clock.py',
        'scripts/prepare_published_strategy_clock.py', 'scripts/prepare_price_delay_clock_pre2026.py',
        'tests/test_published_strategy_clock.py', 'docs/research/published-strategies-clock-fix-2026-10-28.md')
    original.PROFILE = {**original.PROFILE, 'status': 'FROZEN_THREE_2017_RECIPES_WITH_ACTUAL_NEXT_SESSION_CLOCK',
        'previous_failed_request_sha256': '076be09b09bf5943edfd1f685eecd19d1cf201b55d4e2ac2c53df4c8c79a41ea',
        'repair': 'DAY_FUTURE_METADATA_ONLY_NO_INVESTMENT_OR_PRICE_CHANGE'}
    original.main()


if __name__ == '__main__': main()
