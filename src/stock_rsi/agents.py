import json
import os
import math
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .data import canonical, digest
from .models import Decision

DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"action": {"type": "string", "enum": ["BUY", "SELL", "HOLD", "ABSTAIN"]},
                   "security_id": {"type": "string"}, "quantity": {"type": "integer", "minimum": 0},
                   "evidence_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
    "required": ["action", "security_id", "quantity", "evidence_ids", "reason"],
}


def bounded_output(process, timeout, answer, entry):
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    ceilings = {"stdout": 1000000, "stderr": 100000}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for name in buffers:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    entry["status"] = "TIMEOUT"
                    raise RuntimeError("Codex process timed out")
                if answer.exists() and answer.stat().st_size > 100000:
                    entry["status"] = "OUTPUT_BUDGET_EXCEEDED"
                    raise ValueError("Codex answer exceeds byte budget")
                for key, _ in selector.select(min(.05, remaining)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    if len(buffers[name]) + len(chunk) > ceilings[name]:
                        entry["status"] = "OUTPUT_BUDGET_EXCEEDED"
                        raise ValueError("Codex stream exceeds byte budget")
                    buffers[name].extend(chunk)
        process.wait()
        if answer.exists() and answer.stat().st_size > 100000:
            entry["status"] = "OUTPUT_BUDGET_EXCEEDED"
            raise ValueError("Codex answer exceeds byte budget")
        return buffers["stdout"].decode(), buffers["stderr"].decode(errors="replace")
    finally:
        # The leader may have exited while descendants still hold the pipes.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for name, limit in (("stdout", 100000), ("stderr", 4000)):
            entry[name] = buffers[name][-limit:].decode(errors="replace")
            getattr(process, name).close()


class CodexClient:
    """Opt-in CLI bridge. It is engineering-only, not a strong isolation claim."""

    def __init__(self, command=None, timeout=90, max_calls=3, model="gpt-6.1-sol"):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0 or type(max_calls) is not int or max_calls < 1:
            raise ValueError("positive timeout/call budget required")
        self.command = list(command or ["codex"])
        if not isinstance(model, str) or not model or model.startswith("-"):
            raise ValueError("explicit model ID required")
        self.model = model
        self.timeout, self.max_calls = timeout, max_calls
        self.calls = []

    def call(self, prompt, schema):
        if len(self.calls) >= self.max_calls:
            raise RuntimeError("agent call budget exhausted")
        entry = {"request_hash": digest({"prompt": prompt, "schema": schema, "model": self.model}), "model": self.model,
                 "command": self.command, "reasoning_effort": "low", "status": "STARTED", "usage": None}
        self.calls.append(entry)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="stock-rsi-snapshot-agent-") as directory:
            root = Path(directory)
            (root/"schema.json").write_text(canonical(schema))
            answer = root/"answer.json"
            command = self.command + ["exec", "--ephemeral", "--json", "--ignore-user-config",
                       "--model", self.model, "--config", 'model_reasoning_effort="low"',
                       "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(root),
                       "--output-schema", str(root/"schema.json"), "--output-last-message", str(answer), "-"]
            try:
                if len(prompt.encode()) > 60000:
                    raise ValueError("snapshot prompt exceeds byte budget")
                prompt_path = root/"prompt.txt"
                prompt_path.write_text(prompt)
                with prompt_path.open("rb") as input_file:
                    process = subprocess.Popen(command, stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               cwd=root, start_new_session=True)
                    stdout, stderr = bounded_output(process, self.timeout, answer, entry)
                entry["exit_code"] = process.returncode
                if process.returncode:
                    entry["status"] = "PROCESS_ERROR"
                    raise RuntimeError(f"Codex exited with code {process.returncode}")
                events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
                for event in events:
                    if not isinstance(event, dict):
                        raise ValueError("invalid Codex event")
                    item = event.get("item")
                    if isinstance(item, dict) and item.get("type") not in ("reasoning", "agent_message"):
                        entry["status"] = "TOOL_ACTIVITY_REJECTED"
                        raise ValueError("tools are forbidden in snapshot-only runs")
                    if event.get("type") in ("error", "turn.failed"):
                        raise ValueError("Codex reported a failed turn")
                    if event.get("type") == "turn.completed":
                        entry["usage"] = event.get("usage")
                usage = entry["usage"]
                if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")):
                    raise ValueError("complete Codex token usage is required")
                if usage["input_tokens"] > 20000 or usage["output_tokens"] > 4000:
                    raise ValueError("Codex token budget exceeded")
                result = json.loads(answer.read_text())
                if not isinstance(result, dict):
                    raise ValueError("Codex result must be an object")
                entry.update(status="COMPLETED", response=result, response_hash=digest(result))
                return result
            except Exception:
                if entry["status"] == "STARTED":
                    entry["status"] = "INVALID_OUTPUT"
                raise
            finally:
                entry["duration_seconds"] = round(time.monotonic()-started, 6)


class CodexAgent:
    def __init__(self, skill, command=None, timeout=90, max_calls=3, model="gpt-6.1-sol"):
        self.skill = skill
        self.client = CodexClient(command, timeout, max_calls, model)
        self.version = "codex-cli-snapshot-v1:" + model + ":low:" + skill.sha256

    @property
    def calls(self):
        return self.client.calls

    def decide(self, snapshot, wake, account):
        prompt = ("SNAPSHOT_ONLY A-share engineering experiment. Do not use any tools, filesystem, web, "
                  "MCP or external memory. Only the following dated input is permitted. Do not infer hidden "
                  "future facts. Return the JSON schema only, with a short reason and visible record IDs. "
                  "Use this bounded trend-pullback skill as the initial investment hypothesis. BUY/SELL "
                  "quantities must be multiples of 100, affordable, and at most 100 shares for this smoke. "
                  "HOLD/ABSTAIN quantities are zero. If information is insufficient, ABSTAIN. "
                  "Execution is next-session; current snapshot does not include next-session prices.\n" +
                  canonical({"skill":self.skill.to_dict(),"snapshot":snapshot.to_dict(),"wake":wake.to_dict(),"account":account}))
        result = self.client.call(prompt, DECISION_SCHEMA)
        try:
            decision = Decision.from_dict(result, snapshot)
            if decision.action in ("BUY", "SELL") and (decision.quantity > 100 or decision.quantity % 100):
                raise ValueError("Codex smoke orders require exactly one 100-share lot")
            return decision
        except ValueError:
            self.calls[-1]["status"] = "INVALID_DECISION"
            raise
