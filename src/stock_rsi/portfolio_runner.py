import hashlib
import json
from datetime import date
from pathlib import Path

from . import __version__
from .broker import Broker
from .calendar import SHANGHAI
from .data import Dataset, canonical, digest
from .factors import FactorEvidence, FactorFrame
from .policy import PolicyBundle, select_proposal, validate_candidate_set
from .portfolio import PortfolioProposal
from .runner import account_view, code_hash
from .scheduler import schedule
from .targeting import plan_target_orders
from .time import iso, parse_time
from .verification import verify_portfolio_run


def _policy_artifact(policy):
    bundle = getattr(policy, "bundle", None)
    if isinstance(bundle, PolicyBundle):
        artifact = bundle.to_dict()
    else:
        artifact = getattr(policy, "bundle_artifact", None)
        if not isinstance(artifact, dict):
            raise ValueError("portfolio policy must expose a complete PolicyBundle artifact")
        artifact = json.loads(canonical(artifact))
    validated = PolicyBundle.from_artifact(artifact)
    if validated.bundle_id != policy.bundle_id:
        raise ValueError("policy bundle artifact identity mismatch")
    return validated.to_dict()


def _validated_factor_frame(snapshot, frame):
    if not isinstance(frame, FactorFrame) or frame.snapshot_hash != snapshot.sha256:
        raise ValueError("factor provider returned a frame for another snapshot")
    evidence = []
    for item in frame.to_dict()["evidence"]:
        payload = dict(item)
        payload.pop("snapshot_hash", None)
        evidence.append(FactorEvidence.from_dict(payload, snapshot))
    validated = FactorFrame.from_evidence(snapshot, evidence)
    if validated.to_dict() != frame.to_dict():
        raise ValueError("factor provider returned a noncanonical frame")
    return validated


def _config(config):
    config = dict(config)
    allowed = {"start", "end", "initial_cash", "cost_bps", "snapshot_bar_limit"}
    if not set(config) <= allowed or not {"start", "end"} <= set(config):
        raise ValueError("invalid portfolio run configuration")
    start, end = parse_time(config["start"]), parse_time(config["end"])
    if start > end:
        raise ValueError("start after end")
    return config, start, end


def _execution_bars(data):
    bars = {}
    for row in sorted(data.records, key=lambda item: (item.public_at, item.record_id)):
        if row.kind != "bar":
            continue
        payload = row.to_dict()["payload"]
        bars.setdefault((row.security_id, payload["trade_date"]), payload | {"security_id": row.security_id})
    return bars


