"""Fixed two-author daily hypotheses, evaluated on completed visible bars only."""
import math

NAMES=('alvarez2','marwood10')
CODE='SH510050'

def rsi2(values):
    if len(values)<3:raise ValueError('two changes required')
    changes=[b-a for a,b in zip(values,values[1:])]
    up=sum(max(d,0.) for d in changes[:2])/2;down=sum(max(-d,0.) for d in changes[:2])/2
    for d in changes[2:]:up=(up+max(d,0.))/2;down=(down+max(-d,0.))/2
    return 100*up/(up+down) if up+down else 0.

def evaluate(name,values,held,*,low=None,entry_price=None,exit_latched=False):
    if name not in NAMES or type(held)!=bool or type(exit_latched)!=bool:raise ValueError('declared rule and typed state required')
    if len(values)<200 or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('at least200 finite positive completed closes required')
    last=values[-1];detail={'close':last}
    if name=='alvarez2':
        rsi=rsi2(values);down2=values[-1]<values[-2]<values[-3]
        buy=rsi<5 and down2;sell=rsi>50;detail.update(rsi2=rsi,two_strict_down_closes=down2)
    else:
        if low is None or not math.isfinite(low) or low<=0 or low>last:raise ValueError('completed session low required')
        if held and (entry_price is None or not math.isfinite(entry_price) or entry_price<=0):raise ValueError('actual filled entry price required')
        ma200=math.fsum(values[-200:])/200;ma10=math.fsum(values[-10:])/10
        stop=held and low<=entry_price*.9
        buy=last>ma200 and last<ma10;sell=last>ma10 or stop
        detail.update(ma200=ma200,ma10=ma10,low=low,actual_entry_price=entry_price,stop_touched=stop)
    action='SELL' if held and (exit_latched or sell) else 'BUY' if not held and buy else 'HOLD'
    return {'action':action,'leader':CODE if action=='BUY' or held and action!='SELL' else None,'details':detail}
