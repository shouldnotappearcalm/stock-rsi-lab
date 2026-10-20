"""Coordinate adapter for the frozen lot allocator; never a new sizing rule."""
from datetime import date
import math
from stock_rsi.broker import money
from stock_rsi.budgeted_lot_orders import plan_budgeted_lot_orders

# Above this bound a binary float cannot retain every physical share balance.
MAX_EXACT_SHARES=2**53-100


class RawPriorCloseView:
    def __init__(self,as_of,prices):
        if type(as_of) is not date:raise ValueError('explicit prior-close session required')
        self.as_of=as_of
        self._prices={}
        for code,value in prices.items():
            price=money(value)
            if price<=0 or price!=price.quantize(money('.01')) or not math.isfinite(float(price)):
                raise ValueError('finite positive raw cent price required')
            self._prices[code]=float(price)

    def value(self,code,field,day):
        if day!=self.as_of.isoformat() or field not in ('close','factor'):
            raise ValueError('only the fixed prior-close coordinate is visible')
        if code not in self._prices:raise ValueError('missing prior-close raw price')
        # One raw share is one unit; this is a coordinate identity, not an
        # observed cumulative adjustment factor or distribution entitlement.
        return self._prices[code] if field=='close' else 1.


def plan_budgeted_raw_targets(equity,positions,weights,prices,as_of):
    equity=money(equity);weights={code:money(w) for code,w in weights.items()}
    if (equity<=0 or not math.isfinite(float(equity)) or not weights
            or any(w<0 for w in weights.values()) or sum(weights.values())>1
            or any(type(q) is not int or not 0<=q<=MAX_EXACT_SHARES for q in positions.values())):
        raise ValueError('finite long-only equity, weights and exact integer inventory required')
    view=RawPriorCloseView(as_of,prices)
    for code,weight in weights.items():
        if weight>0:
            view.value(code,'close',as_of.isoformat())
            if equity*weight/money(prices[code])>MAX_EXACT_SHARES:
                raise ValueError('target shares exceed exact float-coordinate integer bound')
    rows,receipt=plan_budgeted_lot_orders(float(equity),positions,{c:float(w) for c,w in weights.items()},view)
    orders=[]
    for row in rows:
        quantity=row['normalized_units']
        if not math.isfinite(quantity) or quantity<=0 or quantity!=int(quantity) or quantity>MAX_EXACT_SHARES:
            raise ValueError('allocator output is not an exactly representable integer share quantity')
        if row['side']=='BUY' and int(quantity)%100:
            raise ValueError('allocator buy is not a physical100-share increment')
        orders.append((row['side'],row['instrument'],int(quantity)))
    # The normalized planner has relative float tolerances. Reconstruct its
    # claimed post-allocation using only physical orders, then fail closed if a
    # tolerance suppressed a real share/lot or the receipt lost integer precision.
    realized=dict(positions)
    for side,code,quantity in orders:
        realized[code]=realized.get(code,0)+(quantity if side=='BUY' else -quantity)
        if realized[code]<0:raise ValueError('physical order sells more than known inventory')
    planned=receipt['post_order_normalized_positions']
    if (any(not math.isfinite(q) or q<0 or q!=int(q) or q>MAX_EXACT_SHARES for q in planned.values())
            or any(realized.get(c,0)!=planned.get(c,0) for c in set(realized)|set(planned))):
        raise ValueError('allocation receipt differs from emitted physical orders')
    return tuple(orders),{**receipt,'coordinate_basis':'ONE_UNIT_EQUALS_ONE_RAW_SHARE',
        'observed_adjustment_factor_used':False,'physical_integer_orders':True}
