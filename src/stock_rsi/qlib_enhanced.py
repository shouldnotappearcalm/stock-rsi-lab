"""Point-in-time Qlib enhanced-indexing strategy used by research scripts.

Qlib is intentionally an optional research dependency. Import this module only in
the separate Qlib environment documented under ``experiments/qlib``.
"""
import numpy as np
import pandas as pd

from qlib.backtest.decision import TradeDecisionWO
from qlib.contrib.strategy.signal_strategy import EnhancedIndexingStrategy
from qlib.data import D
from qlib.utils import get_pre_trading_date


_OPTIMIZER_AUDIT_EVENTS = []


def pop_optimizer_audit_events():
    """Return and clear solver diagnostics from the current process."""
    events = list(_OPTIMIZER_AUDIT_EVENTS)
    _OPTIMIZER_AUDIT_EVENTS.clear()
    return events


class AuditedEnhancedIndexingOptimizer:
    """Solve every registered constraint or fail the run.

    Qlib's upstream optimizer retries without its turnover constraint when ECOS does
    not return ``optimal``. That fallback makes the contract data-dependent. This
    variant uses CLARABEL with explicit tolerances and checks the resulting weights;
    it never removes a constraint or silently returns an unverified portfolio.
    """

    def __init__(self, lamb=1.0, delta=0.2, b_dev=0.01, f_dev=None,
                 scale_return=True, epsilon=5e-5, constraint_tolerance=1e-4):
        if lamb < 0 or delta is None or delta < 0 or b_dev is not None and b_dev < 0:
            raise ValueError("invalid optimizer constraint")
        self.lamb = float(lamb)
        self.delta = float(delta)
        self.b_dev = None if b_dev is None else float(b_dev)
        self.f_dev = None if f_dev is None else np.asarray(f_dev, dtype=float)
        self.scale_return = bool(scale_return)
        self.epsilon = float(epsilon)
        self.constraint_tolerance = float(constraint_tolerance)

    def __call__(self, r, F, cov_b, var_u, w0, wb, mfh=None, mfs=None):
        import cvxpy as cp

        r = np.asarray(r, dtype=float)
        F = np.asarray(F, dtype=float)
        cov_b = np.asarray(cov_b, dtype=float)
        var_u = np.asarray(var_u, dtype=float)
        w0 = np.asarray(w0, dtype=float)
        wb = np.asarray(wb, dtype=float)
        if not all(np.isfinite(value).all() for value in (r, F, cov_b, var_u, w0, wb)):
            raise RuntimeError("optimizer received nonfinite input")
        if self.scale_return:
            standard_deviation = r.std()
            if standard_deviation <= 0:
                raise RuntimeError("signal has zero cross-sectional dispersion")
            r = r / standard_deviation
            variance_scale = np.mean(np.diag(F @ cov_b @ F.T) + var_u)
            if not np.isfinite(variance_scale) or variance_scale <= 0:
                raise RuntimeError("risk model has invalid variance scale")
            r *= np.sqrt(variance_scale)

        weight = cp.Variable(len(r), nonneg=True)
        weight.value = wb
        deviation = weight - wb
        factor_deviation = deviation @ F
        risk = cp.quad_form(factor_deviation, cp.psd_wrap(cov_b))
        risk += cp.sum(cp.multiply(var_u, cp.square(deviation)))
        objective = cp.Maximize(deviation @ r - self.lamb * risk)

        lower = np.zeros_like(wb)
        upper = np.ones_like(wb)
        if self.b_dev is not None:
            lower = np.maximum(lower, wb - self.b_dev)
            upper = np.minimum(upper, wb + self.b_dev)
        if mfh is not None:
            lower[mfh] = w0[mfh]
            upper[mfh] = w0[mfh]
        if mfs is not None:
            lower[mfs] = 0
            upper[mfs] = 0

        constraints = [cp.sum(weight) == 1, weight >= lower, weight <= upper]
        if self.f_dev is not None:
            constraints.extend([factor_deviation >= -self.f_dev, factor_deviation <= self.f_dev])
        turnover_applies = w0.sum() > 0
        if turnover_applies:
            constraints.append(cp.norm(weight - w0, 1) <= self.delta)
        problem = cp.Problem(objective, constraints)
        problem.solve(
            solver=cp.CLARABEL,
            max_iter=1000,
            tol_gap_abs=1e-9,
            tol_gap_rel=1e-9,
            tol_feas=1e-9,
        )
        if problem.status not in ("optimal", "optimal_inaccurate") or weight.value is None:
            raise RuntimeError(f"constrained optimizer failed: {problem.status}")

        solved = np.asarray(weight.value, dtype=float).reshape(-1)
        solved[solved < self.epsilon] = 0
        if not np.isfinite(solved).all() or solved.sum() <= 0:
            raise RuntimeError("constrained optimizer returned invalid weights")
        solved = np.maximum(solved, 0)
        solved /= solved.sum()
        violations = {
            "sum": abs(float(solved.sum()) - 1.0),
            "lower": float(np.maximum(lower - solved, 0).max(initial=0)),
            "upper": float(np.maximum(solved - upper, 0).max(initial=0)),
        }
        turnover = float(np.abs(solved - w0).sum()) if turnover_applies else None
        if turnover_applies:
            violations["turnover"] = max(turnover - self.delta, 0.0)
        if self.f_dev is not None:
            actual_factor_deviation = (solved - wb) @ F
            violations["factor"] = float(
                np.maximum(np.abs(actual_factor_deviation) - self.f_dev, 0).max(initial=0)
            )
        maximum_violation = max(violations.values())
        if maximum_violation > self.constraint_tolerance:
            raise RuntimeError(
                f"constrained optimizer produced violation {maximum_violation:.12g}: {violations}"
            )
        _OPTIMIZER_AUDIT_EVENTS.append({
            "solver": "CLARABEL", "status": problem.status,
            "turnover": turnover, "max_constraint_violation": maximum_violation,
        })
        return solved


