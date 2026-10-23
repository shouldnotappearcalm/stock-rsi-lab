"""Native Sina rows: dates first; outside-window financial scalars stay opaque."""
from datetime import date
from decimal import Decimal
import json,re
from stock_rsi.tencent_history import JsonSlices,NUMBER,START,END,need,scale

FIELDS=('open','close','high','low','volume')

def number(token):
    need(type(token) is bytes and len(token)<=128,'bounded native numeric token')
    text=json.loads(token) if token.startswith(b'"') else token.decode('ascii')
    need(type(text) is str and text.isascii() and NUMBER.fullmatch(text.encode()) is not None,'plain native numeric scalar')
    value=Decimal(text);need(value.is_finite() and abs(value.adjusted())<=40,'finite bounded native numeric exponent');return value

def price(token):
    n=number(token);cents=scale(n,100);need(n>0 and cents==cents.to_integral_value(),'exact positive integer-cent native price');n=int(cents)
    return f'{n//100}.{n%100:02d}'

def select(body,code,sessions):
    need(code in ('SH600118','SZ002326') and sessions==sorted(set(sessions))
        and all(START<=d<=END and date.fromisoformat(d).isoformat()==d for d in sessions),'fixed issuer/explicit sessions')
    rows=JsonSlices.items(body);kept=[];previous=None
    for index,raw in enumerate(rows):
        s=JsonSlices(raw);day=json.loads(s.path(('day',)))
        need(type(day) is str and date.fromisoformat(day).isoformat()==day and (previous is None or day>previous),'all source dates canonical unique ascending');previous=day
        if START<=day<=END:
            need(day in sessions,'inside-window date is an explicit session');kept.append((index,day,raw))
    return kept

def decode(body,code,sessions,on_row=None,prefix_rows=None):
    need(prefix_rows is None or type(prefix_rows) is int and prefix_rows>=0,'explicit nonnegative durable prefix')
    if prefix_rows==0:return []
    selected=select(body,code,sessions);count=len(selected) if prefix_rows is None else prefix_rows
    need(count<=len(selected),'durable prefix inside selected history');result=[]
    for index,day,raw in selected[:count]:
        s=JsonSlices(raw);tokens={k:s.path((k,)) for k in FIELDS};values={k:price(tokens[k]) for k in FIELDS[:4]};volume=number(tokens['volume'])
        need(volume>=0 and volume==volume.to_integral_value(),'nonnegative integer native volume shares')
        o,c,h,l=(Decimal(values[k]) for k in FIELDS[:4]);need(l<=min(o,c)<=max(o,c)<=h,'native OHLC range')
        row={'date':day,**values,'volume_shares':str(int(volume)),'amount_cny':None,'source_index':index,
            'source_tokens':{k:v.decode('ascii') for k,v in tokens.items()},'source_kind':'NATIVE_SINA_CENTS_INTEGER_SHARES_NOT_ACCOUNT'}
        if on_row:on_row(row)
        result.append(row)
    return result
