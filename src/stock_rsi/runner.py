import json
from pathlib import Path

from . import __version__
from .broker import Broker
from .calendar import SHANGHAI
from .data import Dataset, canonical, digest
from .models import Decision
from .scheduler import schedule
from .time import iso, parse_time
from .verification import verify_run


def code_hash():
    root = Path(__file__).parent
    return digest({path.name: path.read_text() for path in sorted(root.glob("*.py"))})


def visible_prices(snapshot):
    rows = [row for row in snapshot.to_dict()["records"] if row["kind"] == "bar"]
    prices = {}
    for row in sorted(rows, key=lambda item: item["payload"]["trade_date"]):
        prices[row["security_id"]] = row["payload"]["close"]
    return prices


def account_view(broker, snapshot, calendar, at):
    view = broker.snapshot(visible_prices(snapshot))
    view["pending_orders"] = [order.copy() for order in broker.orders if order["status"] == "PENDING"]
    today = at.astimezone(SHANGHAI).date()
    completed = [day for day in calendar.days if calendar.at(day, "15:00:00") <= at]
    dates = {}
    for row in snapshot.to_dict()["records"]:
        if row["kind"] == "bar":
            dates[row["security_id"]] = max(dates.get(row["security_id"], ""), row["payload"]["trade_date"])
    for security, position in view["positions"].items():
        position["mark_trade_date"] = dates.get(security)
        if completed and position["mark_trade_date"] != completed[-1].isoformat():
            position["mark_source"] = "STALE_VISIBLE_PRICE"
        first = min(lot["bought_on"] for lot in broker.positions[security])
        position["holding_sessions"] = sum(first <= day <= today for day in calendar.days)
    return view


def run(dataset_path, config, agent, out_dir):
    config = dict(config)
    allowed = {"start", "end", "initial_cash", "cost_bps", "snapshot_bar_limit"}
    if not set(config) <= allowed or not {"start", "end"} <= set(config):
        raise ValueError("invalid run configuration")
    start, end = parse_time(config["start"]), parse_time(config["end"])
    if start > end:
        raise ValueError("start after end")
    data = Dataset.load(dataset_path)
    data.snapshot(start,bar_limit=config.get('snapshot_bar_limit'))
    if start.astimezone(SHANGHAI).date().isoformat() < data.sessions[0] or end.astimezone(SHANGHAI).date().isoformat() > data.sessions[-1]:
        raise ValueError("run range outside declared exchange calendar")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    (out/"dataset.json").write_text(Path(dataset_path).read_text())
    calendar = data.calendar
    broker = Broker(calendar, config.get("initial_cash", "100000"), config.get("cost_bps", "20"))
    manifest = {"dataset_id": data.dataset_id, "dataset_hash": data.sha256,
                "evidence_level": data.evidence_level, "provenance": json.loads(data.provenance_json),
                "config": config, "agent_version": agent.version, "engine_version": __version__,
                "engine_hash": code_hash(), "scope": "ENGINEERING_ONLY; no financial efficacy claim"}
    wakes = schedule(data, calendar, start, end, holding=True)
    events = [(wake.at, 1, "wake", wake) for wake in wakes]
    execution_bars = {}
    for row in sorted(data.records, key=lambda row: row.public_at):
        if row.kind != "bar":
            continue
        payload = row.to_dict()["payload"]
        key = (row.security_id, payload["trade_date"])
        execution_bars.setdefault(key, payload | {"security_id": row.security_id})
    for (security, day), bar in execution_bars.items():
        at = calendar.at(__import__('datetime').date.fromisoformat(day), "09:30:00")
        if start <= at <= end:
            events.append((at, 0, "open", bar))
    for day in calendar.days:
        at = calendar.at(day, "09:30:00")
        if start <= at <= end:
            events.append((at, -1, "session_check", day))
    events.sort(key=lambda item: (item[0], item[1], item[3].get("security_id", "") if item[2] == "open" else ""))
    cassette, wake_rows, errors = [], [], []
    snapshots = out/"snapshots"
    snapshots.mkdir()
    for at, _, kind, item in events:
        if kind == "session_check":
            needed = set(broker.positions) | {order["security_id"] for order in broker.orders if order["status"] == "PENDING" and parse_time(order["eligible_at"]) <= at}
            for security in sorted(needed):
                if (security, item.isoformat()) not in execution_bars:
                    errors.append({"at": iso(at), "stage": "execution", "error": f"missing execution bar: {security} {item}"})
                    for order in broker.orders:
                        if order["status"] == "PENDING" and order["security_id"] == security and parse_time(order["eligible_at"]) <= at:
                            order["status"] = "INVALID_MISSING_DATA"
            continue
        if kind == "open":
            try:
                broker.on_open(item)
            except Exception as exc:
                errors.append({"at": iso(at), "stage": "execution", "error": str(exc)})
            continue
        wake = item
        if wake.reasons == ("POSITION_CHECK",) and not broker.positions:
            continue
        snapshot = data.snapshot(at,bar_limit=config.get('snapshot_bar_limit'))
        account = account_view(broker, snapshot, calendar, at)
        request = {"snapshot": snapshot.to_dict(), "wake": wake.to_dict(), "account": account, "agent_version": agent.version}
        request_hash = digest(request)
        entry = wake.to_dict() | {"snapshot_hash": snapshot.sha256, "request_hash": request_hash, "account": account}
        (snapshots/f"{wake.wake_id}.json").write_text(snapshot.serialized)
        try:
            decision = agent.decide(snapshot, wake, account)
            decision = Decision.from_dict(decision.to_dict(), snapshot)
            known = {row["security_id"] for row in snapshot.to_dict()["records"]}
            if decision.action in ("BUY", "SELL") and decision.security_id not in known:
                raise ValueError("trade security absent from visible snapshot")
            broker.submit(decision, at)
            row = {"request_hash": request_hash, "decision": decision.to_dict()}
            row["response_hash"] = digest(row["decision"])
            cassette.append(row)
            entry["decision"] = decision.to_dict()
        except Exception as exc:
            errors.append({"at": iso(at), "stage": "agent", "error": str(exc)})
            cassette.append({"request_hash": request_hash, "error": str(exc), "response_hash": digest({"error": str(exc)})})
            entry["error"] = str(exc)
        wake_rows.append(entry)
    final_snapshot = data.snapshot(end,bar_limit=config.get('snapshot_bar_limit'))
    final_account = account_view(broker, final_snapshot, calendar, end)
    if any(position["mark_source"] != "VISIBLE_PRICE" for position in final_account["positions"].values()):
        errors.append({"at": iso(end), "stage": "valuation", "error": "unmarked holding"})
    manifest["cassette_hash"] = digest(cassette)
    report = {"status": "INVALID_AGENT" if any(e["stage"] == "agent" for e in errors) else "INVALID_DATA" if errors else "COMPLETED_ENGINEERING",
              "manifest": manifest, "wakes": wake_rows, "fills": broker.fills, "orders": broker.orders,
              "account": final_account, "errors": errors,
              "agent_calls": getattr(agent, "calls", [])}
    report['verify_gate']=verify_run(report)
    if report['status']=='COMPLETED_ENGINEERING' and not report['verify_gate']['exploratory_backtest_allowed']:
        report['status']='INVALID_VERIFICATION'
        errors.append({'at':iso(end),'stage':'verification','error':'; '.join(report['verify_gate']['hard_checks']['failures'])})
    manifest["agent_calls_hash"] = digest(report["agent_calls"])
    (out/"cassette.json").write_text(canonical(cassette))
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report


