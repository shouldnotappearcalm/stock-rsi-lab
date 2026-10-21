"""Phase-bound trading-regime replay with the unchanged nonbudgeted integer allocator.

This separate daily engineering version preserves the ordinary replay. Source
and pending-execution prerequisites are checked before any daily corporate
credit. New targets enter the dependency set only at their prior-close clock.
Regime evidence and execution audits never enter decision snapshots.
"""
from decimal import Decimal
from scripts.run_low_risk_raw_share_validation import clean
from stock_rsi.broker import money
from stock_rsi.data import Snapshot,canonical,digest
from stock_rsi.trading_regime_horizon_source import regime_source_rows_on, execute_regime_open
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import CENT,plan_integer_targets
from stock_rsi.stock_distribution_account import StockDistributionAccount
from stock_rsi.time import iso


def simulate_regime_fixed_targets(calendar,bars,events,targets,initial_cash,*,lifecycles,regime_evidence,account_factory=StockDistributionAccount,policy_id="price_delay_d1",source_rows=None):
    # Explicit evaluator source-view injection preserves future-only issuer
    # boundaries without replacing any production globals or function objects.
    read_source=regime_source_rows_on if source_rows is None else source_rows
    if not callable(read_source):raise ValueError("explicit callable regime source adapter required")
    events=tuple(events)
    account=account_factory(calendar,initial_cash,events,tax_reserve_rate=".2")
    initial=Decimal(initial_cash);previous_equity=initial;previous_cash=initial;previous_owned={}
    marks={};rows=[];intents=[];ownership={};capacity=[];lifecycle_audit=[];regime_audit=[];phase_audit=[]
    for number,day in enumerate(calendar.days):
        before_corp=len(account.corporate_ledger);before_fills=len(account.broker.fills)
        following=None;target=None;phase="PREOPEN";current_phase=phase
        required=set(account.owned_quantities())|{order["security_id"] for order in account.broker.orders if order["status"]=="PENDING"}
        required.update(event.instrument for event in events if event.ex_date==day and account.entitlements.get(event.event_id,0))
        # The next monthly target is unavailable at PREOPEN. Only existing
        # physical dependencies and positive ex-date entitlements belong here.
        day_bars,exceptions,regimes=read_source(
            bars,day,required,lifecycles,evidence=regime_evidence,
            as_of=calendar.at(day,"09:25:00"))
        lifecycle_audit.extend(exceptions)
        regime_audit.append({"session":day.isoformat(),"phase":"PREOPEN","regimes":regimes})
        phase_audit.append({"session":day.isoformat(),"phase":"PREOPEN_SOURCE_VALIDATED",
                            "as_of":iso(calendar.at(day,"09:25:00")),"required":sorted(required)})
        # Opening prices first become available at09:30. Validate the whole
        # opening batch now, before start_day can credit any corporate claim.
        phase="OPEN_VALIDATION";current_phase=phase
        execution_audit=execute_regime_open(account.broker,day,day_bars,regimes,validate_only=True)
        regime_audit.append({"session":day.isoformat(),"phase":"OPEN_VALIDATION","execution":execution_audit})
        phase_audit.append({"session":day.isoformat(),"phase":"OPEN_VALIDATED_BEFORE_ACCOUNT_START",
                            "as_of":iso(calendar.at(day,"09:30:00"))})
        marks={code:price for code,price in marks.items() if code in day_bars}
        phase="START_DAY";current_phase=phase
        account.start_day(day)
        phase="OPEN";current_phase=phase
        execution_audit=execute_regime_open(account.broker,day,day_bars,regimes)
        regime_audit.append({"session":day.isoformat(),"phase":"OPEN",
                             "execution":execution_audit})
        phase_audit.append({"session":day.isoformat(),"phase":"OPEN_EXECUTED",
                            "as_of":iso(calendar.at(day,"09:30:00"))})
        new_fills=account.broker.fills[before_fills:]
        # At15:05 the completed source session can be read for valuation and
        # capacity diagnostics. Only now may the next frozen target be required.
        phase="CLOSE";current_phase=phase
        following=calendar.days[number+1] if number+1<len(calendar.days) else None
        target=targets.get(following.isoformat()) if following else None
        close_required=set(account.owned_quantities())|required
        if target is not None:close_required.update(target["weights"])
        day_bars,exceptions,close_regimes=read_source(
            bars,day,close_required,lifecycles,evidence=regime_evidence,
            as_of=calendar.at(day,"15:05:00"))
        for item in exceptions:
            if item not in lifecycle_audit:lifecycle_audit.append(item)
        regime_audit.append({"session":day.isoformat(),"phase":"CLOSE",
                             "regimes":close_regimes})
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
        phase_audit.append({"session":day.isoformat(),"phase":"CLOSE_RECORDED",
                            "as_of":iso(calendar.at(day,"15:05:00")),"required":sorted(close_required)})
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
    return {"regime_audit":regime_audit,"phase_audit":phase_audit,"lifecycle_source_audit":lifecycle_audit,"days":rows,"intents":intents,"fills":account.broker.fills,"orders":account.broker.orders,
            "corporate_ledger":account.corporate_ledger,"ownership":ownership,
            "max_daily_volume_fraction":max(capacity,default=Decimal(0)),
            "whole_day_volume_violations":sum(value>1 for value in capacity),
            "execution_status":"INVALID_OBSERVED_TAPE_CAPACITY" if any(value>1 for value in capacity)
                               else "DAILY_PROXY_NECESSARY_CHECKS_PASSED"}
