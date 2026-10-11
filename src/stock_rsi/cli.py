import argparse
import json
import sys
from pathlib import Path

from .data import Dataset
from .runner import replay, run
from .skill import RuleAgent, Skill
from .time import parse_time


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stock-rsi")
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot", help="inspect a point-in-time serialized view")
    snap.add_argument("--dataset", required=True)
    snap.add_argument("--as-of", required=True)
    replay_parser = commands.add_parser("replay", help="verify fixed-response replay and ledger")
    replay_parser.add_argument("--run-dir", required=True)
    replay_parser.add_argument("--output", required=True)
    compare = commands.add_parser("compare", help="bounded development-only skill-search comparison")
    compare.add_argument("--dataset", required=True)
    compare.add_argument("--splits", required=True)
    compare.add_argument("--split", default="development")
    compare.add_argument("--budget", type=int, default=2)
    compare.add_argument("--output", required=True)
    compare.add_argument("--arms", default="fixed,grid,random,evidence,shuffled")
    compare.add_argument("--codex-bin", default="codex")
    compare.add_argument("--model", default="gpt-6.1-sol")
    compare.add_argument("--agent-timeout", type=float, default=60)
    runner = commands.add_parser("run", help="run an explicit historical range")
    runner.add_argument("--dataset", required=True)
    runner.add_argument("--start", required=True)
    runner.add_argument("--end", required=True)
    runner.add_argument("--output", required=True)
    runner.add_argument("--skill")
    runner.add_argument("--initial-cash", default="100000")
    runner.add_argument("--cost-bps", default="20")
    runner.add_argument("--agent", choices=("rule", "codex"), default="rule")
    runner.add_argument("--max-agent-calls", type=int, default=3)
    runner.add_argument("--agent-timeout", type=float, default=90)
    runner.add_argument("--codex-bin", default="codex")
    runner.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            snapshot = Dataset.load(args.dataset).snapshot(parse_time(args.as_of))
            print(json.dumps({"snapshot_hash": snapshot.sha256, "snapshot": snapshot.to_dict()}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "compare":
            from .campaign import CodexProposer, run_campaign
            arms = tuple(args.arms.split(","))
            proposer = None
            if "codex" in arms:
                from .agents import CodexClient
                proposer = CodexProposer(CodexClient([args.codex_bin], args.agent_timeout, args.budget, args.model))
            report = run_campaign(args.dataset, args.splits, args.split, args.budget, args.output, arms, proposer)
            print(json.dumps({"status": report["status"], "evidence_level": report["evidence_level"],
                              "arms": {key: {"valid_evaluations": value["valid_evaluations"], "best_metrics": value["best_metrics"]}
                                       for key, value in report["arms"].items()}}, ensure_ascii=False, indent=2))
            return 0 if all(value["valid_evaluations"] == args.budget for value in report["arms"].values()) else 2
        if args.command == "replay":
            report = replay(args.run_dir, args.output)
        else:
            skill = Skill.load(args.skill) if args.skill else Skill()
            if args.agent == "rule":
                agent = RuleAgent(skill)
            else:
                from .agents import CodexAgent
                agent = CodexAgent(skill, command=[args.codex_bin], max_calls=args.max_agent_calls, timeout=args.agent_timeout, model=args.model)
            report = run(args.dataset, {"start": args.start, "end": args.end,
                         "initial_cash": args.initial_cash, "cost_bps": args.cost_bps}, agent, args.output)
        summary = {"status": report["status"], "dataset": report["manifest"]["dataset_id"],
                   "evidence_level": report["manifest"]["evidence_level"], "wakes": len(report["wakes"]),
                   "fills": len(report["fills"]), "account": report["account"], "errors": report["errors"]}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "COMPLETED_ENGINEERING" else 2
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"stock-rsi: {exc}", file=sys.stderr)
        return 2