class ReplayAgent:
    def __init__(self, version, rows):
        self.version, self.rows, self.index = version, rows, 0

    def decide(self, snapshot, wake, account):
        request = {"snapshot": snapshot.to_dict(), "wake": wake.to_dict(), "account": account, "agent_version": self.version}
        if self.index >= len(self.rows):
            raise ValueError("replay exhausted")
        row = self.rows[self.index]
        self.index += 1
        if digest(request) != row["request_hash"]:
            raise ValueError("replay request mismatch")
        if "error" in row:
            raise RuntimeError(row["error"])
        return Decision.from_dict(row["decision"], snapshot)


def replay(run_dir, out_dir):
    source = Path(run_dir)
    report = json.loads((source/"report.json").read_text())
    manifest = report["manifest"]
    rows = json.loads((source/"cassette.json").read_text())
    if digest(rows) != manifest["cassette_hash"] or code_hash() != manifest["engine_hash"]:
        raise ValueError("replay artifact/source integrity mismatch")
    if Dataset.load(source/"dataset.json").sha256 != manifest["dataset_hash"]:
        raise ValueError("replay dataset integrity mismatch")
    for row in rows:
        response = row["decision"] if "decision" in row else {"error": row["error"]}
        if digest(response) != row["response_hash"]:
            raise ValueError("replay response integrity mismatch")
    for wake in report["wakes"]:
        saved = (source/"snapshots"/f"{wake['wake_id']}.json").read_text()
        import hashlib
        if hashlib.sha256(saved.encode()).hexdigest() != wake["snapshot_hash"]:
            raise ValueError("replay saved snapshot integrity mismatch")
    if digest(report["agent_calls"]) != manifest["agent_calls_hash"]:
        raise ValueError("replay agent calls integrity mismatch")
    agent = ReplayAgent(manifest["agent_version"], rows)
    result = run(source/"dataset.json", manifest["config"], agent, out_dir)
    if agent.index != len(rows) or any(result[key] != report[key] for key in ("status", "wakes", "fills", "orders", "account", "errors", "verify_gate")):
        raise ValueError("replay incomplete or ledger mismatch")
    if any("replay" in error["error"] for error in result["errors"]):
        raise ValueError("replay mismatch")
    return result
