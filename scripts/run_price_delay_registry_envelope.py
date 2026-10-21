"""Complete local registry-allocation tree for one unchanged frozen portfolio.

The strict failed account is immutable. Every admitted uncertainty branch is
replayed continuously; no annual result is published from an incomplete tree.
"""
import argparse
import csv
import json
from math import isfinite
from collections import deque
from copy import deepcopy
from datetime import date
from decimal import Decimal
from functools import partial
from pathlib import Path

from scripts import run_price_delay_regime_horizon as strict
from scripts.replay_regime_stock_distribution_targets import simulate_regime_fixed_targets
from scripts.reconcile_registry_account import reconcile_registry_case
from stock_rsi.execution_cost import ExecutionCostBroker
from stock_rsi.registry_allocation_account import AllocationChoiceRequired, RegistryAllocationAccount
from stock_rsi.registry_allocation_bounds import allocation_bounds

old = strict.old
read, sha, safe, need, clean, write = strict.read, strict.sha, strict.safe, strict.need, strict.clean, strict.write
OUTPUT = 'price-delay-registry-envelope-horizon-20261021'
STRICT_PLAN = 'experiments/qlib/price-delay-regime-horizon-request.json'
STRICT_AUDIT = 'experiments/qlib/price-delay-regime-horizon-failure-independent-audit.json'
PROOFS = 'experiments/qlib/price-delay-registry-allocation-proofs.json'
DESIGN = 'docs/research/registry-allocation-envelope-design-2026-10-21.md'
RESEARCH = 'experiments/qlib/price-delay-registry-fractional-rights-source-research.json'
METHOD_FILES = tuple(dict.fromkeys(strict.METHOD_FILES + (
    'src/stock_rsi/registry_allocation_bounds.py', 'src/stock_rsi/registry_allocation_account.py',
    'scripts/reconcile_registry_account.py', 'scripts/run_price_delay_registry_envelope.py')))
PUBLIC_FILES = (STRICT_PLAN, STRICT_AUDIT, PROOFS, DESIGN, RESEARCH)
PROFILE = {'status': 'FROZEN_UNCHANGED_PRICE_DELAY_COMPLETE_LOCAL_ALLOCATION_ENVELOPE',
    'candidate': old.POLICY, 'candidate_budget': 1, 'window': [old.START, old.END],
    'initial_CNY': old.CAPITAL, 'extra_cost_bps': [20, 40], 'reference_extra_bps': 40,
    'node_budget_per_cost': 128, 'allocator': 'plan_integer_targets', 'output_relative': OUTPUT,
    'resource_budget_exceeded_prohibits_ROI': True, 'all_nodes_and_costs_before_any_annual_ROI': True,
    'investment_rule_changed': False, 'risk_warning_buy_permission': False,
    'strict_failure_must_remain_unchanged': True, 'source_queries': 0,
    'actual_registry_allocation_certified': False, 'full_October_2026_complete': False}


def validate_plan(plan):
    need(all(type(plan.get(k)) is type(v) and plan[k] == v for k, v in PROFILE.items()),
         'fixed complete-tree resource budget, strategy and cost profiles required')
    for field, names in (('method_code_sha256', METHOD_FILES), ('public_evidence_sha256', PUBLIC_FILES)):
        need(set(plan[field]) == set(names), 'complete frozen tree method/source bindings required')


