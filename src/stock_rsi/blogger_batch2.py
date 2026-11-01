"""Two predeclared single-ETF rules, with visible-history-only calculations."""
import math

NAMES=('bigquant20','rayner10');CODE='SH510050'

def rsi10(values):
    if len(values)<11:raise ValueError('ten price changes required')
    changes=[b-a for a,b in zip(values,values[1:])];gain=sum(max(v,0.) for v in changes[:10])/10;loss=sum(max(-v,0.) for v in changes[:10])/10
    result=[100*gain/(gain+loss) if gain+loss else 0.]
    for d in changes[10:]:
        gain=(gain*9+max(d,0.))/10;loss=(loss*9+max(-d,0.))/10
        result.append(100*gain/(gain+loss) if gain+loss else 0.)
    return result

def evaluate(name,values,held,holding_sessions=0,exit_latched=False):
    if name not in NAMES or type(held)!=bool or type(exit_latched)!=bool or type(holding_sessions)!=int or holding_sessions<0:raise ValueError('fixed rule and typed actual holding state required')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('finite positive completed closes required')
    if name=='bigquant20':
        if len(values)!=20:raise ValueError('exact20 completed closes required')
        high=max(values);low=min(values[-10:]);buy=not held and values[-1]>=high;sell=held and values[-1]<=low
        detail={'upper20':high,'lower10':low,'close':values[-1]}
    else:
        if len(values)<200:raise ValueError('complete200SMA and fixed-origin Wilder history required')
        mean=sum(values[-200:])/200;rsis=rsi10(values);value=rsis[-1]
        buy=not held and values[-1]>mean and value<30;sell=held and (exit_latched or value>40 or holding_sessions>=10)
        detail={'ma200':mean,'rsi10':value,'previous_rsi10':rsis[-2],'close':values[-1]}
    action='SELL' if sell else 'BUY' if buy else 'HOLD'
    return {'action':action,'leader':CODE if buy or held and not sell else None,'details':detail}