def run_portfolio(dataset_path, config, policy, selector, factor_provider, out_dir):
    config, start, end = _config(config)
    data = Dataset.load(dataset_path)
    if (start.astimezone(SHANGHAI).date().isoformat() < data.sessions[0] or
            end.astimezone(SHANGHAI).date().isoformat() > data.sessions[-1]):
        raise ValueError("run range outside declared exchange calendar")
    data.snapshot(start, bar_limit=config.get("snapshot_bar_limit"))
    if not isinstance(getattr(policy, "bundle_id", None), str):
        raise ValueError("portfolio policy bundle_id required")
    for component, name in ((selector, "selector"), (factor_provider, "factor provider")):
        if not isinstance(getattr(component, "version", None), str) or not component.version:
            raise ValueError(f"{name} version required")
    bundle_artifact = _policy_artifact(policy)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    (out / "dataset.json").write_text(Path(dataset_path).read_text())
    (out / "policy_bundle.json").write_text(canonical(bundle_artifact))
    calendar = data.calendar
    broker = Broker(calendar, config.get("initial_cash", "100000"), config.get("cost_bps", "20"))
    manifest = {
        "dataset_id": data.dataset_id,
        "dataset_hash": data.sha256,
        "evidence_level": data.evidence_level,
        "provenance": json.loads(data.provenance_json),
        "config": config,
        "policy_bundle_id": policy.bundle_id,
        "policy_bundle_artifact_hash": digest(bundle_artifact),
        "selector_version": selector.version,
        "factor_provider_version": factor_provider.version,
        "engine_version": __version__,
        "engine_hash": code_hash(),
        "scope": "ENGINEERING_ONLY; portfolio proposal foundation; no financial efficacy claim",
    }
    wakes = schedule(data, calendar, start, end, holding=True)
    events = [(wake.at, 1, "wake", wake) for wake in wakes]
    execution = _execution_bars(data)
    by_day = {}
    for (security, day), bar in execution.items():
        by_day.setdefault(day, []).append(bar)
    for session in calendar.days:
        at = calendar.at(session, "09:30:00")
        if start <= at <= end:
            events.append((at, 0, "open", sorted(by_day.get(session.isoformat(), []), key=lambda row: row["security_id"])))
    events.sort(key=lambda item: (item[0], item[1]))
    cassette, wake_rows, candidate_sets, selections, errors = [], [], [], [], []
    snapshots = out / "snapshots"
    snapshots.mkdir()
    for at, _, kind, item in events:
        if kind == "open":
            bars = item
            needed = set(broker.positions) | {
                order["security_id"] for order in broker.orders
                if order["status"] == "PENDING" and parse_time(order["eligible_at"]) <= at
            }
            available = {bar["security_id"] for bar in bars}
            for security in sorted(needed - available):
                errors.append({"at": iso(at), "stage": "execution", "error": f"missing execution bar: {security} {at.astimezone(SHANGHAI).date()}"})
                for order in broker.orders:
                    if (order["status"] == "PENDING" and order["security_id"] == security and
                            parse_time(order["eligible_at"]) <= at):
                        order["status"] = "INVALID_MISSING_DATA"
            if bars:
                try:
                    broker.on_market_open(bars)
                except Exception as exc:
                    errors.append({"at": iso(at), "stage": "execution", "error": str(exc)})
            continue
        wake = item
        if wake.reasons == ("POSITION_CHECK",) and not broker.positions:
            continue
        snapshot = data.snapshot(at, bar_limit=config.get("snapshot_bar_limit"))
        account = account_view(broker, snapshot, calendar, at)
        entry = wake.to_dict() | {"snapshot_hash": snapshot.sha256, "account": account}
        (snapshots / f"{wake.wake_id}.json").write_text(snapshot.serialized)
        failure_row = None
        try:
            factors = _validated_factor_frame(snapshot, factor_provider.build(snapshot, wake, account))
            request = {
                "snapshot": snapshot.to_dict(), "wake": wake.to_dict(), "account": account,
                "factors": factors.to_dict(), "policy_bundle_id": policy.bundle_id,
                "selector_version": selector.version, "factor_provider_version": factor_provider.version,
            }
            request_hash = digest(request)
            proposals = validate_candidate_set(policy, snapshot, account, policy.propose(snapshot, wake, account, factors))
            candidate_payloads = [row.to_dict() for row in proposals]
            candidate_set_hash = digest({"request_hash": request_hash, "candidates": candidate_payloads})
            candidate_record = {"wake_id": wake.wake_id, "request_hash": request_hash,
                                "candidate_set_hash": candidate_set_hash, "candidates": candidate_payloads}
            candidate_sets.append(candidate_record)
            cassette_base = {
                "request_hash": request_hash,
                "factors": factors.to_dict(),
                "candidates": candidate_payloads,
                "candidate_set_hash": candidate_set_hash,
            }
            stage = "selector"
            try:
                selected = select_proposal(selector, snapshot, account, proposals)
                selection_hash = digest({"candidate_set_hash": candidate_set_hash, "selected_id": selected.proposal_id,
                                         "selector_version": selector.version})
                stage = "intent"
                decisions = plan_target_orders(selected, snapshot, account)
                broker.replace_pending_intent(decisions, at, selected.expires_at)
            except Exception as exc:
                failure_row = cassette_base | {"error_stage": stage, "error": str(exc)}
                cassette.append(failure_row)
                raise
            row = cassette_base | {
                "selected_id": selected.proposal_id, "selection_hash": selection_hash,
                "decisions": [decision.to_dict() for decision in decisions],
            }
            cassette.append(row)
            selections.append({"wake_id": wake.wake_id, "candidate_set_hash": candidate_set_hash,
                               "selected_id": selected.proposal_id, "selected_proposal_hash": selected.sha256,
                               "selection_hash": selection_hash})
            entry.update(request_hash=request_hash, candidate_set_hash=candidate_set_hash,
                         selected_id=selected.proposal_id, decisions=row["decisions"])
        except Exception as exc:
            errors.append({"at": iso(at), "stage": "portfolio", "error": str(exc)})
            entry["error"] = str(exc)
        wake_rows.append(entry)
    final_snapshot = data.snapshot(end, bar_limit=config.get("snapshot_bar_limit"))
    final_account = account_view(broker, final_snapshot, calendar, end)
    if any(position["mark_source"] != "VISIBLE_PRICE" for position in final_account["positions"].values()):
        errors.append({"at": iso(end), "stage": "valuation", "error": "unmarked holding"})
    status = "INVALID_POLICY" if any(error["stage"] == "portfolio" for error in errors) else "INVALID_DATA" if errors else "COMPLETED_ENGINEERING"
    manifest["cassette_hash"] = digest(cassette)
    report = {
        "status": status, "manifest": manifest, "wakes": wake_rows,
        "candidate_sets": candidate_sets, "selections": selections,
        "orders": broker.orders, "fills": broker.fills, "account": final_account, "errors": errors,
    }
    report["verify_gate"] = verify_portfolio_run(report)
    if status == "COMPLETED_ENGINEERING" and not report["verify_gate"]["exploratory_backtest_allowed"]:
        report["status"] = "INVALID_VERIFICATION"
    (out / "cassette.json").write_text(canonical(cassette))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report


