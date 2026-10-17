"""Evidence about fixed executor windows; never an order, fill or ROI claim."""
from decimal import Decimal,ROUND_DOWN


def buy_window_evidence(windows,daily,participation_bps):
    if participation_bps not in (100,500,1000) or type(participation_bps) is not int:
        raise ValueError('registered participation required')
    if not isinstance(windows,list) or len(windows)!=48:raise ValueError('complete48-window series required')
    out={'protective_buy_limit_CNY':None,'candidate_windows':0,'windows':[],
         'actual_fill_verified':False,'cash_and_parent_quantity_simulated':False,'queue_and_impact_calibrated':False}
    if daily['tradestatus']!='1' or daily['isST']!='0':return out|{'status':'HALTED_OR_SPECIAL_STATUS_UNSUPPORTED'}
    reference=Decimal(daily['preclose'])
    if not reference.is_finite() or reference<=0:raise ValueError('finite positive reference required')
    limit=(reference*Decimal('1.095')).quantize(Decimal('.01'),rounding=ROUND_DOWN)
    out['protective_buy_limit_CNY']=str(limit)
    # Same first/last eligible window indices as the frozen IntradayBroker.
    for i in range(1,47):
        previous,current=windows[i-1],windows[i]
        a,b=previous['volume_lower_shares'],current['volume_lower_shares']
        if any(type(v) is not int or v<0 for v in (a,b)):raise ValueError('nonnegative integer stressed volumes required')
        price=current['buy_price']
        if price is None:continue
        price=Decimal(price)
        if not price.is_finite() or price<=0:raise ValueError('finite positive sampled price required')
        capacity=min(a*participation_bps//10000,b*participation_bps//10000,1000000)//100*100
        if capacity<100 or price>=limit:continue
        out['windows'].append({'start':current['start'],'end':current['end'],
            'previous_available_at':previous['end'],'previous_evidence_id':previous['evidence_id'],
            'current_evidence_id':current['evidence_id'],'sampled_adverse_buy_CNY':str(price),
            'two_bucket_volume_cap_shares':capacity})
    out['candidate_windows']=len(out['windows']);return out|{'status':'SAMPLED_SOURCE_WINDOWS_CLASSIFIED'}
