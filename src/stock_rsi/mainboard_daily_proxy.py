"""Explicit ordinary/known-warning daily-open semantics, not auction liquidity."""
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
import re
from stock_rsi.broker import money
from stock_rsi.calendar import SHANGHAI
from stock_rsi.time import parse_time

def need(ok,why):
    if not ok:raise ValueError(why)

def cent(value):
    v=money(value);need(v>0 and v==v.quantize(Decimal('.01')),'positive cent-tick observed price required');return v

def execution_rows(day,bars,pending_orders,policy):
    need(type(day) is date and type(policy['simulated_warning_buy_agreement']) is bool and type(policy['warning_daily_buy_cap']) is int and policy['warning_daily_buy_cap']==500000,'explicit simulated warning access/cap profile')
    pending=[v for v in pending_orders if v['status']=='PENDING'];codes=sorted({v['security_id'] for v in pending});result=[]
    for code in codes:
        need(re.fullmatch(r'(?:SH60|SZ00)[0-9]{4}',code) is not None,'supported mainboard issuer required');row=bars[code]
        need(row['date']==day.isoformat() and row['tradestatus'] in ('0','1') and row['isST'] in ('0','1'),'explicit same-day market/warning states')
        item={'security_id':code,'trade_date':day.isoformat(),'suspended':row['tradestatus']=='0'}
        if item['suspended']:result.append(item);continue
        rate=Decimal('.10')
        if row['isST']=='1':
            p=policy['warnings'].get(code);need(p is not None and p['start']<=day.isoformat()<=p['end'] and p['published_on']<day.isoformat() and p['rate']=='0.05' and re.fullmatch('[a-f0-9]{64}',p['source_sha256']),'known warning issuer/date and primary5%rate required');rate=Decimal('.05');buy=0
            for v in pending:
                if v['security_id']!=code:continue
                need(v['action'] in ('BUY','SELL') and type(v['quantity']) is int and v['quantity']>0,'positive typed pending trade')
                eligible=parse_time(v['eligible_at']).astimezone(SHANGHAI);expiry=parse_time(v['expires_at']).astimezone(SHANGHAI) if v.get('expires_at') else None
                if v['action']=='BUY' and eligible.date()==day and (expiry is None or expiry>=eligible):buy+=v['quantity']
            need(not buy or policy['simulated_warning_buy_agreement'],'simulated warning buy agreement required');need(buy<=policy['warning_daily_buy_cap'],'warning eligible pending BUYcap exceeded')
        reference=cent(row['preclose']);opening=cent(row['open']);upper=(reference*(1+rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);lower=(reference*(1-rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        need(0<lower<upper and lower<=opening<=upper,'observed open outside supported cent-rounded band')
        item.update(open=str(opening),limit_up=str(upper),limit_down=str(lower));result.append(item)
    return result
