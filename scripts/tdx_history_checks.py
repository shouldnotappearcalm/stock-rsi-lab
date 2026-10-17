"""Source diagnostics only: no substitution into trading decisions or fills."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def bounded_opening_match(fetch,code,day):
    for pages in (4,16):
        try:
            value=fetch(code,day,include_raw=True,max_pages=pages)
        except RuntimeError as exc:
            if str(exc)!="trade pagination reached max_pages before an empty page" or pages==16:
                raise
            continue
        if value is not None or pages==16:
            return value,pages
    raise RuntimeError("bounded opening scan did not terminate")


def _price_agrees(value, milli):
    if isinstance(value,bool): return False
    try:
        number=Decimal(str(value))
        return number.is_finite() and number==Decimal(milli)/1000
    except Exception:
        return False


def minute_labels():
    return tuple(f"{hour:02d}:{minute:02d}" for hour in (9,10,11,13,14,15) for minute in range(60)
                 if "09:31" <= f"{hour:02d}:{minute:02d}" <= "11:30"
                 or "13:01" <= f"{hour:02d}:{minute:02d}" <= "15:00")


def inspect_minutes(instrument, day, payload, daily):
    if (not isinstance(payload,dict) or payload.get("exchange") != instrument[:2].lower()
            or type(payload.get("market_id")) is not int or payload.get("market_id") != (1 if instrument[:2]=="SH" else 0)
            or payload.get("code") != instrument[2:] or payload.get("trading_date") != day):
        raise ValueError("history request/decoded security or date identity mismatch")
    points = payload.get("points")
    if not isinstance(points,list) or len(points) != 240:
        raise ValueError("complete 240-point minute series required")
    bad_range = []; total_hands = 0
    for index,(point,label) in enumerate(zip(points,minute_labels())):
        if type(point.get("index")) is not int or point.get("index") != index or point.get("time_label") != label:
            raise ValueError("minute label or index changed")
        at = datetime.fromisoformat(point["time"])
        if (at.utcoffset() is None or at.isoformat() != day+"T"+label+":00+08:00"):
            raise ValueError("minute exchange clock is not explicit")
        price,volume = point.get("price_milli"),point.get("volume")
        if type(price) is not int or type(volume) is not int or min(price,volume)<0:
            raise ValueError("nonnegative integer protocol price/hand volume required")
        if not _price_agrees(point.get("price"),price):
            raise ValueError("decoded price disagrees with protocol milli price")
        if volume>0:
            if price<=0 or price%10: raise ValueError("traded ordinary-share price must be on cent tick")
            if daily["tradestatus"]=="1" and not Decimal(daily["low"])<=Decimal(price)/1000<=Decimal(daily["high"]):
                bad_range.append(index)
        total_hands += volume
    last = Decimal(points[-1]["price_milli"])/1000
    daily_volume = Decimal(daily["volume"]) if daily["volume"] else None
    return {"points":len(points),"minute_volume_hands":total_hands,"minute_volume_shares_at_documented_multiplier":total_hands*100,
            "daily_volume_shares":str(daily_volume) if daily_volume is not None else None,
            "exact_total_shares_match":daily_volume is not None and total_hands*100==daily_volume,
            "nearest_hand_daily_total_match_diagnostic_only":daily_volume is not None and Decimal(total_hands)==(daily_volume/100).quantize(Decimal(1),rounding=ROUND_HALF_UP),
            "last_close_matches":daily["tradestatus"]=="1" and last==Decimal(daily["close"]),
            "traded_points_outside_daily_range":bad_range,
            "positive_volume_on_original_halt":daily["tradestatus"]=="0" and total_hands>0,
            "historical_date_echo_authenticated":False,"exact_share_precision_certified":False}


def inspect_opening(day, payload, daily):
    if payload is None: return {"status":"NO_MATCH_WITHIN_BOUNDED_SCAN","usable_matched_volume":False}
    if (not isinstance(payload,dict) or payload.get("event_kind")!="opening_match"
            or payload.get("time_minutes")!=565 or payload.get("time_label")!="09:25"
            or type(payload.get("status_raw")) is not int or payload.get("status_raw")==8):
        raise ValueError("virtual auction snapshot is not an opening match")
    at = datetime.fromisoformat(payload["trade_datetime"])
    at = at.replace(tzinfo=ZoneInfo("Asia/Shanghai")) if at.utcoffset() is None else at.astimezone(ZoneInfo("Asia/Shanghai"))
    if at.date().isoformat()!=day or (at.hour,at.minute,at.second)!=(9,25,0):
        raise ValueError("opening minute/date mismatch")
    price,volume = payload.get("price_milli"),payload.get("volume")
    if type(price) is not int or type(volume) is not int or price<=0 or price%10 or volume<=0:
        raise ValueError("positive cent opening price and whole-hand matched volume required")
    if not _price_agrees(payload.get("price"),price):
        raise ValueError("opening price disagrees with protocol milli price")
    equal = daily["tradestatus"]=="1" and Decimal(price)/1000==Decimal(daily["open"])
    return {"status":"OPENING_PRICE_AGREES_WITH_DAILY" if equal else "OPENING_PRICE_SOURCE_CONFLICT",
            "opening_price_CNY":str(Decimal(price)/1000),"matched_volume_hands":volume,
            "matched_volume_shares_at_documented_multiplier":volume*100,"usable_matched_volume":equal,
            "exchange_time_interpreted":at.isoformat(),
            "timestamp_interpretation":"exchange-local 09:25 minute, date may be attached from request by SDK",
            "historical_date_echo_authenticated":False,"counterfactual_queue_and_impact_verified":False}
