import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .data import Snapshot, canonical, digest
from .factors import FactorFrame
from .portfolio import PortfolioProposal, account_hash, keep_current_proposal
from .time import parse_time


MODULE_NAMES = frozenset({
    "universe_filter", "regime_policy", "candidate_ranker", "entry_policy",
    "exit_policy", "portfolio_constructor", "execution_policy",
})
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PolicyBundle:
    root: Path
    manifest_json: str
    modules_json: tuple[tuple[str, str], ...]
    bundle_id: str

    @classmethod
    def load(cls, path: str | Path):
        root = Path(path)
        manifest_path = root / "manifest.json"
        if root.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("policy bundle requires a regular manifest")
        manifest = json.loads(manifest_path.read_text())
        fields = {"schema_version", "name", "parent_bundle_id", "factor_schema_ids", "modules", "description"}
        if not isinstance(manifest, dict) or set(manifest) != fields:
            raise ValueError("policy bundle manifest fields do not match schema")
        if manifest["schema_version"] != "policy-bundle-v1":
            raise ValueError("unsupported policy bundle schema")
        for name in ("name", "description"):
            if not isinstance(manifest[name], str) or not manifest[name].strip():
                raise ValueError(f"nonempty {name} required")
        parent = manifest["parent_bundle_id"]
        if parent is not None and (not isinstance(parent, str) or not HASH_PATTERN.fullmatch(parent)):
            raise ValueError("parent_bundle_id must be null or a SHA-256")
        factors = manifest["factor_schema_ids"]
        if (not isinstance(factors, list) or
                not all(isinstance(item, str) and item for item in factors) or
                len(factors) != len(set(factors))):
            raise ValueError("factor_schema_ids must be unique strings")
        modules = manifest["modules"]
        if not isinstance(modules, dict) or set(modules) != MODULE_NAMES:
            raise ValueError("policy bundle requires the exact module set")
        loaded = {}
        for name, filename in modules.items():
            if (not isinstance(filename, str) or not filename or
                    Path(filename).name != filename or Path(filename).suffix != ".json"):
                raise ValueError("module paths must be simple JSON basenames")
            module_path = root / filename
            if module_path.is_symlink() or not module_path.is_file():
                raise ValueError("policy modules must be regular files")
            value = json.loads(module_path.read_text())
            if not isinstance(value, dict) or set(value) != {"schema_version", "module", "mode", "parameters"}:
                raise ValueError("policy module fields do not match schema")
            if value["schema_version"] != "policy-module-v1" or value["module"] != name:
                raise ValueError("policy module identity mismatch")
            if not isinstance(value["mode"], str) or not value["mode"] or not isinstance(value["parameters"], dict):
                raise ValueError("invalid policy module mode or parameters")
            loaded[name] = value
        return cls._validated(root.resolve(), manifest, loaded)

    @classmethod
    def from_artifact(cls, artifact: dict):
        if not isinstance(artifact, dict) or set(artifact) != {"bundle_id", "manifest", "modules"}:
            raise ValueError("complete policy bundle artifact required")
        manifest, modules = artifact["manifest"], artifact["modules"]
        if not isinstance(manifest, dict) or not isinstance(modules, dict):
            raise ValueError("invalid policy bundle artifact")
        result = cls._validated(Path("<artifact>"), manifest, modules)
        if artifact["bundle_id"] != result.bundle_id:
            raise ValueError("policy bundle artifact content hash mismatch")
        return result

    @classmethod
    def _validated(cls, root, manifest, loaded):
        fields = {"schema_version", "name", "parent_bundle_id", "factor_schema_ids", "modules", "description"}
        if not isinstance(manifest, dict) or set(manifest) != fields:
            raise ValueError("policy bundle manifest fields do not match schema")
        if manifest["schema_version"] != "policy-bundle-v1":
            raise ValueError("unsupported policy bundle schema")
        for field in ("name", "description"):
            if not isinstance(manifest[field], str) or not manifest[field].strip():
                raise ValueError(f"nonempty {field} required")
        parent = manifest["parent_bundle_id"]
        if parent is not None and (not isinstance(parent, str) or not HASH_PATTERN.fullmatch(parent)):
            raise ValueError("parent_bundle_id must be null or a SHA-256")
        factors = manifest["factor_schema_ids"]
        if (not isinstance(factors, list) or
                not all(isinstance(item, str) and item for item in factors) or
                len(factors) != len(set(factors))):
            raise ValueError("factor_schema_ids must be unique strings")
        modules = manifest["modules"]
        if (not isinstance(modules, dict) or set(modules) != MODULE_NAMES or
                not all(isinstance(value, str) and value for value in modules.values())):
            raise ValueError("policy bundle manifest requires the exact module set")
        if not isinstance(loaded, dict) or set(loaded) != MODULE_NAMES:
            raise ValueError("policy bundle artifact requires the exact module set")
        for name, value in loaded.items():
            if (not isinstance(value, dict) or
                    set(value) != {"schema_version", "module", "mode", "parameters"} or
                    value["schema_version"] != "policy-module-v1" or value["module"] != name or
                    not isinstance(value["mode"], str) or not value["mode"] or
                    not isinstance(value["parameters"], dict)):
                raise ValueError("invalid policy module artifact")
        identity = digest({"manifest": manifest, "modules": loaded})
        return cls(root, canonical(manifest), tuple((name, canonical(loaded[name])) for name in sorted(loaded)), identity)

    def module(self, name: str):
        for key, payload in self.modules_json:
            if key == name:
                return json.loads(payload)
        raise KeyError(name)

    def to_dict(self):
        return {
            "bundle_id": self.bundle_id,
            "manifest": json.loads(self.manifest_json),
            "modules": {name: json.loads(payload) for name, payload in self.modules_json},
        }