def load_inputs(base, repo, plan_path, expected_sha):
    base, repo, plan_path = Path(base).resolve(), Path(repo).resolve(), Path(plan_path).resolve()
    need(sha(plan_path) == expected_sha, 'external complete-tree request changed')
    plan = read(plan_path)
    validate_plan(plan)
    inputs = strict.load_inputs(base, repo, repo / STRICT_PLAN, plan['public_evidence_sha256'][STRICT_PLAN])
    known = dict(inputs['known_hashes'])
    def bind(path, expected):
        path = Path(path).resolve()
        need(path.is_relative_to(base) or path.is_relative_to(repo), 'source outside registered roots')
        need(str(path) not in known or known[str(path)] == expected, 'conflicting tree input hash')
        need(sha(path) == expected, 'frozen tree input changed: ' + str(path))
        known[str(path)] = expected
    bind(plan_path, expected_sha)
    for field in ('method_code_sha256', 'public_evidence_sha256'):
        for name, expected in plan[field].items():
            bind(safe(repo, name), expected)
    audit = read(repo / STRICT_AUDIT)
    need(audit['status'] == 'PASS_INDEPENDENT_BOUNDED_PRICE_DELAY_REGIME_FRACTIONAL_GUARD_FAILURE_AUDIT'
         and not audit['critical_or_important_findings'] and audit['failure_day'] == '2026-06-04'
         and audit['failure_instrument'] == 'SZ002831' and audit['actual_input_count'] == 531
         and audit['portfolio_returns_computed'] is False and audit['all_old60_financial_bytes_unchanged'] is True,
         'independently reconstructed strict registry failure required')
    for name, expected in audit['all_bound_input_sha256'].items():
        bind(name, expected)
    for name, expected in audit['all_output_file_sha256'].items():
        bind(safe(base / strict.OUTPUT, name), expected)
    need(audit['summary_sha256'] == sha(base / strict.OUTPUT / 'summary.json'), 'strict failure summary changed')
    proofs = read(repo / PROOFS)
    events = {e.event_id: e for e in inputs['events']}
    reviewed = read(base / old.PROOFDIR / 'reviewed-manifest.json')['documents']
    reviewed = list(reviewed.values()) if isinstance(reviewed, dict) else reviewed
    need(type(proofs) is dict and bool(proofs), 'explicit primary proof map required')
    for event_id, components in proofs.items():
        need(event_id in events and set(components) == {'capital'}, 'only reviewed capital-component proof admitted')
        event = events[event_id]
        proof = components['capital']
        document = [d for d in reviewed if d['file'] == proof['source_file'] and d['instrument'] == proof['issuer']]
        need(len(document) == 1, 'unique existing reviewed issuer original required')
        document = document[0]
        bind(base / old.PROOFDIR / document['file'], proof['source_sha256'])
        need(document['sha256'] == proof['source_sha256']
             and document['fractional_share_method'].startswith('Largest fractional remainders first')
             and int(document['eligible_share_count']) == proof['eligible_count']
             and int(document['issuer_capital_shares']) == proof['declared_total_shares']
             and document['capital_per_10_original_shares'] == proof['quoted_per10'],
             'original primary total/base/printed component/remainder method required')
        RegistryAllocationAccount._bound_envelope(event, 'capital', proof, 0)
    inputs.update(plan=plan, registry_proofs=proofs, known_hashes=known,
        strict_prefix={cost: {'case': read(base / strict.OUTPUT / str(cost) / 'partial_case.json'),
                             'state': read(base / strict.OUTPUT / str(cost) / 'failed_account_state.json')}
                       for cost in old.COSTS})
    strict.verify_hashes(known)
    return inputs


def choices_id(choices):
    return old.digest(choices)


def child_choices(choices, request):
    event_id, component = request['event_id'], request['component']
    need(component not in choices.get(event_id, {}), 'a completed choice point cannot recur')
    candidates = request['candidates']
    need(type(candidates) is list and candidates == sorted(set(candidates)) and 0 < len(candidates) <= 3
         and all(type(q) is int and q >= 0 for q in candidates), 'complete canonical local candidate list required')
    envelope = request['envelope']
    proof = envelope['proof']
    need(proof['event_id'] == event_id and proof['component'] == component
         and proof['issuer'] == request['instrument'], 'branch point primary identity mismatch')
    recomputed = allocation_bounds(proof, request['registered_quantity'], as_of=envelope['as_of'])
    need(clean(envelope) == clean(recomputed)
         and candidates == recomputed['possible_integer_shares'],
         'branch candidates must equal the complete independently recomputed primary envelope')
    result = []
    for quantity in candidates:
        child = deepcopy(choices)
        child.setdefault(event_id, {})[component] = quantity
        result.append(child)
    return result


class CheckpointRegistryAccount(RegistryAllocationAccount):
    def end_day(self, day):
        super().end_day(day)
        if day.isoformat() == old.PRE and not hasattr(self, 'pre2026_checkpoint'):
            self.pre2026_checkpoint = deepcopy(clean({
                'orders': self.broker.orders, 'fills': self.broker.fills,
                'corporate_ledger': self.corporate_ledger}))


def require_strict_prefix(case, prior):
    trace, state = prior['case'], prior['state']
    need(len(trace['rows']) == 584 and len(trace['intents']) == 30, 'complete strict584day/30intent anchor required')
    cut = '2026-06-04'
    need(clean(case['days'][:584]) == trace['rows']
         and clean([r for r in case['intents'] if r['execution_session'] < cut]) == trace['intents']
         and clean({d: q for d, q in case['ownership'].items() if d < cut}) == trace['ownership']
         and clean([r for r in case['fills'] if r['execution_at'][:10] < cut]) == state['fills']
         and clean([r for r in case['corporate_ledger'] if str(r['day']) < cut]) == state['corporate_ledger'],
         'allocation model changed pre-June4 strict account history')


