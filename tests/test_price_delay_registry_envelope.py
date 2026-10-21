import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import run_price_delay_registry_envelope as runner


class CompleteAllocationTreeTests(unittest.TestCase):
    def request(self, event='event', component='capital', quantity=900):
        proof = {'contract': 'PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1',
            'issuer': 'SZ002831', 'event_id': event, 'record_date': '2024-06-03',
            'ex_date': '2024-06-04', 'component': component,
            'source_file': 'synthetic.pdf', 'source_sha256': 'a' * 64,
            'published_on': '2024-05-28', 'available_at': '2024-05-29T00:00:00+08:00',
            'actual_arrival_verified': False, 'eligible_count': 10000000,
            'declared_total_shares': 4019063, 'quoted_per10': '4.019063',
            'fraction_method': 'LARGEST_REMAINDER_DESC_RANDOM_TIES',
            'quoted_precision_bound': 'ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION'}
        envelope = runner.allocation_bounds(proof, quantity, as_of='2024-06-04T09:30:00+08:00')
        return {'event_id': event, 'instrument': proof['issuer'], 'component': component,
                'registered_quantity': quantity, 'candidates': envelope['possible_integer_shares'],
                'envelope': envelope}

    def node_runner(self, choices, folder):
        if not choices:
            return {'status': 'LOCAL_ALLOCATION_BRANCH_POINT', 'portfolio_returns_computed': False,
                    'choice_request': self.request()}, None
        return {'status': 'COMPLETE_RECONCILED_LEAF_UNSCORED', 'portfolio_returns_computed': False}, {'shares': choices['event']['capital']}

    def tree(self, root, budget=128, node_runner=None):
        root.mkdir()
        return runner.run_cost_tree(root, {}, 40, budget=budget, node_runner=node_runner or self.node_runner)

    def test_all_children_replayed_with_no_profit_based_pruning_or_choice_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree')
            self.assertTrue(tree['complete'])
            self.assertEqual(len(tree['nodes']), 3)
            self.assertEqual({case['shares'] for case in tree['leaves'].values()}, {361, 362})
            runner.require_closed_tree(tree)
            for node in tree['nodes'].values():
                self.assertIs(node['portfolio_returns_computed'], False)

    def test_nested_event_uncertainties_generate_all_four_paths(self):
        def nested(choices, folder):
            if not choices:
                return self.node_runner(choices, folder)
            if 'other-event' not in choices:
                return {'status': 'LOCAL_ALLOCATION_BRANCH_POINT', 'portfolio_returns_computed': False,
                        'choice_request': self.request('other-event', 'stock', 25)}, None
            return {'status': 'COMPLETE_RECONCILED_LEAF_UNSCORED', 'portfolio_returns_computed': False}, copy.deepcopy(choices)
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree', node_runner=nested)
            self.assertTrue(tree['complete'])
            self.assertEqual(len(tree['nodes']), 7)
            self.assertEqual(len(tree['leaves']), 4)
            runner.require_closed_tree(tree)

    def test_budget_and_invalid_leaf_block_every_profile_annual_scorer(self):
        for invalid in (False, True):
            def bad(choices, folder):
                if choices.get('event', {}).get('capital') == 362:
                    return {'status': 'INVALID_SOURCE_ACCOUNT_OR_LEAF', 'error_type': 'ValueError',
                            'error': 'unknown tax', 'portfolio_returns_computed': False}, None
                return self.node_runner(choices, folder)
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                tree = self.tree(Path(tmp) / 'tree', budget=128 if invalid else 2,
                                 node_runner=bad if invalid else self.node_runner)
                self.assertFalse(tree['complete'])
                scorer = Mock(side_effect=AssertionError('no ROI from incomplete envelope'))
                self.assertIsNone(runner.score_complete_trees({20: tree, 40: tree}, True, scorer=scorer))
                scorer.assert_not_called()

    def test_claimed_complete_tree_cannot_omit_one_branch_or_add_unreachable_leaf(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree')
            for orphan in (False, True):
                changed = copy.deepcopy(tree)
                if orphan:
                    choices = {'unreachable': {'capital': 1}}
                    key = runner.choices_id(choices)
                    changed['nodes'][key] = {'status': 'COMPLETE_RECONCILED_LEAF_UNSCORED',
                        'choices': choices, 'portfolio_returns_computed': False}
                    changed['leaves'][key] = {'shares': 1}
                else:
                    key = next(iter(changed['leaves']))
                    del changed['leaves'][key]
                    del changed['nodes'][key]
                scorer = Mock()
                with self.subTest(orphan=orphan), self.assertRaises(ValueError):
                    runner.score_complete_trees({20: changed, 40: tree}, True, scorer=scorer)
                scorer.assert_not_called()

    def test_coherent_candidate_and_child_deletion_cannot_shrink_primary_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree')
            root = tree['nodes'][runner.choices_id({})]
            root['choice_request']['candidates'] = [361]
            removed = root['child_node_ids'].pop()
            del tree['nodes'][removed]
            del tree['leaves'][removed]
            scorer = Mock()
            with self.assertRaises(ValueError):
                runner.score_complete_trees({20: tree, 40: tree}, True, scorer=scorer)
            scorer.assert_not_called()

    def test_first_input_write_failure_still_postchecks_and_preserves_original_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / runner.OUTPUT
            inputs = {'known_hashes': {}}
            checked = {'completed': True}
            real_write = runner.write
            def fail_first(path, value):
                if path.name == 'input-before.json':
                    raise OSError('first input write failed')
                real_write(path, value)
            with patch.object(runner, 'load_inputs', return_value=inputs), \
                 patch.object(runner.strict, 'postcheck', return_value=checked) as post, \
                 patch.object(runner, 'run_cost_tree') as accounts, \
                 patch.object(runner, 'write', side_effect=fail_first):
                self.assertEqual(runner.main(['--source-root', str(base), '--output-dir', str(out),
                    '--plan', 'unused.json', '--expected-plan-sha256', 'a' * 64]), 2)
            post.assert_called_once()
            accounts.assert_not_called()
            summary = runner.read(out / 'summary.json')
            self.assertEqual(summary['execution_error']['error'], 'first input write failed')
            self.assertFalse(summary['annual_returns_computed_after_all_trees_complete'])
            self.assertTrue(summary['source_postcheck']['completed'])

    def test_final_ranges_cover_every_leaf_even_when_floor_has_the_higher_return(self):
        def score(case):
            value = 12.0 if case['shares'] == 361 else 11.0
            return {'2024_return_pct': 1.0, '2025_return_pct': 2.0,
                    '2026_through_2026-10-20_return_pct': value,
                    'three_numeric_conditions_met_at_interim_cutoff': True}
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree')
            result = runner.score_complete_trees({20: tree, 40: tree}, True, scorer=score)
            self.assertEqual(result['40']['annual_return_ranges_pct']['2026_through_2026-10-20_return_pct'], [11., 12.])
            self.assertEqual(result['40']['complete_leaf_count'], 2)
            self.assertTrue(result['40']['all_leaves_meet_three_interim_numeric_conditions'])
            self.assertTrue(all(n['portfolio_returns_computed'] is False for n in tree['nodes'].values()))
            blocked = Mock()
            self.assertIsNone(runner.score_complete_trees({20: tree, 40: tree}, False, scorer=blocked))
            blocked.assert_not_called()

    def test_second_profile_score_failure_does_not_mutate_or_publish_first_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self.tree(Path(tmp) / 'tree')
            before = copy.deepcopy(tree)
            scorer = Mock(side_effect=[{}, {}, ValueError('second profile score invalid')])
            with self.assertRaises(ValueError):
                runner.score_complete_trees({20: tree, 40: tree}, True, scorer=scorer)
            self.assertEqual(tree, before)

    def test_failure_persistence_keeps_original_error_and_declares_incomplete_evidence(self):
        original = KeyboardInterrupt('original source interruption')
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'write', side_effect=OSError('diagnostic write failed')):
            result = runner.preserve_node_stop(Path(tmp), original, None, 'INVALID_SOURCE_ACCOUNT_OR_LEAF')
            self.assertEqual(result['error_type'], 'KeyboardInterrupt')
            self.assertTrue(result['persistence_errors'])
            self.assertIs(result['portfolio_returns_computed'], False)

    def test_plan_forbids_outcome_driven_budget_cost_target_or_account_changes(self):
        plan = copy.deepcopy(runner.PROFILE)
        plan['method_code_sha256'] = dict.fromkeys(runner.METHOD_FILES, 'a' * 64)
        plan['public_evidence_sha256'] = dict.fromkeys(runner.PUBLIC_FILES, 'b' * 64)
        runner.validate_plan(plan)
        for key, value in [('node_budget_per_cost', True), ('node_budget_per_cost', 129),
                           ('extra_cost_bps', [20]), ('investment_rule_changed', True),
                           ('risk_warning_buy_permission', True), ('all_nodes_and_costs_before_any_annual_ROI', False),
                           ('window', ['2023-12-29', '2026-10-21']), ('method_code_sha256', {})]:
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.validate_plan(changed)


if __name__ == '__main__':
    unittest.main()