@runtime_checkable
class FactorProvider(Protocol):
    version: str

    def build(self, snapshot, wake, account) -> FactorFrame: ...


@runtime_checkable
class PortfolioPolicy(Protocol):
    bundle_id: str

    def propose(self, snapshot, wake, account, factors) -> tuple[PortfolioProposal, ...]: ...


@runtime_checkable
class ProposalSelector(Protocol):
    version: str

    def select(self, snapshot, account, proposals) -> str: ...


def validate_candidate_set(
    policy: PortfolioPolicy,
    snapshot: Snapshot,
    account: dict,
    proposals,
):
    if not isinstance(policy, PortfolioPolicy):
        raise ValueError("policy does not satisfy PortfolioPolicy")
    if not isinstance(proposals, (tuple, list)) or len(proposals) < 2:
        raise ValueError("policy must produce at least two proposals")
    if not all(isinstance(row, PortfolioProposal) for row in proposals):
        raise ValueError("candidate set contains a non-proposal")
    visible = {row["security_id"] for row in snapshot.to_dict()["records"]}
    eligible = visible | set(account.get("positions", {}))
    revalidated = [PortfolioProposal.from_dict(row.to_dict(), snapshot, account, eligible, policy.bundle_id)
                   for row in proposals]
    ordered = tuple(sorted(revalidated, key=lambda row: row.proposal_id))
    ids = [row.proposal_id for row in ordered]
    if len(ids) != len(set(ids)) or ids.count("keep-current") != 1:
        raise ValueError("candidate IDs must be unique and include keep-current exactly once")
    expected_account = account_hash(account)
    for row in ordered:
        if row.snapshot_hash != snapshot.sha256 or row.account_hash != expected_account or row.policy_bundle_id != policy.bundle_id:
            raise ValueError("candidate set mixes snapshot, account or policy identities")
    keep = next(row for row in ordered if row.proposal_id == "keep-current")
    expected = keep_current_proposal(
        snapshot, account, policy.bundle_id, list(keep.evidence_ids), parse_time(keep.expires_at),
    )
    if keep.targets != expected.targets:
        raise ValueError("keep-current candidate does not preserve the current account")
    return ordered


def select_proposal(
    selector: ProposalSelector,
    snapshot: Snapshot,
    account: dict,
    proposals,
):
    if not isinstance(selector, ProposalSelector):
        raise ValueError("selector does not satisfy ProposalSelector")
    selected = selector.select(snapshot, account, proposals)
    if not isinstance(selected, str) or not selected:
        raise ValueError("selector must return a proposal ID")
    matches = [row for row in proposals if row.proposal_id == selected]
    if len(matches) != 1:
        raise ValueError("selector returned an unknown proposal ID")
    return matches[0]