def validate_leaf(case, account, inputs, cost):
    need([r['day'] for r in case['days']] == inputs['sessions']
         and [r['execution_session'] for r in case['intents']] == sorted(inputs['targets'])
         and len(case['intents']) == 34 and case['whole_day_volume_violations'] == 0,
         'complete676days/34intentions and observed capacity check required')
    old.verify_prefix(case, account.pre2026_checkpoint, inputs['references'][cost], inputs['old_scope'])
    strict.require_failed_financial_prefix(case, inputs['failed_prefix'][cost])
    require_strict_prefix(case, inputs['strict_prefix'][cost])
    reconcile_registry_case(case, inputs['events'], inputs['bars'], inputs['sessions'], cost,
                            registry_proofs=inputs['registry_proofs'])
    need(len(case['phase_audit']) == 4 * len(inputs['sessions'])
         and len(case['regime_audit']) == 4 * len(inputs['sessions']), 'complete phase/regime histories required')
    need(not any(o['action'] == 'BUY' and o['status'] == 'FILLED'
                 and any(s['instrument'] == o['security_id']
                         and s['effective_from'] <= o['eligible_at'][:10] <= s['effective_through']
                         for s in inputs['regime_evidence']['state_intervals']) for o in case['orders']),
         'unsigned ST account cannot acquire new ST buy fills')


def partial_trace(error):
    tb = error.__traceback__
    while tb:
        if tb.tb_frame.f_code is simulate_regime_fixed_targets.__code__:
            v = tb.tb_frame.f_locals
            return clean({key: v.get(key) for key in ('day', 'current_phase', 'rows', 'intents', 'ownership', 'phase_audit', 'lifecycle_audit')})
        tb = tb.tb_next
    return {}


def preserve_node_stop(folder, error, account, status, completed_case=None):
    result = {'status': status, 'error_type': type(error).__name__, 'error': str(error),
              'portfolio_returns_computed': False, 'persistence_errors': []}
    def attempt(name, value):
        try:
            write(folder / name, value)
        except BaseException as persistence_error:
            result['persistence_errors'].append({'file': name,
                'error_type': type(persistence_error).__name__, 'error': str(persistence_error)})
    trace = partial_trace(error)
    attempt('partial_trace.json', trace)
    if account is not None:
        attempt('account_state.json', {'last_account_clock': account._last_clock,
            'cash': account.broker.cash, 'positions': account.broker.positions,
            'orders': account.broker.orders, 'fills': account.broker.fills,
            'entitlements': account.entitlements, 'corporate_ledger': account.corporate_ledger,
            'cash_claims': account.cash_claims, 'stock_claims': account.stock_claims,
            'registry_allocation_audit': account.allocation_audit})
    if completed_case is not None:
        attempt('unvalidated_completed_case.json', completed_case)
    return result


