"""Execution-account validation of frozen targets, not a new alpha search."""
import argparse
import csv
import json
import math
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from scripts.capture_low_risk_raw_account_data import END, EXPECTED_TARGET_SHA256, START
from scripts.prepare_qlib_master_market_pre2026 import sha256_file
from stock_rsi.broker import money
from stock_rsi.calendar import TradingCalendar
from stock_rsi.data import Snapshot, canonical, digest
from stock_rsi.models import Decision
from stock_rsi.raw_share_account import CENT, Distribution, RawShareAccount, plan_integer_targets
from stock_rsi.time import iso, parse_time


CAPITALS = ("100000","1000000","10000000","100000000")
METHOD_FILES = ("scripts/run_low_risk_raw_share_validation.py","scripts/capture_low_risk_raw_account_data.py",
                "src/stock_rsi/raw_share_account.py","src/stock_rsi/broker.py","src/stock_rsi/models.py",
                "src/stock_rsi/data.py","src/stock_rsi/calendar.py","src/stock_rsi/time.py")


def clean(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,date):return value.isoformat()
    if isinstance(value,dict):return {str(key):clean(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [clean(item) for item in value]
    return value


def canonical_distributions(packets, proofs):
    events=[];seen=set()
    for code,packet in sorted(packets.items()):
        for row in packet["distributions"]:
            key=code+"|"+row["dividOperateDate"]
            if key in seen:raise ValueError("same-date distributions require primary resolution")
            seen.add(key)
            if not row["dividCashPsBeforeTax"] or not row["dividStocksPs"]:
                raise ValueError("missing distribution cash or stock ratio")
            cash=money(row["dividCashPsBeforeTax"])
            stock=money(row["dividStocksPs"])
            if cash < 0 or stock < 0:raise ValueError("negative distribution amount")
            override=proofs.get("cash_overrides",{}).get(key)
            if override:
                if (cash!=Decimal(override["expected_source_cash_per_share"])
                        or override["publication_day"]!=row["dividPlanDate"]):
                    raise ValueError("primary cash override no longer matches source event")
                cash=Decimal(override["cash_per_share"])
            if stock!=0:
                raise ValueError("stock dividend taxation requires a separate supported event")
            capital_text=row["dividReserveToStockPs"]
            if not capital_text:
                display=row.get("dividCashStock","")
                if not (cash>0 and display.startswith("10派") and "转" not in display
                        and "送" not in display and not row["dividStockMarketDate"]):
                    raise ValueError("missing capital ratio without explicit cash-only distribution")
                capital_text="0"
            capital=money(capital_text)
            if capital<0:raise ValueError("negative capital ratio")
            taxproof=proofs.get("capital_tax",{}).get(key,{})
            event_id=digest({"instrument":code,"source_distribution":row,"effective_cash":str(cash)})
            events.append(Distribution(event_id,code,date.fromisoformat(row["dividPlanDate"]),
                date.fromisoformat(row["dividRegistDate"]),date.fromisoformat(row["dividOperateDate"]),
                date.fromisoformat(row["dividPayDate"]) if row["dividPayDate"] else None,
                date.fromisoformat(row["dividStockMarketDate"]) if row["dividStockMarketDate"] else None,
                cash,capital,taxproof.get("verified_exempt") is True))
    return tuple(events)



def validate_source_coverage(packets):
    """Admission checks, never a way to synthesize cash or stock entitlements.

    Some vendor adjustment entries are recorded the next exchange session.
    They are accepted only beside a separately dated distribution; factors
    never determine inventory or the size of a payment.
    """
    for code,packet in packets.items():
        for item in packet["quarantine"]:
            at=item["record"].get("dividOperateDate","")
            if not (item["reason"]=="AFTER_CAPTURE_CUTOFF" and at>END
                    or item["reason"]=="BEFORE_CAPTURE_WINDOW" and at and at<START):
                raise ValueError("unresolved quarantined distribution: "+code)
        ex_dates={row["dividOperateDate"] for row in packet["distributions"]}
        rows=packet["bars"];previous_close=None
        indices={row["date"]:i for i,row in enumerate(rows)}
        for row in rows:
            reference=money(row["preclose"]) if row["preclose"] else None
            if (previous_close is not None and reference is not None and reference>0
                    and abs(reference-previous_close)>Decimal(".005") and row["date"] not in ex_dates):
                raise ValueError("unexplained raw reference change: "+code+" "+row["date"])
            if row["close"] and money(row["close"])>0:previous_close=money(row["close"])
        for adjustment in packet["adjustments"]:
            at=adjustment["dividOperateDate"]
            if at not in indices:raise ValueError("adjustment outside observed sessions: "+code)
            index=indices[at]
            if at not in ex_dates and not (index>0 and rows[index-1]["date"] in ex_dates):
                raise ValueError("unresolved adjustment event: "+code+" "+at)


def simulate_fixed_targets(calendar,bars,events,targets,initial_cash,*,account_factory=RawShareAccount):
    account=account_factory(calendar,initial_cash,events,tax_reserve_rate=".2")
    initial=Decimal(initial_cash);previous_equity=initial;previous_cash=initial;previous_owned={}
    marks={};rows=[];intents=[];ownership={};capacity=[]
    for number,day in enumerate(calendar.days):
        before_corp=len(account.corporate_ledger);before_fills=len(account.broker.fills)
        account.start_day(day)
        pending={order["security_id"] for order in account.broker.orders if order["status"]=="PENDING"}
        execution=[]
        for code in sorted(pending):
            row=bars[code][day.isoformat()]
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
            volume=Decimal(bars[fill["security_id"]][day.isoformat()]["volume"])
            if volume<=0:raise ValueError("a fill has no observed share volume")
            capacity.append(Decimal(fill["quantity"])/volume)
        ex_codes={event.instrument for event in events if event.ex_date==day}
        for code,by_day in bars.items():
            source=by_day[day.isoformat()]
            if source["date"]!=day.isoformat():raise ValueError("market date identity changed")
            if source["tradestatus"]=="1":
                price=Decimal(source["close"])
                if price<=0 or price!=price.quantize(CENT):raise ValueError("invalid actual raw close")
                marks[code]=price
            elif code in ex_codes:
                marks[code]=Decimal(source["preclose"])
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
                expected[item["instrument"]]=expected.get(item["instrument"],0)+item["capital_shares"]
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
                if any(bars[code][day.isoformat()]["tradestatus"]!="1" for code in target["weights"]):
                    raise ValueError("frozen signal eligibility contradicts independent formation-day status")
                orders=plan_integer_targets(wealth["equity"],owned,target["weights"],marks)
                as_of=calendar.at(day,"15:05:00")
                record={"record_id":digest({"policy":"low_vol36","formation":day.isoformat(),"target":target}),
                        "kind":"frozen_target","available_at":iso(as_of),"payload":target}
                visible=[record]
                for code in sorted(set(owned)|set(target["weights"])):
                    content={"instrument":code,"as_of":day.isoformat(),"known_mark":str(marks[code]),
                             "source_bar":bars[code][day.isoformat()]}
                    visible.append({"record_id":digest(content),"kind":"raw_market_state",
                                    "available_at":iso(as_of),"payload":content})
                snapshot=Snapshot(canonical({"as_of":iso(as_of),"records":visible,"account":clean(wealth)}))
                decisions=[Decision.from_dict({"action":action,"security_id":code,"quantity":quantity,
                    "evidence_ids":[record["record_id"]],"reason":"frozen monthly low-volatility target, physical-share execution"},snapshot)
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
    return {"days":rows,"intents":intents,"fills":account.broker.fills,"orders":account.broker.orders,
            "corporate_ledger":account.corporate_ledger,"ownership":ownership,
            "max_daily_volume_fraction":max(capacity,default=Decimal(0)),
            "whole_day_volume_violations":sum(value>1 for value in capacity),
            "execution_status":"INVALID_OBSERVED_TAPE_CAPACITY" if any(value>1 for value in capacity)
                               else "DAILY_PROXY_NECESSARY_CHECKS_PASSED"}


def summarize_case(case,initial_cash):
    rows=case["days"];nav={row["day"]:row["equity"] for row in rows}
    first=Decimal(initial_cash)
    values={"2024_return_pct":float((nav["2024-12-31"]/first-1)*100),
            "2025_return_pct":float((nav["2025-12-31"]/nav["2024-12-31"]-1)*100)}
    for cutoff in ("2026-10-13",END):
        selected=[row for row in rows if "2026-01-01"<=row["day"]<=cutoff]
        if not selected:continue
        start=nav["2025-12-31"];peak=start;drawdown=Decimal(0)
        for row in selected:
            peak=max(peak,row["equity"]);drawdown=min(drawdown,row["equity"]/peak-1)
        values["2026_through_"+cutoff]={"net_compound_return_pct":float((selected[-1]["equity"]/start-1)*100),
            "max_drawdown_pct":float(drawdown*100),
            "average_exposure_pct":float(sum((row["exposure"] for row in selected),Decimal(0))/len(selected)*100),
            "ending_equity":str(selected[-1]["equity"]),"sessions":len(selected)}
    values.update({"fills":len(case["fills"]),"orders":len(case["orders"]),"monthly_decisions":len(case["intents"]),
                   "all_fills_integer":True,"daily_cash_and_share_conservation":True,
                   "record_date_entitlements_verified":True,
                   "max_order_fraction_of_whole_day_volume":float(case["max_daily_volume_fraction"]),
                   "whole_day_volume_violations":case["whole_day_volume_violations"],
                   "opening_auction_liquidity_verified":False})
    return values


def main(argv=None):
    parser=argparse.ArgumentParser()
    for flag in ("data-dir","proof-dir","targets","plan","expected-plan-sha256","output-dir"):
        parser.add_argument("--"+flag,required=True)
    args=parser.parse_args(argv);output=Path(args.output_dir)
    if output.exists():raise ValueError("raw account validation output already exists")
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError("raw validation plan changed")
    plan=json.loads(Path(args.plan).read_text());root=Path(__file__).resolve().parents[1]
    if (plan["status"]!="FROZEN_BEFORE_RAW_ACCOUNT_OUTCOMES" or plan["capitals"]!=list(CAPITALS)
            or set(plan["method_code_sha256"])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan["method_code_sha256"].items())):
        raise ValueError("raw account validation method changed")
    if sha256_file(args.targets)!=EXPECTED_TARGET_SHA256:raise ValueError("frozen investment targets changed")
    for name,value in plan["frozen_economic_core_sha256"].items():
        if sha256_file(root/name)!=value:raise ValueError("investment rule changed during execution validation")
    data=Path(args.data_dir);proof_dir=Path(args.proof_dir)
    if (sha256_file(data/"manifest.json")!=plan["data_manifest_sha256"]
            or sha256_file(proof_dir/"manifest.json")!=plan["proof_manifest_sha256"]):
        raise ValueError("raw market or corporate proof data changed")
    manifest=json.loads((data/"manifest.json").read_text());proofs=json.loads((proof_dir/"manifest.json").read_text())
    if manifest["window"]!=[START,END]:raise ValueError("raw data window changed")
    for document in proofs["documents"]:
        name=document["file"]
        if Path(name).name!=name or sha256_file(proof_dir/name)!=document["sha256"]:
            raise ValueError("primary corporate notice bytes changed")
    if sha256_file(data/"calendar.json")!=manifest["calendar_sha256"]:raise ValueError("exchange sessions changed")
    calendar=TradingCalendar(json.loads((data/"calendar.json").read_text())["sessions"])
    packets={}
    for code,value in manifest["per_code_sha256"].items():
        path=data/"codes"/(code+".json")
        if sha256_file(path)!=value:raise ValueError("raw security source changed")
        packet=json.loads(path.read_text())
        if packet["instrument"]!=code:raise ValueError("raw security identity changed")
        if [row["date"] for row in packet["bars"]]!=[day.isoformat() for day in calendar.days]:
            raise ValueError("complete raw historical session rows required")
        packets[code]=packet
    validate_source_coverage(packets)
    events=canonical_distributions(packets,proofs)
    bars={code:{row["date"]:row for row in packet["bars"]} for code,packet in packets.items()}
    targets=json.loads(Path(args.targets).read_text())
    output.mkdir(parents=True);results={}
    for capital in CAPITALS:
        print("physical-share replay capital="+capital,flush=True)
        folder=output/capital;folder.mkdir()
        try:
            case=simulate_fixed_targets(calendar,bars,events,targets,capital)
            if len(case["intents"])!=34:raise ValueError("all frozen monthly decisions required")
            with (folder/"daily.csv").open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(case["days"][0]));writer.writeheader();writer.writerows(case["days"])
            for key in ("intents","fills","orders","corporate_ledger","ownership"):
                (folder/(key+".json")).write_text(json.dumps(clean(case[key]),indent=2)+"\n")
            results[capital]={"status":("INVALID_OBSERVED_TAPE_CAPACITY" if case["whole_day_volume_violations"]
                                        else "RAW_SHARE_ACCOUNT_RECONCILED"),
                              "execution_status":case["execution_status"],**summarize_case(case,capital),
                              "artifact_sha256":{p.name:sha256_file(p) for p in sorted(folder.iterdir())}}
        except (ValueError,KeyError) as exc:
            results[capital]={"status":"INVALID_ACCOUNT_OR_SOURCE","error":str(exc)}
        (output/"case_results.json").write_text(json.dumps(results,indent=2)+"\n")
    result={"status":"FIXED_SIGNAL_RAW_ACCOUNT_VALIDATION","policy_changed":False,"end":END,
            "target_sha256":EXPECTED_TARGET_SHA256,"results_by_initial_CNY":results,
            "tax_profile":"all cash dividends reserve 20%; not an actual FIFO tax implementation",
            "capital_transfer_profile":"only independently verified exempt transfers may credit entitled inventory",
            "fees":{"buy_bps":5,"sell_bps":15,"minimum_CNY":5},
            "cash_available_rule":"next explicit session after published payment date",
            "execution":"daily open proxy, original direction-specific 9.5% reference-price limit proxy",
            "opening_liquidity_and_impact_verified":False,"historical_observed_arrival_verified":False,
            "research_gate_promoted":False,"sealed_evidence":False,"objective_achieved":False,
            "plan_sha256":args.expected_plan_sha256,"data_manifest_sha256":plan["data_manifest_sha256"],
            "proof_manifest_sha256":plan["proof_manifest_sha256"]}
    (output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
