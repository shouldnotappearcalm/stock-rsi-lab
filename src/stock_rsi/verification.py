"""Separate executable correctness from eligibility for research promotion."""
from decimal import Decimal, InvalidOperation


def verify_run(report):
    failures = [f"{row['stage']}: {row['error']}" for row in report['errors']]
    if report['status'] != 'COMPLETED_ENGINEERING':
        failures.append('run did not complete successfully')
    try:
        account=report['account']
        cash,equity=Decimal(account['cash']),Decimal(account['equity'])
        market_value=Decimal(account['market_value'])
        if not cash.is_finite() or cash<0 or not equity.is_finite() or equity<0:
            failures.append('invalid account cash/equity')
        if any(type(p['quantity']) is not int or p['quantity']<=0 for p in account['positions'].values()):
            failures.append('invalid holding quantity')
        holdings_value=Decimal(0)
        for position in account['positions'].values():
            price=Decimal(position['mark_price'])
            if not price.is_finite() or price<=0:
                failures.append('invalid mark price')
            holdings_value+=price*position['quantity']
        if not market_value.is_finite() or market_value<0 or market_value!=holdings_value or equity!=cash+market_value:
            failures.append('account value does not conserve cash and marked holdings')
    except (ValueError,InvalidOperation,KeyError,TypeError):
        failures.append('invalid account contract')
    provenance=report['manifest']['provenance']
    warnings=list(provenance.get('assumptions',[]))+list(provenance.get('limitations',[]))
    if report['manifest']['evidence_level']!='PIT_RESEARCH_VERIFIED':
        warnings.append('dataset is not verified PIT research evidence')
    return {'version':'two-level-v1',
            'hard_checks':{'status':'FAIL' if failures else 'PASS','failures':failures},
            'exploratory_backtest_allowed':not failures,
            'warnings':warnings,
            'research_promotion_allowed':False,
            'promotion_reasons':['No independent preregistered efficacy evaluation has been completed'],
            'policy':'Data assumptions annotate exploratory results; time, evidence, runtime and accounting errors fail closed.'}


def verify_portfolio_run(report):
    gate = verify_run(report)
    failures = list(gate["hard_checks"]["failures"])
    try:
        sets = {row["candidate_set_hash"]: row for row in report["candidate_sets"]}
        if len(sets) != len(report["candidate_sets"]):
            failures.append("duplicate candidate-set hash")
        for row in report["candidate_sets"]:
            candidates = row["candidates"]
            ids = [candidate["proposal_id"] for candidate in candidates]
            if len(candidates) < 2 or len(ids) != len(set(ids)) or ids.count("keep-current") != 1:
                failures.append("invalid portfolio candidate set")
            identity = {(candidate["snapshot_hash"], candidate["account_hash"], candidate["policy_bundle_id"])
                        for candidate in candidates}
            if len(identity) != 1:
                failures.append("portfolio candidates mix identities")
        for selection in report["selections"]:
            candidate_set = sets[selection["candidate_set_hash"]]
            ids = {candidate["proposal_id"] for candidate in candidate_set["candidates"]}
            if selection["selected_id"] not in ids:
                failures.append("selection is absent from candidate set")
    except (KeyError, TypeError):
        failures.append("invalid portfolio candidate/selection contract")
    failures = list(dict.fromkeys(failures))
    gate["version"] = "portfolio-two-level-v1"
    gate["hard_checks"] = {"status": "FAIL" if failures else "PASS", "failures": failures}
    gate["exploratory_backtest_allowed"] = not failures
    return gate