def run_cost_tree(folder, inputs, cost, *, budget=128, node_runner=None):
    """BFS never reads ROI; every branch point must have every child queued."""
    queue = deque([{}])
    seen, nodes, leaves = set(), {}, {}
    complete, persistence_errors = True, []
    while queue:
        if len(nodes) >= budget:
            complete = False
            write(folder / 'budget-exhausted.json', {'unattempted_choices': list(queue),
                'node_budget': budget, 'portfolio_returns_computed': False})
            break
        choices = queue.popleft()
        node_id = choices_id(choices)
        need(node_id not in seen, 'duplicate choice path cannot replace an unvisited branch')
        seen.add(node_id)
        node = folder / node_id
        node.mkdir()
        write(node / 'choices.json', choices)
        if node_runner is not None:
            result, case = node_runner(choices, node)
        else:
            holders = []
            source_view, _ = strict.make_source_view(inputs)
            def factory(calendar, cash, events, **kwargs):
                account = CheckpointRegistryAccount(calendar, cash, events,
                    registry_proofs=inputs['registry_proofs'], allocation_choices=choices,
                    broker_factory=partial(ExecutionCostBroker, extra_cost_bps=cost), **kwargs)
                holders.append(account)
                return account
            case = None
            try:
                case = simulate_regime_fixed_targets(inputs['calendar'], inputs['bars'], inputs['events'],
                    inputs['targets'], old.CAPITAL, lifecycles={}, regime_evidence=inputs['regime_evidence'],
                    account_factory=factory, policy_id=old.POLICY, source_rows=source_view)
                account = holders[0]
                case['registry_allocation_audit'] = deepcopy(account.allocation_audit)
                validate_leaf(case, account, inputs, cost)
                artifacts = old.write_case(node, case, account.pre2026_checkpoint)
                for name, value in (('registry_allocation_audit.json', case['registry_allocation_audit']),
                                    ('phase_audit.json', case['phase_audit']), ('regime_audit.json', case['regime_audit'])):
                    write(node / name, value)
                    artifacts[name] = sha(node / name)
                result = {'status': 'COMPLETE_RECONCILED_LEAF_UNSCORED',
                          'artifact_sha256': artifacts, 'portfolio_returns_computed': False}
            except AllocationChoiceRequired as error:
                result = preserve_node_stop(node, error, holders[0] if holders else None, 'LOCAL_ALLOCATION_BRANCH_POINT')
                result['choice_request'] = {'event_id': error.event_id, 'instrument': error.instrument,
                    'component': error.component, 'registered_quantity': error.registered_quantity,
                    'candidates': list(error.candidates), 'envelope': error.envelope}
                case = None
            except BaseException as error:
                result = preserve_node_stop(node, error, holders[0] if holders else None, 'INVALID_SOURCE_ACCOUNT_OR_LEAF', case)
                result['interrupted'] = not isinstance(error, Exception)
                case = None
        result['choices'] = deepcopy(choices)
        if result['status'] == 'LOCAL_ALLOCATION_BRANCH_POINT':
            children = child_choices(choices, result['choice_request'])
            result['child_node_ids'] = [choices_id(child) for child in children]
            queue.extend(children)
        elif result['status'] == 'COMPLETE_RECONCILED_LEAF_UNSCORED':
            leaves[node_id] = case
        else:
            complete = False
        if result.get('persistence_errors'):
            complete = False
        try:
            write(node / 'result.json', result)
        except BaseException as error:
            persistence_errors.append({'file': node_id + '/result.json',
                'error_type': type(error).__name__, 'error': str(error)})
            complete = False
        nodes[node_id] = result
        try:
            old.write_json(folder / 'nodes.json', nodes)
        except BaseException as error:
            persistence_errors.append({'file': 'nodes.json', 'error_type': type(error).__name__, 'error': str(error)})
            complete = False
        if result.get('interrupted'):
            complete = False
            break
    return {'complete': complete and not queue and bool(leaves), 'nodes': nodes,
            'leaves': leaves, 'queued_unattempted': list(queue), 'persistence_errors': persistence_errors,
            'first_error': next(({'error_type': n['error_type'], 'error': n['error']} for n in nodes.values()
                                 if n['status'] == 'INVALID_SOURCE_ACCOUNT_OR_LEAF'), None),
            'interrupted': any(n.get('interrupted', False) for n in nodes.values())}


def require_closed_tree(tree):
    need(tree['complete'] is True and not tree['queued_unattempted'] and not tree.get('persistence_errors')
         and bool(tree['leaves']), 'complete persisted tree and nonempty leaves required')
    nodes = tree['nodes']
    root = choices_id({})
    need(root in nodes, 'original unselected root path required')
    pending, visited, leaves = [root], set(), set()
    while pending:
        node_id = pending.pop()
        need(node_id in nodes and node_id not in visited, 'missing, repeated or cyclic allocation node')
        visited.add(node_id)
        node = nodes[node_id]
        need(node_id == choices_id(node['choices']) and node['portfolio_returns_computed'] is False
             and not node.get('persistence_errors'), 'unaltered unscored node identity and complete persistence required')
        if node['status'] == 'LOCAL_ALLOCATION_BRANCH_POINT':
            expected = [choices_id(c) for c in child_choices(node['choices'], node['choice_request'])]
            need(node['child_node_ids'] == expected, 'all local uncertainty children must be included')
            pending.extend(expected)
        else:
            need(node['status'] == 'COMPLETE_RECONCILED_LEAF_UNSCORED', 'invalid account cannot be an admitted leaf')
            leaves.add(node_id)
    need(visited == set(nodes) and leaves == set(tree['leaves']), 'no omitted leaf or orphan allocation path allowed')


