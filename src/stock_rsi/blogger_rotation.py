"""Independently abstracted fixed blogger rules; no execution or future records."""
from fractions import Fraction
import math

NAMES=('fengji20','fengji_mean','plus2047')
FUNDS=('SH518880','SZ159915','SH510050','SH510300','SH510500')
SIGNAL_MAP={'SH000016':'SH510050','SH000300':'SH510300','SH000905':'SH510500'}


def evaluate(config,histories,owned):
    name=config['id']
    if name not in NAMES:raise ValueError('fixed blogger cohort only')
    if set(histories)!=set(config['signal_symbols']):raise ValueError('all declared histories required')
    held=[c for c,q in owned.items() if q>0]
    if len(held)>1 or any(c not in config['symbols'] for c in held):raise ValueError('single declared fund inventory required')
    scores={}
    for c,values in histories.items():
        if len(values)!=config['history'] or any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in values):
            raise ValueError('exact complete positive visible history required')
        p=[Fraction(str(x)) for x in values]
        base=sum(p[:3],Fraction(0))/3 if name=='fengji_mean' else p[0]
        scores[c]=p[-1]/base-1
    leader=None;reason='CASH_NO_POSITIVE_LEADER'
    if name=='plus2047':
        if held:
            signal=next(k for k,v in SIGNAL_MAP.items() if v==held[0])
            if scores[signal]>0:leader=held[0];reason='KEEP_HELD_OWN_MOMENTUM_POSITIVE'
            else:reason='EXIT_HELD_OWN_MOMENTUM_NONPOSITIVE'
        else:
            for signal in config['signal_symbols']:
                if scores[signal]>0 and all(scores[signal]-v>Fraction(1,100) for k,v in scores.items() if k!=signal):
                    leader=SIGNAL_MAP[signal];reason='FLAT_STRICT_ONE_PERCENTAGE_POINT_LEADER';break
    else:
        maximum=max(scores.values())
        if maximum>0:
            tied=[c for c in config['symbols'] if scores[c]==maximum]
            leader=held[0] if held and held[0] in tied else tied[0];reason='POSITIVE_RELATIVE_LEADER'
    return {'leader':leader,'reason':reason,'scores':{k:float(v) for k,v in scores.items()},
            'scores_exact_ratio':{k:[str(v.numerator),str(v.denominator)] for k,v in scores.items()}}


def development_pass(metric):
    for y in ('2024_return_pct','2025_return_pct'):
        if type(metric.get(y)) not in (int,float) or not math.isfinite(metric[y]):raise ValueError('finite complete annual metrics required')
    return metric['2024_return_pct']>0 and metric['2025_return_pct']>0 and metric['unverified_held_marks']==0
