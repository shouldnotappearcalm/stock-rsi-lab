"""Local five-minute observations from verified, cached minute snapshots."""
from datetime import timedelta
from decimal import Decimal
from stock_rsi.calendar import SHANGHAI
from stock_rsi.data import digest
from stock_rsi.time import iso,parse_time


def aggregate_minutes(code,day,points):
    labels=[f'{hour:02d}:{minute:02d}' for hour in (9,10,11,13,14,15) for minute in range(60)
            if '09:31'<=f'{hour:02d}:{minute:02d}'<='11:30' or '13:01'<=f'{hour:02d}:{minute:02d}'<='15:00']
    if not isinstance(points,list) or len(points)!=240:raise ValueError("complete minute series required")
    for point,label in zip(points,labels):
        at=parse_time(point['time']).astimezone(SHANGHAI)
        if at.date()!=day or at.strftime('%H:%M')!=label or at.second:
            raise ValueError("minute observation clock changed")
        if type(point['volume']) is not int or point['volume']<0 or type(point['price_milli']) is not int:
            raise ValueError("integer raw volume/price required")
        if point['volume'] and (point['price_milli']<=0 or point['price_milli']%10):
            raise ValueError("positive cent traded price required")
    windows=[]
    for index in range(0,240,5):
        block=points[index:index+5];end=parse_time(block[-1]['time']);start=end-timedelta(minutes=5)
        prices=[Decimal(p['price_milli'])/1000 for p in block if p['volume']>0]
        evidence={'security_id':code,'day':day.isoformat(),'points':[
            {'time':p['time'],'volume':p['volume'],'price_milli':p['price_milli']} for p in block]}
        windows.append({'security_id':code,'start':iso(start),'end':iso(end),'available_at':iso(end),
                        'volume_lower_shares':sum(max(0,p['volume']*100-100) for p in block),
                        'buy_price':str(max(prices)) if prices else None,
                        'sell_price':str(min(prices)) if prices else None,'evidence_id':digest(evidence)})
    return windows