def score_complete_trees(trees, source_ok, *, scorer=old.annual_returns):
    need(set(trees) == {20, 40}, 'both cost trees required')
    if not source_ok or not all(tree['complete'] for tree in trees.values()):
        return None
    for tree in trees.values():
        require_closed_tree(tree)
    # Build every score before returning or mutating any node result.
    scored = {cost: {node_id: scorer(case) for node_id, case in tree['leaves'].items()}
              for cost, tree in trees.items()}
    result = {}
    keys = ('2024_return_pct', '2025_return_pct', '2026_through_2026-10-20_return_pct')
    for cost, leaves in scored.items():
        need(all(all(type(value[key]) in (int, float) and isfinite(value[key]) for key in keys)
                 and type(value['three_numeric_conditions_met_at_interim_cutoff']) is bool
                 for value in leaves.values()), 'finite complete annual payloads required')
        result[str(cost)] = {'leaf_results': leaves, 'complete_leaf_count': len(leaves),
            'annual_return_ranges_pct': {key: [min(v[key] for v in leaves.values()), max(v[key] for v in leaves.values())]
                                         for key in keys},
            'all_leaves_meet_three_interim_numeric_conditions': all(v['three_numeric_conditions_met_at_interim_cutoff'] for v in leaves.values())}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ('source-root', 'plan', 'expected-plan-sha256', 'output-dir'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--source-preflight-only', action='store_true')
    args = parser.parse_args(argv)
    base, repo, out = Path(args.source_root), Path(__file__).resolve().parents[1], Path(args.output_dir)
    need(not out.exists() and not out.is_symlink() and out.resolve() == (base / OUTPUT).resolve(), 'fixed fresh tree directory required')
    inputs = load_inputs(base, repo, args.plan, args.expected_plan_sha256)
    if args.source_preflight_only:
        print('strict failures/source/primary allocation proof bound; no new account tree or ROI')
        return 0
    out.mkdir(parents=True)
    trees, execution_error = {}, None
    try:
        write(out / 'input-before.json', inputs['known_hashes'])
        for cost in old.COSTS:
            folder = out / str(cost)
            folder.mkdir()
            trees[cost] = run_cost_tree(folder, inputs, cost, budget=inputs['plan']['node_budget_per_cost'])
            if trees[cost]['interrupted']:
                execution_error = trees[cost]['first_error']
                break
    except BaseException as error:
        execution_error = {'error_type': type(error).__name__, 'error': str(error)}
        try:
            write(out / 'execution-error.json', execution_error)
        except BaseException as persistence_error:
            execution_error['diagnostic_persistence_error'] = {'error_type': type(persistence_error).__name__, 'error': str(persistence_error)}
    finally:
        def reauthenticate():
            refreshed = load_inputs(base, repo, args.plan, args.expected_plan_sha256)
            need(refreshed['known_hashes'] == inputs['known_hashes'], 'tree input binding set changed')
        checked = strict.postcheck(inputs, reauthenticate)
        try:
            write(out / 'input-postcheck.json', checked)
        except BaseException as error:
            execution_error = execution_error or {'stage': 'POSTCHECK_PERSISTENCE', 'error_type': type(error).__name__, 'error': str(error)}
    scores, scoring_error = None, None
    if execution_error is None and set(trees) == {20, 40}:
        try:
            scores = score_complete_trees(trees, checked['completed'])
        except BaseException as error:
            scoring_error = {'error_type': type(error).__name__, 'error': str(error)}
    summary = {'status': 'COMPLETE_LOCAL_REGISTRY_ENVELOPE_DIAGNOSTIC' if scores else 'INCOMPLETE_LOCAL_REGISTRY_ENVELOPE_NO_ANNUAL_ROI',
        'plan_sha256': args.expected_plan_sha256, 'candidate': old.POLICY, 'window': [old.START, old.END],
        'results_by_extra_bps': scores, 'trees': {str(c): {'complete': t['complete'], 'nodes': len(t['nodes']),
            'leaf_count': len(t['leaves']), 'node_statuses': {n: v['status'] for n, v in t['nodes'].items()},
            'queued_unattempted': t['queued_unattempted'], 'first_error': t['first_error'],
            'persistence_errors': t['persistence_errors']} for c, t in trees.items()},
        'source_postcheck': checked, 'execution_error': execution_error, 'scoring_error': scoring_error,
        'annual_returns_computed_after_all_trees_complete': scores is not None,
        'investment_rule_changed': False, 'new_alpha_candidates': 0, 'source_queries': 0,
        'allocation_model': 'CONSERVATIVE_LOCAL_DISPLAY_PRECISION_ENVELOPE_NOT_ACTUAL_REGISTER',
        'all_local_candidates_globally_jointly_feasible_certified': False, 'probabilities_certified': False,
        'actual_registry_allocation_certified': False, 'strict_failed_accounts_relabelled_success': False,
        'full_October_2026_complete': False, 'sealed_2026_evidence_claimed': False,
        'historical_arrival_verified': False, 'queue_and_impact_calibrated': False,
        'actual_FIFO_tax_liability_verified': False, 'objective_achieved': False}
    write(out / 'summary.json', summary)
    return 0 if scores else 2


if __name__ == '__main__':
    raise SystemExit(main())
