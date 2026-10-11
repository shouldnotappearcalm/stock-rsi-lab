"""Bounded development-only module search. No efficacy or recursive-RSI claim."""
import json
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

from .data import Dataset, canonical, digest
from .runner import run, visible_prices
from .skill import RuleAgent, Skill
from .time import iso, parse_time

CATALOG = {
    "shallower-pullback": {"min_pullback": .005},
    "deeper-pullback": {"min_pullback": .03},
    "shorter-hold": {"max_holding_sessions": 2},
    "longer-hold": {"max_holding_sessions": 8},
}
DEFAULT_ARMS = ("fixed", "grid", "random", "evidence", "shuffled")
PROPOSAL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"candidate_id": {"type": "string", "enum": list(CATALOG)},
                   "reason": {"type": "string"},
                   "feedback_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["candidate_id", "reason", "feedback_ids"],
}


def validate_proposal(value, catalog, feedback, used):
    if not isinstance(value, dict) or set(value) != {"candidate_id", "reason", "feedback_ids"}:
        raise ValueError("invalid proposal contract")
    key = value["candidate_id"]
    if not isinstance(key, str) or key not in catalog or key in used:
        raise ValueError("unknown or repeated candidate")
    ids = value["feedback_ids"]
    if not isinstance(value["reason"], str) or not value["reason"].strip() or not isinstance(ids, list) or not ids:
        raise ValueError("proposal requires reason and feedback evidence")
    visible = {row["case_id"] for row in feedback}
    if any(not isinstance(item, str) or item not in visible for item in ids):
        raise ValueError("proposal refers to unavailable feedback")
    return key


class CodexProposer:
    def __init__(self, client):
        self.client = client

    @property
    def calls(self):
        return self.client.calls

    def propose(self, catalog, feedback, used):
        prompt = ("SNAPSHOT_ONLY A-share engineering module-search experiment. Use no tools, filesystem, "
                  "web, MCP or external memory. Choose ONE unused candidate ID from this fixed catalog. "
                  "All patches apply to the frozen seed. Cite the provided feedback case IDs and give "
                  "a short falsifiable reason. These are synthetic/engineering observations, not evidence "
                  "of alpha. Output only the JSON schema.\n" +
                  canonical({"catalog": catalog, "feedback": feedback, "used": sorted(used)}))
        return self.client.call(prompt, PROPOSAL_SCHEMA)


def metrics(report, initial_cash="100000"):
    equity = Decimal(report["account"]["equity"])
    peak = Decimal(initial_cash)
    drawdown = Decimal(0)
    # Only known account marks; this is a diagnostic, not a return inference gate.
    values = [Decimal(row["account"]["equity"]) for row in report["wakes"]
              if all(p["mark_source"] == "VISIBLE_PRICE" for p in row["account"]["positions"].values())]
    for value in values + [equity]:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak-value)/peak)
    return {"net_return": str(equity/Decimal(initial_cash)-1),
            "max_observed_drawdown": str(drawdown), "fills": len(report["fills"]),
            "errors": len(report["errors"])}


def marked_equity(data, report, at):
    cash = Decimal(report["manifest"]["config"].get("initial_cash", "100000"))
    positions = {}
    for fill in report["fills"]:
        if parse_time(fill["execution_at"]) <= at:
            cash = Decimal(fill["cash_after"])
            key = fill["security_id"]
            positions[key] = positions.get(key, 0) + (fill["quantity"] if fill["action"] == "BUY" else -fill["quantity"])
    prices = visible_prices(data.snapshot(at))
    if any(qty and key not in prices for key, qty in positions.items()):
        raise ValueError("feedback valuation missing visible price")
    return cash + sum((qty * Decimal(str(prices[key])) for key, qty in positions.items() if qty), Decimal(0))


