"""Monthly signal and annual target execution with prior-close cash only."""
from fractions import Fraction
import math

NAMES=('faber10','glaozi50');STOCK,BOND='SH510050','SH511010'

def month_ends(history):
    months={};previous=''
    for d,v in history:
        if d<=previous or type(v) not in (int,float) or not math.isfinite(v) or v<=0:raise ValueError('ordered complete positive visible history required')
        months[d[:7]]=[d,v];previous=d
    if len(months)<10:raise ValueError('ten complete month observations required')
    return list(months.values())[-10:]

def monthly_regime(monthly,previous):
    if len(monthly)!=10 or previous not in (None,True,False):raise ValueError('ten monthly closes and prior state required')
    prices=[Fraction(str(v)) for _,v in monthly]
    if min(prices)<=0:raise ValueError('positive monthly closes required')
    mean=sum(prices)/10;diff=prices[-1]-mean
    return (True if diff>0 else False if diff<0 else bool(previous)),{'ma10':float(mean),'close':float(prices[-1]),'difference_exact':[str(diff.numerator),str(diff.denominator)]}

def lot_floor(q,factor):
    if not math.isfinite(q) or q<0 or not math.isfinite(factor) or factor<=0:raise ValueError('finite positive factor and nonnegative quantity required')
    n=math.floor(q*factor/100);result=n*100/factor
    return max(0,n-1)*100/factor if result>q else result

def annual_targets(equity,closes,factors):
    if not math.isfinite(equity) or equity<=0 or set(closes)!={STOCK,BOND} or set(factors)!=set(closes):raise ValueError('solvent actual account and both declared assets required')
    if any(not math.isfinite(v) or v<=0 for v in [*closes.values(),*factors.values()]):raise ValueError('positive known prices and factors required')
    return {c:lot_floor(.475*equity/closes[c],factors[c]) for c in (STOCK,BOND)}

def annual_orders(targets,equity,cash,owned,closes,factors,extra):
    if equity<=0 or set(targets)!={STOCK,BOND} or set(closes)!=set(targets) or set(factors)!=set(targets) or set(owned)-set(targets) or any(not math.isfinite(v) or v<0 for v in [equity,cash,*targets.values(),*owned.values()]):raise ValueError('declared finite long-only actual inventory and targets required')
    if extra not in (20,40):raise ValueError('fixed cost scenarios required')
    if any(not math.isfinite(v) or v<=0 for v in [*closes.values(),*factors.values()]):raise ValueError('positive prior marks required')
    sells=[]
    for c in (STOCK,BOND):
        q=lot_floor(max(0,owned.get(c,0)-targets[c]),factors[c])
        if q>0:sells.append({'instrument':c,'side':'SELL','normalized_units':q})
    if sells:return sells
    remaining=max(0,cash-.05*equity);orders=[];rate=(5+extra)/10000
    for c in (STOCK,BOND):
        deficit=max(0,targets[c]-owned.get(c,0));budget=max(0,min(deficit*closes[c],remaining/(1+rate),remaining-5))
        q=lot_floor(budget/closes[c],factors[c])
        if q>0:
            value=q*closes[c];cost=max(5,value*rate)
            if value+cost>remaining+1e-8:raise ValueError('planned fees and quantities exceed known cash')
            orders.append({'instrument':c,'side':'BUY','normalized_units':q});remaining-=value+cost
    return orders
