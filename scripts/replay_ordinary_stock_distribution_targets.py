"""Ordinary-state guard over the original fixed-target stock-income replay.

The original raw-share runner remains unchanged. Primary lifecycle evidence
is evaluator-only and cannot enter a decision record. This daily-price adapter
can use an authenticated IntradayBroker factory without changing investments.
"""
from decimal import Decimal
from scripts.run_low_risk_raw_share_validation import clean
from stock_rsi.broker import money
from stock_rsi.data import Snapshot,canonical,digest
from stock_rsi.ordinary_source_scope import ordinary_source_rows_on as source_rows_on
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import CENT,plan_integer_targets
from stock_rsi.stock_distribution_account import StockDistributionAccount
from stock_rsi.time import iso


def simulate_fixed_targets(calendar,bars,events,targets,initial_cash,*,lifecycles,account_factory=StockDistributionAccount,policy_id="amihud22"):
    events=tuple(events)
    account=account_factory(calendar,initial_cash,events,tax_reserve_rate=".2")
    initial=Decimal(initial_cash);previous_equity=initial;previous_cash=initial;previous_owned={}
    marks={};rows=[];intents=[];ownership={};capacity=[];lifecycle_audit=[]
    for number,day in enumerate(calendar.days):
        before_corp=len(account.corporate_ledger);before_fills=len(account.broker.fills)
        following=calendar.days[number+1] if number+1<len(calendar.days) else None
        target=targets.get(following.isoformat()) if following else None
        required=set(account.owned_quantities())|{order["security_id"] for order in account.broker.orders if order["status"]=="PENDING"}
        required.update(event.instrument for event in events if event.ex_date==day and account.entitlements.get(event.event_id,0))
        if target is not None:required.update(target["weights"])
        day_bars,exceptions=source_rows_on(bars,day,required,lifecycles)
        lifecycle_audit.extend(exceptions)
        marks={code:price for code,price in marks.items() if code in day_bars}
        account.start_day(day)
        pending={order["security_id"] for order in account.broker.orders if order["status"]=="PENDING"}
        execution=[]
        for code in sorted(pending):
            row=day_bars[code]
            if row["date"]!=day.isoformat() or row["tradestatus"] not in ("0","1") or row["isST"]!="0":
                raise ValueError("execution data or supported ordinary-board state unknown")
            item={"security_id":code,"trade_date":day.isoformat(),"suspended":row["tradestatus"]=="0"}
            if row["tradestatus"]=="1":
                reference=money(row["preclose"]);price=money(row["open"])
                if price!=price.quantize(CENT):
                    raise ValueError("actual stock execution price must lie on the cent tick")
                item.update(open=str(price),limit_up=str(reference*Decimal("1.095")),
                            limit_down=str(reference*Decimal(".905")))
            execution.append(item)
        if execution:account.broker.on_market_open(execution)
        new_fills=account.broker.fills[before_fills:]
        for fill in new_fills:
            if type(fill["quantity"]) is not int or fill["quantity"]<=0:
                raise ValueError("noninteger physical stock fill")
            if fill["action"]=="BUY" and fill["quantity"]%100:
                raise ValueError("physical stock buy violates 100-share unit")
            volume=money(day_bars[fill["security_id"]]["volume"])
            if volume<=0:raise ValueError("a fill has no observed share volume")
            capacity.append(Decimal(fill["quantity"])/volume)
        ex_codes={event.instrument for event in events if event.ex_date==day}
        for code,source in day_bars.items():
            if source["date"]!=day.isoformat():raise ValueError("market date identity changed")
            if source["tradestatus"] not in ("0","1"):raise ValueError("unknown source market status")
            if source["tradestatus"]=="1":
                price=money(source["close"])
                if price<=0 or price!=price.quantize(CENT):raise ValueError("invalid actual raw close")
                marks[code]=price
            elif code in ex_codes:
                marks[code]=money(source["preclose"])
            elif code not in marks and source["close"] and money(source["close"])>0:
                marks[code]=money(source["close"])
        account.end_day(day)
        wealth=account.wealth(marks);owned=account.owned_quantities()
        corporate=account.corporate_ledger[before_corp:]
        dividend_cash=sum((item["cash_delta"] for item in corporate if item["kind"]=="NET_DIVIDEND_CASH_AVAILABLE"),Decimal(0))
        signed=sum(((Decimal(fill["price"])*fill["quantity"])*(1 if fill["action"]=="BUY" else -1)
                    for fill in new_fills),Decimal(0))
        fees=sum((Decimal(fill["cost"]) for fill in new_fills),Decimal(0))
        if wealth["cash"]!=previous_cash-signed-fees+dividend_cash:
            raise ValueError("physical cash-flow conservation failed")
        expected=dict(previous_owned)
        for fill in new_fills:
            code=fill["security_id"]
            expected[code]=expected.get(code,0)+fill["quantity"]*(1 if fill["action"]=="BUY" else -1)
        for item in corporate:
            if item["kind"]=="EX_DATE_ENTITLEMENT":
                expected[item["instrument"]]=expected.get(item["instrument"],0)+item["capital_shares"]+item.get("stock_shares",0)
        expected={code:q for code,q in expected.items() if q}
        if expected!=owned:raise ValueError("integer share-flow conservation failed")
        independent_equity=wealth["cash"]+wealth["cash_receivable"]+sum((q*marks[code] for code,q in owned.items()),Decimal(0))
        if independent_equity!=wealth["equity"]:raise ValueError("raw asset valuation double counted a claim")
        ownership[day.isoformat()]={code:int(item["quantity"]) for code,item in wealth["positions"].items()}
        exposure=(wealth["market_value"]+wealth["pending_stock_value"])/wealth["equity"]
        rows.append({"day":day.isoformat(),"cash":wealth["cash"],"market_value":wealth["market_value"],
                     "cash_receivable":wealth["cash_receivable"],"pending_stock_value":wealth["pending_stock_value"],
                     "equity":wealth["equity"],"net_return":wealth["equity"]/previous_equity-1,
                     "exposure":exposure,"fees":fees,"net_dividend_cash_available":dividend_cash})
        if number+1<len(calendar.days):
            following=calendar.days[number+1];target=targets.get(following.isoformat())
            if target is not None:
                if target["as_of"]!=day.isoformat() or day.month==following.month:
                    raise ValueError("frozen monthly target is not visible on the prior close")
                if any(day_bars[code]["tradestatus"]!="1" for code in target["weights"]):
                    raise ValueError("frozen signal eligibility contradicts independent formation-day status")
                orders=plan_integer_targets(wealth["equity"],owned,target["weights"],marks)
                as_of=calendar.at(day,"15:05:00")
                record={"record_id":digest({"policy":policy_id,"formation":day.isoformat(),"target":target}),
                        "kind":"frozen_target","available_at":iso(as_of),"payload":target}
                visible=[record]
                for code in sorted(set(owned)|set(target["weights"])):
                    content={"instrument":code,"as_of":day.isoformat(),"known_mark":str(marks[code]),
                             "source_bar":day_bars[code]}
                    visible.append({"record_id":digest(content),"kind":"raw_market_state",
                                    "available_at":iso(as_of),"payload":content})
                snapshot=Snapshot(canonical({"as_of":iso(as_of),"records":visible,"account":clean(wealth)}))
                decisions=[Decision.from_dict({"action":action,"security_id":code,"quantity":quantity,
                    "evidence_ids":[record["record_id"]],"reason":"frozen monthly "+policy_id+" target, physical-share execution"},snapshot)
                    for action,code,quantity in orders]
                account.broker.replace_pending_intent(decisions,as_of,calendar.at(following,"09:30:00"))
                intents.append({"execution_session":following.isoformat(),"as_of":iso(as_of),
                                "snapshot_sha256":snapshot.sha256,"equity_at_decision":wealth["equity"],
                                "owned_integer_shares":owned,"decisions":[d.to_dict() for d in decisions]})
        previous_equity,previous_cash,previous_owned=wealth["equity"],wealth["cash"],owned
    by_id={event.event_id:event for event in events}
    for entry in account.corporate_ledger:
        if entry["kind"]!="EX_DATE_ENTITLEMENT":continue
        event=by_id[entry["event_id"]]
        expected=ownership.get(event.recorded.isoformat(),{}).get(event.instrument,0)
        if entry["registered_quantity"]!=expected:raise ValueError("dividend entitlement differs from record-date inventory")
    return {"lifecycle_source_audit":lifecycle_audit,"days":rows,"intents":intents,"fills":account.broker.fills,"orders":account.broker.orders,
            "corporate_ledger":account.corporate_ledger,"ownership":ownership,
            "max_daily_volume_fraction":max(capacity,default=Decimal(0)),
            "whole_day_volume_violations":sum(value>1 for value in capacity),
            "execution_status":"INVALID_OBSERVED_TAPE_CAPACITY" if any(value>1 for value in capacity)
                               else "DAILY_PROXY_NECESSARY_CHECKS_PASSED"}