def iso_week_key(value):
    """Return a stable key so the first available session in a week rebalances."""
    iso = pd.Timestamp(value).isocalendar()
    return int(iso.year), int(iso.week)


class WeeklyCachedEnhancedIndexingStrategy(EnhancedIndexingStrategy):
    """Enhanced indexing with weekly decisions and point-in-time market caches.

    The upstream strategy repeatedly reads all instruments for every session. This
    implementation loads the permitted development interval once and rebalances on
    the first trading session of each ISO week. Risk data and benchmark weights are
    always read at ``pre_date``; the trade-date close is never used to size an order.
    """

    _shared_market_caches = {}

    def __init__(self, *, cache_start, cache_end, optimizer_kwargs=None,
                 latest_permitted_date="2025-12-30", **kwargs):
        optimizer_kwargs = dict(optimizer_kwargs or {})
        super().__init__(optimizer_kwargs=optimizer_kwargs, **kwargs)
        self.optimizer = AuditedEnhancedIndexingOptimizer(**optimizer_kwargs)
        self.cache_start = pd.Timestamp(cache_start)
        self.cache_end = pd.Timestamp(cache_end)
        self.latest_permitted_date = pd.Timestamp(latest_permitted_date)
        if self.cache_end > self.latest_permitted_date:
            raise ValueError("cache exceeds explicit permitted date")
        if self.cache_start > self.cache_end:
            raise ValueError("cache_start must not follow cache_end")
        self._last_rebalance_week = None
        self._market_cache = None

    def _ensure_market_cache(self):
        if self._market_cache is not None:
            return
        key = (self.market, self.cache_start, self.cache_end)
        if key in self._shared_market_caches:
            self._market_cache = self._shared_market_caches[key]
            return
        raw = D.features(
            D.instruments("all"),
            [f"${self.market}_weight", "$volume"],
            start_time=self.cache_start,
            end_time=self.cache_end,
        )
        cache = {
            "benchmark": raw[f"${self.market}_weight"].unstack("instrument"),
            "volume": raw["$volume"].unstack("instrument"),
        }
        self._shared_market_caches[key] = cache
        self._market_cache = cache

    def generate_trade_decision(self, execute_result=None):
        trade_step = self.trade_calendar.get_trade_step()
        trade_start_time, _ = self.trade_calendar.get_step_time(trade_step)
        week_key = iso_week_key(trade_start_time)
        if week_key == self._last_rebalance_week:
            return TradeDecisionWO([], self)
        self._last_rebalance_week = week_key
        return super().generate_trade_decision(execute_result)

    def generate_target_weight_position(self, score, current, trade_start_time, trade_end_time):
        self._ensure_market_cache()
        pre_date = get_pre_trading_date(trade_start_time, future=True)
        if pre_date > self.cache_end or pre_date > self.latest_permitted_date:
            raise ValueError(f"market snapshot exceeds registered cache end: {pre_date:%Y-%m-%d}")
        outs = self.get_risk_data(pre_date)
        if outs is None:
            self.logger.warning(f"no risk data for {pre_date:%Y-%m-%d}, skip optimization")
            return None
        factor_exp, factor_cov, specific_risk, universe, blacklist = outs
        score_values = score.reindex(universe).fillna(score.min()).values

        current_weight = current.get_stock_weight_dict(only_stock=False)
        current_weight = np.array([current_weight.get(stock, 0) for stock in universe])
        if not np.all(current_weight >= 0):
            raise ValueError("long-only strategy received negative current weight")
        current_weight = current_weight / self.get_risk_degree(trade_start_time)

        try:
            benchmark = self._market_cache["benchmark"].loc[pre_date]
            volume = self._market_cache["volume"].loc[pre_date]
        except KeyError:
            self.logger.warning(f"no cached market snapshot for {pre_date:%Y-%m-%d}")
            return None
        benchmark_weight = benchmark.reindex(universe).fillna(0).values
        tradable = volume.reindex(universe).gt(0).values
        force_sell = np.array([stock in blacklist for stock in universe], dtype=bool)

        weight = self.optimizer(
            r=score_values,
            F=factor_exp,
            cov_b=factor_cov,
            var_u=specific_risk**2,
            w0=current_weight,
            wb=benchmark_weight,
            mfh=~tradable,
            mfs=force_sell,
        )
        return {stock: value for stock, value in zip(universe, weight) if value > 0}
