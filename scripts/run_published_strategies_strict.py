"""V3: unchanged source signals, actual clock, conservative execution rounding."""
from unittest.mock import patch
from scripts import run_published_strategies as original
from scripts.run_published_strategies_clock import validate_clock


def strict_simulation(provider, config, extra, out):
    import qlib.backtest as engine
    from stock_rsi.strict_qlib_exchange import StrictRequestedQuantityExchange
    native_backtest = engine.backtest
    def bounded_backtest(*args, **kwargs):
        exchange_kwargs = dict(kwargs['exchange_kwargs'])
        # Construct after the original simulator calls qlib.init; preserve all
        # prices, costs, limit filters and account settings from that simulator.
        exchange_kwargs['exchange'] = StrictRequestedQuantityExchange(**exchange_kwargs)
        kwargs['exchange_kwargs'] = exchange_kwargs
        return native_backtest(*args, **kwargs)
    with patch.object(engine, 'backtest', bounded_backtest):
        return BASE_SIMULATE(provider, config, extra, out)


BASE_SIMULATE = original.simulate


def main():
    prior_bindings = original.bindings
    def bindings(root, provider):
        validate_clock(provider)
        return prior_bindings(root, provider)
    original.bindings = bindings
    original.simulate = strict_simulation
    original.METHODS = (*original.METHODS, 'scripts/run_published_strategies_clock.py',
        'scripts/prepare_published_strategy_clock.py', 'scripts/prepare_price_delay_clock_pre2026.py',
        'tests/test_published_strategy_clock.py', 'docs/research/published-strategies-clock-fix-2026-10-28.md',
        'scripts/run_published_strategies_strict.py', 'src/stock_rsi/strict_qlib_exchange.py',
        'scripts/audit_published_strategy_execution.py', 'tests/test_published_strategy_execution.py',
        'tests/test_strict_qlib_exchange.py', 'docs/research/published-strategies-execution-fix-2026-10-28.md')
    original.PROFILE = {**original.PROFILE, 'status': 'FROZEN_THREE_2017_RECIPES_STRICT_REQUEST_QUANTITY',
        'previous_clock_request_sha256': 'a7fb7b4df7da7a906e6fc050421ec0b2dc32e2c2024d6fd56714e852fcc8cbf6',
        'execution_rounding': 'STRICT_FLOOR_NEVER_ADD_PRECISION_SHARES', 'actual_next_session_clock_only': True}
    original.main()


if __name__ == '__main__': main()
