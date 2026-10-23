"""Conditional native-f32 cents and integer shares; ignored branches stay opaque."""
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo
import json,re
from stock_rsi.tencent_history import JsonSlices,NUMBER,START,END,need
from stock_rsi.float32_quote_bounds import cell,ceil,floor

TICKERS={'SH600118':'600118.SS','SZ002326':'002326.SZ'}
FIELDS=('open','close','high','low','volume')

def price(token):
    need(type(token) is bytes and len(token)<=128 and NUMBER.fullmatch(token) is not None,'bounded numeric price token')
    value=Decimal(token.decode('ascii'));need(value.is_finite() and value>0 and abs(value.adjusted())<=40,'positive bounded price exponent')
    exact=Fraction(value);cents=exact*100
    if cents.denominator==1:n=cents.numerator
    else:
        native=float(token);need(Decimal(repr(native))==value,'shortest native float token; no lost decimal tails')
        lo,hi=cell(native);first,last=ceil(lo*100),floor(hi*100)
        need(first==last and first>0,'one positive cent in native-f32 cell');n=first
    return f'{n//100}.{n%100:02d}'

def decode(body,code,sessions,on_row=None,prefix_rows=None):
    need(prefix_rows is None or type(prefix_rows) is int and prefix_rows>=0,'explicit nonnegative durable prefix')
    if prefix_rows==0:return []
    need(code in TICKERS and sessions==sorted(set(sessions)) and all(START<=d<=END for d in sessions),'fixed code/sessions')
    s=JsonSlices(body);need(s.path(('chart','error'))==b'null','no Yahoo chart error')
    results=s.items(s.path(('chart','result')));need(len(results)==1,'one Yahoo result')
    s=JsonSlices(results[0]);need(json.loads(s.path(('meta','symbol')))==TICKERS[code]
        and json.loads(s.path(('meta','exchangeTimezoneName')))=='Asia/Shanghai','exact issuer/zone')
    timestamps=s.items(s.path(('timestamp',)));days=[];previous=None
    # Deliberately finish the entire timestamp pass before selecting quote arrays.
    for token in timestamps:
        need(re.fullmatch(rb'(?:0|[1-9][0-9]{0,10})',token) is not None,'integer bounded timestamp')
        stamp=int(token);local=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('Asia/Shanghai'));day=local.date().isoformat()
        need(START<=day<=END and day in sessions and local.strftime('%H:%M:%S')=='09:30:00'
            and (previous is None or day>previous),'all Yahoo timestamps in explicit ascending historical sessions')
        days.append(day);previous=day
    quotes=s.items(s.path(('indicators','quote')));need(len(quotes)==1,'one quote object');q=JsonSlices(quotes[0])
    arrays={k:q.items(q.path((k,))) for k in FIELDS};need(days and all(len(v)==len(days) for v in arrays.values()),'aligned nonempty historical quote arrays')
    count=len(days) if prefix_rows is None else prefix_rows;need(count<=len(days),'durable prefix inside source')
    rows=[]
    for i in range(count):
        values={k:price(arrays[k][i]) for k in FIELDS[:4]};v=arrays['volume'][i]
        need(re.fullmatch(rb'(?:0|[1-9][0-9]{0,29})',v) is not None,'nonnegative integer volume shares')
        o,c,h,l=(Decimal(values[k]) for k in FIELDS[:4]);need(l<=min(o,c)<=max(o,c)<=h,'Yahoo OHLC range')
        row={'date':days[i],**values,'volume_shares':str(int(v)),'amount_cny':None,
            'source_tokens':{k:arrays[k][i].decode('ascii') for k in FIELDS},'source_kind':'CONDITIONAL_NATIVE_F32_CENTS_INTEGER_SHARES_NOT_ACCOUNT'}
        if on_row:on_row(row)
        rows.append(row)
    return rows