def feedback_cases(data, report):
    cutoff = parse_time(report["manifest"]["config"]["end"])
    # One resolved version of each visible fact, not a mixture of revisions.
    bars = [row for row in data.snapshot(cutoff).to_dict()["records"] if row["kind"] == "bar"]
    bars.sort(key=lambda row: (row["payload"]["trade_date"], row["security_id"]))
    cases = []
    for security in sorted({row["security_id"] for row in bars}):
        rows = [row for row in bars if row["security_id"] == security]
        for index in range(3):
            part = rows[len(rows)*index//3:len(rows)*(index+1)//3]
            if len(part) < 2:
                continue
            closes = [Decimal(str(row["payload"]["close"])) for row in part]
            peak, dd = closes[0], Decimal(0)
            for value in closes:
                peak = max(peak, value); dd = max(dd, (peak-value)/peak)
            start = data.calendar.at(date.fromisoformat(part[0]["payload"]["trade_date"]), "17:00:00")
            end = min(cutoff, data.calendar.at(date.fromisoformat(part[-1]["payload"]["trade_date"]), "17:00:00"))
            strategy_return = marked_equity(data, report, end)/marked_equity(data, report, start)-1
            cases.append({"case_id": f"{security}:episode-{index}",
                          "context": {"security_id": security, "start": iso(start), "end": iso(end),
                                      "observations": len(part), "price_versions_as_of": iso(cutoff)},
                          "outcome": {"market_return": str(closes[-1]/closes[0]-1), "market_drawdown": str(dd),
                                      "strategy_return": str(strategy_return)}})
    if len(cases) < 2:
        raise ValueError("at least two development feedback episodes required")
    return cases


def shuffle_feedback(feedback):
    # A non-identity permutation preserves the types and marginal outcomes.
    outcomes = [row["outcome"] for row in feedback]
    return [row | {"outcome": outcomes[(i+1) % len(outcomes)]} for i, row in enumerate(feedback)]


def heuristic(feedback, used):
    # Explicitly an offline diagnostic; this arm is not labeled LLM evidence.
    latest = max(feedback, key=lambda row: row["context"]["end"])
    outcome = latest["outcome"]
    first = "shorter-hold" if Decimal(outcome["market_drawdown"]) > Decimal('.08') else (
        "longer-hold" if Decimal(outcome["market_return"]) > 0 else "deeper-pullback")
    key = next(key for key in [first] + sorted(CATALOG) if key not in used)
    return {"candidate_id": key, "reason": "offline heuristic from latest development episode", "feedback_ids": [latest["case_id"]]}


def run_campaign(dataset_path, registry_path, split, budget, out_dir, arms=DEFAULT_ARMS, proposer=None, random_seed=42):
    if split != "development":
        raise ValueError("evolution access denied: only development split is allowed")
    if type(budget) is not int or not 1 <= budget <= len(CATALOG):
        raise ValueError("candidate attempt budget must be 1..4")
    if not arms or len(set(arms)) != len(arms) or not set(arms) <= set(DEFAULT_ARMS) | {"codex"}:
        raise ValueError("invalid comparison arms")
    if "codex" in arms and proposer is None:
        raise ValueError("codex arm requires an explicit proposer")
    raw = json.loads(Path(dataset_path).read_text())
    data = Dataset.load(dataset_path)
    registry = json.loads(Path(registry_path).read_text())
    if registry["dataset_id"] != data.dataset_id or set(registry["splits"]) != {"development", "validation", "sealed"}:
        raise ValueError("split registry identity mismatch")
    intervals = sorted((parse_time(v["start"]), parse_time(v["end"]), k) for k, v in registry["splits"].items())
    if [item[2] for item in intervals] != ["development", "validation", "sealed"] or any(start > end for start, end, _ in intervals) or any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("split registry overlaps or has invalid intervals")
    config = registry["splits"][split] | {"initial_cash": "100000", "cost_bps": "20"}
    start, end = parse_time(config["start"]), parse_time(config["end"])
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=False)
    # The agent-facing research export contains no held-out records. Historical
    # warm-up before start is allowed; original calendar is fixed infrastructure.
    raw["records"] = [row for row in raw["records"] if parse_time(row["available_at"]) <= end]
    raw["provenance"] = raw["provenance"] | {"development_export_cutoff": iso(end), "source_dataset_hash": data.sha256}
    development_path = out/"development.json"; development_path.write_text(canonical(raw))
    development = Dataset.load(development_path)
    seed = Skill()
    baseline = run(development_path, config, RuleAgent(seed), out/"baseline")
    if baseline["status"] != "COMPLETED_ENGINEERING":
        raise ValueError("invalid development baseline")
    feedback = feedback_cases(development, baseline)
    report = {"status": "ENGINEERING_NO_EFFICACY", "source_dataset_hash": data.sha256,
              "evidence_level": data.evidence_level, "split": split, "registry_hash": digest(registry),
              "candidate_budget_per_arm": budget, "random_seed": random_seed,
              "catalog": CATALOG, "baseline_metrics": metrics(baseline), "feedback": feedback,
              "feedback_original_hash": digest(feedback), "arms": {},
              "limitations": ["tiny engineering experiment", "no sealed evaluation", "seed-relative catalog search; not recursive RSI",
                              "offline evidence heuristic is not an LLM", "CLI isolation is not an OS data boundary"]}
    for name in arms:
        current_feedback = shuffle_feedback(feedback) if name == "shuffled" else feedback
        result = {"feedback_hash": digest(current_feedback), "trials": [], "valid_evaluations": 0,
                  "best_skill_hash": seed.sha256, "best_metrics": metrics(baseline)}
        used = set(); rng = random.Random(random_seed)
        random_order = rng.sample(sorted(CATALOG), len(CATALOG))
        for attempt in range(budget):
            trial = {"attempt": attempt+1, "feedback_hash": digest(current_feedback), "feedback": json.loads(canonical(current_feedback))}
            try:
                if name == "fixed":
                    key, patch, skill = "seed", {}, seed
                else:
                    if name == "codex":
                        proposal = proposer.propose(json.loads(canonical(CATALOG)), json.loads(canonical(current_feedback)), used.copy())
                    elif name in ("evidence", "shuffled"):
                        proposal = heuristic(current_feedback, used)
                    else:
                        key = sorted(CATALOG)[attempt] if name == "grid" else random_order[attempt]
                        proposal = {"candidate_id": key, "reason": name+" control", "feedback_ids": [current_feedback[0]["case_id"]]}
                    trial["proposal"] = proposal
                    key = validate_proposal(proposal, CATALOG, current_feedback, used)
                    patch = CATALOG[key].copy(); skill = seed.patch(patch); used.add(key)
                trial.update(candidate_id=key, patch=patch, skill_hash=skill.sha256)
                evaluated = run(development_path, config, RuleAgent(skill), out/name/f"attempt-{attempt+1}")
                trial.update(status="EVALUATED" if evaluated["status"] == "COMPLETED_ENGINEERING" else "INVALID_EVALUATION",
                             metrics=metrics(evaluated), run_status=evaluated["status"])
                if trial["status"] == "EVALUATED":
                    result["valid_evaluations"] += 1
                    if Decimal(trial["metrics"]["net_return"]) > Decimal(result["best_metrics"]["net_return"]):
                        result.update(best_skill_hash=skill.sha256, best_metrics=trial["metrics"])
                    updated = feedback_cases(development, evaluated)
                    current_feedback = shuffle_feedback(updated) if name == "shuffled" else updated
            except (ValueError, RuntimeError, OSError) as exc:
                trial.update(status="INVALID_PROPOSAL" if "skill_hash" not in trial else "INVALID_EVALUATION", error=str(exc))
            result["trials"].append(trial)
            (out/"ledger.json").write_text(canonical(report | {"in_progress_arm": name, "in_progress_trials": result["trials"]}))
        report["arms"][name] = result
    if any(arm["valid_evaluations"] != budget for arm in report["arms"].values()):
        report["status"] = "INVALID_CAMPAIGN"
    report["proposal_calls"] = getattr(proposer, "calls", [])
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (out/"ledger.json").write_text(canonical(report))
    return report
