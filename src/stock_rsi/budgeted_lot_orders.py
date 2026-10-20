"""Prior-close lot allocation; improves target tracking within its notional budget.

This deterministic greedy heuristic is not a global integer optimizer. It does
not certify execution, fees, or cash availability at a future opening price.
"""
import math

from stock_rsi.prior_close_orders import plan_prior_close_orders


def plan_budgeted_lot_orders(equity, positions, weights, view):
    # Preserve established validation and unpriced known-inventory full exits.
    original = plan_prior_close_orders(equity, positions, weights, view)
    exits = [row for row in original if weights.get(row['instrument'], 0.) == 0]
    budget = equity * math.fsum(weights.values())
    tolerance = max(1e-8, equity * 1e-10)
    quotes, ideal, post, candidates = {}, {}, {}, []
    for code in sorted(c for c, w in weights.items() if w > 0):
        price = view.value(code, 'close', view.as_of.isoformat())
        factor = view.value(code, 'factor', view.as_of.isoformat())
        lot = 100 / factor
        desired = equity * weights[code] / price
        held = positions.get(code, 0.)
        if any(not math.isfinite(v) or v <= 0 for v in (price, factor, lot, desired, price * lot)):
            raise ValueError('finite positive lot valuation required')
        # Buy increments use one floor of the deficit, preserving existing odd
        # balances. Selling keeps the established target-floor convention.
        base = (held + math.floor((desired-held)/lot + 1e-10)*lot if desired >= held
                else math.floor(desired/lot + 1e-10)*lot)
        quotes[code] = (price, factor, lot)
        ideal[code], post[code] = desired, base
        proposed, action = base + lot, 'ONE_BUY_LOT'
        if desired < held:
            proposed = min(proposed, held)
            action = 'CANCEL_REMAINING_SELL' if proposed == held else 'REDUCE_SELL_ONE_LOT'
        cost = (proposed-base) * price
        shortfall = (desired-base) * price
        gain = cost * (2*shortfall-cost)
        if not math.isfinite(gain):
            raise ValueError('finite tracking error required')
        if cost > 0 and gain > 0:
            # Twelve significant digits prevent normalization roundoff from
            # deciding mathematical ties; the security code breaks those ties.
            priority = float(format(gain, '.12g'))
            candidates.append((priority, code, proposed, cost, gain, action))
    initial = math.fsum(post[c] * quotes[c][0] for c in post)
    if initial > budget + tolerance:
        raise ValueError('initial integer allocation exceeds target notional budget')
    before = math.fsum(((ideal[c]-post[c])*quotes[c][0])**2 for c in post)
    remaining = budget-initial
    steps = []
    for _, code, proposed, cost, gain, action in sorted(candidates, key=lambda r: (-r[0], r[1])):
        if cost > remaining + tolerance:
            continue
        steps.append({'instrument': code, 'normalized_units_added': proposed-post[code],
            'notional_added': cost, 'squared_error_reduction': gain, 'action': action})
        post[code] = proposed
        remaining -= cost
    orders = list(exits)
    for code in sorted(post):
        price, factor, lot = quotes[code]
        held = positions.get(code, 0.)
        difference = post[code]-held
        if abs(difference) <= 1e-8 * max(1., held, post[code]):
            continue
        if difference > 0:
            raw_lots = difference/lot
            if not math.isclose(raw_lots, round(raw_lots), rel_tol=1e-10, abs_tol=1e-8):
                raise ValueError('buy increment is not a whole lot')
        orders.append({'instrument': code, 'side': 'BUY' if difference > 0 else 'SELL',
            'normalized_units': abs(difference), 'known_normalized_close': price,
            'known_factor': factor, 'as_of': view.as_of.isoformat(),
            'quantity_basis': 'PRIOR_CLOSE_BUDGETED_LOT_TARGET'})
    final = math.fsum(post[c]*quotes[c][0] for c in post)
    after = math.fsum(((ideal[c]-post[c])*quotes[c][0])**2 for c in post)
    if (not all(math.isfinite(v) for v in (budget, initial, final, before, after))
            or final > budget+tolerance or after > before+max(1e-8, before*1e-10)):
        raise ValueError('allocation budget/tracking conservation failed')
    receipt = {'as_of': view.as_of.isoformat(), 'target_notional_budget': budget,
        'initial_planned_notional': initial, 'final_planned_notional': final,
        'unallocated_notional_budget': budget-final,
        'squared_tracking_error_before': before, 'squared_tracking_error_after': after,
        'post_order_normalized_positions': post, 'allocation_steps': steps,
        'execution_prices_or_returns_used': False, 'future_cash_or_fill_guaranteed': False}
    return tuple(sorted(orders, key=lambda r: (r['side'] != 'SELL', r['instrument']))), receipt