class _RecordedComponents:
    def __init__(self, rows, manifest, bundle_artifact):
        self.rows = rows
        self.manifest = manifest
        self.index = 0
        self.current = None
        self.version = manifest["factor_provider_version"]
        self.bundle_id = manifest["policy_bundle_id"]
        self.bundle_artifact = bundle_artifact

    def build(self, snapshot, wake, account):
        if self.index >= len(self.rows):
            raise ValueError("portfolio replay exhausted")
        self.current = self.rows[self.index]
        payload = self.current["factors"]
        evidence = []
        for item in payload["evidence"]:
            source = dict(item)
            source.pop("snapshot_hash", None)
            evidence.append(FactorEvidence.from_dict(source, snapshot))
        frame = FactorFrame.from_evidence(snapshot, evidence)
        if frame.to_dict() != payload:
            raise ValueError("replay factor frame mismatch")
        return frame

    def propose(self, snapshot, wake, account, factors):
        proposals = []
        visible = {row["security_id"] for row in snapshot.to_dict()["records"]}
        for payload in self.current["candidates"]:
            eligible = visible | {row["security_id"] for row in payload["targets"] if row["security_id"] != "CASH"}
            proposals.append(PortfolioProposal.from_dict(payload, snapshot, account, eligible, self.bundle_id))
        return tuple(proposals)

    def select(self, snapshot, account, proposals):
        if self.current.get("error_stage") == "selector":
            message = self.current["error"]
            self.index += 1
            raise ValueError(message)
        selected = self.current["selected_id"]
        self.index += 1
        return selected

    @property
    def selector_version(self):
        return self.manifest["selector_version"]


class _RecordedSelector:
    def __init__(self, components):
        self.components = components
        self.version = components.selector_version

    def select(self, snapshot, account, proposals):
        return self.components.select(snapshot, account, proposals)


def replay_portfolio(run_dir, out_dir):
    source = Path(run_dir)
    report = json.loads((source / "report.json").read_text())
    manifest = report["manifest"]
    rows = json.loads((source / "cassette.json").read_text())
    bundle_artifact = json.loads((source / "policy_bundle.json").read_text())
    if code_hash() != manifest["engine_hash"]:
        raise ValueError("portfolio replay source integrity mismatch")
    if Dataset.load(source / "dataset.json").sha256 != manifest["dataset_hash"]:
        raise ValueError("portfolio replay dataset integrity mismatch")
    if digest(rows) != manifest["cassette_hash"]:
        raise ValueError("portfolio replay cassette integrity mismatch")
    bundle = PolicyBundle.from_artifact(bundle_artifact)
    if digest(bundle_artifact) != manifest["policy_bundle_artifact_hash"] or bundle.bundle_id != manifest["policy_bundle_id"]:
        raise ValueError("portfolio replay policy bundle integrity mismatch")
    for wake in report["wakes"]:
        saved = (source / "snapshots" / f"{wake['wake_id']}.json").read_text()
        if hashlib.sha256(saved.encode()).hexdigest() != wake["snapshot_hash"]:
            raise ValueError("portfolio replay saved snapshot integrity mismatch")
    for row in rows:
        candidate_hash = digest({"request_hash": row["request_hash"], "candidates": row["candidates"]})
        if candidate_hash != row["candidate_set_hash"]:
            raise ValueError("portfolio replay candidate integrity mismatch")
        if "error_stage" not in row:
            selection_hash = digest({"candidate_set_hash": candidate_hash, "selected_id": row["selected_id"],
                                     "selector_version": manifest["selector_version"]})
            if selection_hash != row["selection_hash"]:
                raise ValueError("portfolio replay selection integrity mismatch")
        elif row["error_stage"] != "selector" or not isinstance(row.get("error"), str):
            raise ValueError("unsupported portfolio replay failure record")
    components = _RecordedComponents(rows, manifest, bundle_artifact)
    selector = _RecordedSelector(components)
    result = run_portfolio(source / "dataset.json", manifest["config"], components, selector, components, out_dir)
    if components.index != len(rows):
        raise ValueError("portfolio replay did not consume every record")
    compared = ("status", "wakes", "candidate_sets", "selections", "orders", "fills", "account", "errors", "verify_gate")
    regenerated_rows = json.loads((Path(out_dir) / "cassette.json").read_text())
    if regenerated_rows != rows or result["manifest"]["cassette_hash"] != manifest["cassette_hash"]:
        raise ValueError("portfolio replay cassette/request/decision mismatch")
    if any(result[key] != report[key] for key in compared):
        raise ValueError("portfolio replay ledger mismatch")
    return result
