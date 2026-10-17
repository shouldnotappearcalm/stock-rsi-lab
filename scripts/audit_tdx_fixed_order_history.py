"""Historical source/auction-print comparison, not an execution simulator."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.audit_low_risk_execution_tape import order_session
from scripts.tdx_history_checks import inspect_minutes, inspect_opening


EXPECTED_RAW = "4177efc8615eca4a53fec13161087ca9329b8f1448bc75a41e94179cb368f19a"
EXPECTED_REPLAY = "1c1ebd67e9d87ca4004b2d39b6c74aa8eb8f1ae20fdcfd4c23ece9f2eeb71006"


def main(argv=None):
    parser = argparse.ArgumentParser()
    for flag in ("capture-dir","raw-data-dir","feedback-replay-dir","expected-capture-manifest-sha256","output"):
        parser.add_argument("--"+flag,required=True)
    args=parser.parse_args(argv)
    capture,raw,replay,output=map(Path,(args.capture_dir,args.raw_data_dir,args.feedback_replay_dir,args.output))
    if output.exists():raise ValueError("TDX audit output already exists")
    if (sha256_file(capture/"manifest.json")!=args.expected_capture_manifest_sha256
            or sha256_file(raw/"manifest.json")!=EXPECTED_RAW
            or sha256_file(replay/"summary.json")!=EXPECTED_REPLAY):
        raise ValueError("historical source or fixed replay identity changed")
    manifest=json.loads((capture/"manifest.json").read_text());plan=json.loads((capture/"plan.json").read_text())
    if sha256_file(capture/"plan.json")!=manifest["plan_sha256"] or plan["feedback_summary_sha256"]!=EXPECTED_REPLAY:
        raise ValueError("history capture plan changed")
    root=Path(__file__).resolve().parents[1]
    if sha256_file(root/"experiments/qlib/audit_sources/2026-10-17-tdx-fixed-order-history-v1.py")!=plan["script_sha256"]:
        raise ValueError("history capture source version changed")
    original=json.loads((raw/"manifest.json").read_text());bars={}
    for code,expected in original["per_code_sha256"].items():
        path=raw/"codes"/(code+".json")
        if sha256_file(path)!=expected:raise ValueError("original raw prices changed")
        bars[code]={row["date"]:row for row in json.loads(path.read_text())["bars"]}
    summary=json.loads((replay/"summary.json").read_text());profile_files={};requests=set()
    for bps,cases in summary["results_by_extra_bps_and_initial_CNY"].items():
        for capital,case in cases.items():
            label=bps+"/"+capital
            if "artifact_sha256" not in case:
                if case["status"]!="INVALID_SINGLE_ORDER_LIMIT":raise ValueError("unknown failed profile")
                continue
            folder=replay/bps/capital
            for name in ("orders.json","fills.json"):
                if sha256_file(folder/name)!=case["artifact_sha256"][name]:raise ValueError("fixed replay artifact changed")
            orders=json.loads((folder/"orders.json").read_text());fills=json.loads((folder/"fills.json").read_text())
            requests.update(key for order in orders if (key:=order_session(order)) is not None)
            profile_files[label]=(orders,fills)
    if plan["requests"]!=[list(key) for key in sorted(requests)] or manifest["requested_code_sessions"]!=len(requests):
        raise ValueError("historical source requests do not cover exact all-order union")
    expected_names={code+"-"+day+".json" for code,day in requests}
    if (not set(manifest["per_session_sha256"])<=expected_names
            or manifest["captured_code_sessions"]!=len(manifest["per_session_sha256"])):
        raise ValueError("unexpected history file or capture count")
    facts={};known_halts=0;missing=[]
    for code,day in sorted(requests):
        name=code+"-"+day+".json"
        if name not in manifest["per_session_sha256"]:
            missing.append([code,day]);continue
        path=capture/"sessions"/name
        if sha256_file(path)!=manifest["per_session_sha256"][name]:raise ValueError("history response bytes changed")
        packet=json.loads(path.read_text())
        if packet["instrument"]!=code or packet["requested_day"]!=day:raise ValueError("history packet identity changed")
        daily=bars[code][day];item={"instrument":code,"day":day,"original_tradestatus":daily["tradestatus"]}
        if daily["tradestatus"]=="0":known_halts+=1
        for method,key,check in (("minutes.history","minute",inspect_minutes),
                                 ("trades.opening_match_history","opening",inspect_opening)):
            record=packet["methods"].get(method)
            if record is None or record["status"] not in ("RESPONSE_CAPTURED","NO_MATCH_WITHIN_BOUNDED_SCAN"):
                item[key]={"status":"SOURCE_REQUEST_FAILED","error":record};continue
            try:
                item[key]=check(code,day,record["response"],daily) if key=="minute" else check(day,record["response"],daily)
            except (ValueError,KeyError,TypeError) as exc:
                item[key]={"status":"SOURCE_SHAPE_OR_IDENTITY_CONFLICT","error":str(exc)}
        minute=item.get("minute",{});opening=item.get("opening",{})
        item["price_signature_compatible"]=(minute.get("last_close_matches") is True
            and not minute.get("traded_points_outside_daily_range") and not minute.get("positive_volume_on_original_halt"))
        item["usable_print_comparison"]=(opening.get("usable_matched_volume") is True and item["price_signature_compatible"])
        facts[(code,day)]=item
    profiles={}
    for label,(orders,fills) in profile_files.items():
        unknown=[];ratios=[]
        for fill in fills:
            key=(fill["security_id"],fill["execution_at"][:10]);item=facts.get(key)
            if item is None or not item["usable_print_comparison"]:
                unknown.append({"security_id":key[0],"day":key[1],"order_id":fill["order_id"]});continue
            matched=item["opening"]["matched_volume_shares_at_documented_multiplier"]
            ratios.append({"security_id":key[0],"day":key[1],"action":fill["action"],"quantity":fill["quantity"],
                           "matched_source_shares":matched,"fraction":Decimal(fill["quantity"])/matched,
                           "fill_clock":fill["execution_at"],"print_clock":item["opening"]["exchange_time_interpreted"]})
        maximum=max(ratios,key=lambda r:r["fraction"]) if ratios else None
        profiles[label]={"status":"OPENING_PRINT_BENCHMARK_IMPACT_UNVERIFIED" if not unknown else "INCOMPLETE_SOURCE_PRINT_COMPARISON",
            "fills":len(fills),"comparable_fills":len(ratios),"unknown_source_fills":unknown,
            "over_1pct_of_observed_match":sum(r["fraction"]>Decimal(".01") for r in ratios),
            "over_10pct_of_observed_match":sum(r["fraction"]>Decimal(".1") for r in ratios),
            "over_100pct_of_observed_match":sum(r["fraction"]>1 for r in ratios),
            "max_comparison":{k:float(v) if isinstance(v,Decimal) else v for k,v in maximum.items()} if maximum else None,
            "counterfactual_queue_and_impact_verified":False,"broker_fill_clock_equals_auction_clock":False}
    active=[item for item in facts.values() if item["original_tradestatus"]=="1"]
    result={"status":"HISTORICAL_SOURCE_AND_AUCTION_PRINT_DIAGNOSTIC_NOT_EXECUTION_CERTIFICATION",
        "capture_manifest_sha256":args.expected_capture_manifest_sha256,"raw_manifest_sha256":EXPECTED_RAW,
        "feedback_summary_sha256":EXPECTED_REPLAY,"audit_code_sha256":sha256_file(__file__),
        "source_check_code_sha256":sha256_file(root/"scripts/tdx_history_checks.py"),
        "requested_code_sessions":len(requests),"captured_code_sessions":len(facts),"missing_capture_sessions":missing,
        "original_known_halt_sessions":known_halts,"active_requested_sessions":len(active),
        "complete_minute_series":sum(item.get("minute",{}).get("points")==240 for item in active),
        "last_close_matches":sum(item.get("minute",{}).get("last_close_matches") is True for item in active),
        "nearest_hand_daily_total_matches_diagnostic_only":sum(item.get("minute",{}).get("nearest_hand_daily_total_match_diagnostic_only") is True for item in active),
        "opening_price_matches":sum(item.get("opening",{}).get("usable_matched_volume") is True for item in active),
        "usable_source_print_comparisons":sum(item["usable_print_comparison"] for item in active),
        "profiles":profiles,"per_session":{code+"/"+day:item for (code,day),item in facts.items()},
        "interpretation":"Observed 09:25 prints are benchmarks for 09:30-timestamp daily-open proxy fills. Adding orders may change price and matched volume; these ratios neither prove impossibility nor prove queue/impact feasibility.",
        "source_hand_precision_is_exact_share_precision":False,"historical_date_echo_authenticated":False,
        "old_baostock_minute_responses_replaced":False,"policy_changed":False,"objective_achieved":False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({key:value for key,value in result.items() if key not in ("profiles","per_session")},indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
