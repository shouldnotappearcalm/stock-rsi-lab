from decimal import Decimal, ROUND_DOWN

from .data import Snapshot
from .models import Decision
from .portfolio import PortfolioProposal, account_hash


def _visible_closes(snapshot: Snapshot):
    rows = [row for row in snapshot.to_dict()["records"] if row.get("kind") == "bar"]
    prices = {}
    for row in sorted(rows, key=lambda item: item["payload"]["trade_date"]):
        value = Decimal(str(row["payload"]["close"]))
        if not value.is_finite() or value <= 0:
            raise ValueError("target planning requires positive finite closes")
        prices[row["security_id"]] = value
    return prices


def plan_target_orders(
    proposal: PortfolioProposal,
    snapshot: Snapshot,
    account: dict,
):
    if not isinstance(proposal, PortfolioProposal):
        raise ValueError("validated PortfolioProposal required")
    if proposal.snapshot_hash != snapshot.sha256 or proposal.account_hash != account_hash(account):
        raise ValueError("proposal does not match snapshot/account")
    if not isinstance(account.get("positions"), dict):
        raise ValueError("account positions required")
    equity = Decimal(str(account.get("equity")))
    if not equity.is_finite() or equity <= 0:
        raise ValueError("positive finite account equity required")
    target_weights = {row.security_id: row.decimal for row in proposal.targets if row.security_id != "CASH"}
    current = {}
    for security, position in account["positions"].items():
        quantity = position.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("positive integer position quantity required")
        current[security] = quantity
    prices = _visible_closes(snapshot)
    changes = []
    for security in sorted(set(current) | set(target_weights)):
        weight = target_weights.get(security, Decimal(0))
        held = current.get(security, 0)
        if (weight > 0 or held > 0) and security not in prices:
            raise ValueError(f"visible close required for target planning: {security}")
        desired = int((equity * weight / prices[security]).to_integral_value(rounding=ROUND_DOWN)) if weight > 0 else 0
        if desired > held:
            quantity = (desired - held) // 100 * 100
            action = "BUY"
        else:
            quantity = held - desired
            action = "SELL"
        if quantity > 0:
            changes.append((action, security, quantity))
    changes.sort(key=lambda row: (0 if row[0] == "SELL" else 1, row[1]))
    return tuple(Decision.from_dict({
        "action": action,
        "security_id": security,
        "quantity": quantity,
        "evidence_ids": list(proposal.evidence_ids),
        "reason": f"portfolio proposal {proposal.proposal_id} target rebalance",
    }, snapshot) for action, security, quantity in changes)
