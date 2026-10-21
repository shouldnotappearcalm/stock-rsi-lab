import copy
import tempfile
import unittest
from pathlib import Path

from scripts import prepare_price_delay_horizon_formations as runner


class HorizonFormationContractTests(unittest.TestCase):
    def test_requires_frozen_unchanged_policy_and_all48_financial_anchors(self):
        p = copy.deepcopy(runner.PROFILE)
        for field, names in runner.BINDINGS:
            p[field] = dict.fromkeys(names, 'a' * 64)
        financial = dict.fromkeys(runner.FINANCIAL_FILES, 'b' * 64)
        p['immutable_financial_sha256'] = dict(financial)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            out = base / runner.OUTPUT
            runner.validate_contract(p, base, out, financial)
            for key, value in [('candidate', 'low_delay_control'), ('candidate_budget', True),
                               ('investment_rule_changes_permitted', True),
                               ('portfolio_returns_to_compute', True),
                               ('window', ['2024-01-02', '2026-10-21']),
                               ('immutable_financial_sha256', {}), ('method_code_sha256', {}),
                               ('public_evidence_sha256', {}), ('local_source_sha256', {})]:
                changed = copy.deepcopy(p)
                changed[key] = value
                with self.subTest(field=key), self.assertRaises(ValueError):
                    runner.validate_contract(changed, base, out, financial)
            with self.assertRaises(ValueError):
                runner.validate_contract(p, base, base / 'wrong', financial)

    def test_new_formations_cannot_replace_old_targets_or_old_regression_receipts(self):
        old = {'price_delay_d1': {'2024-01-02': {'weights': {'SZ000001': .95}}}}
        full = copy.deepcopy(old)
        full['price_delay_d1']['2026-01-05'] = {'weights': {'SZ000002': .95}}
        receipt = [{'execution_session': '2024-01-02', 'fit': 1}]
        extended = receipt + [{'execution_session': '2026-01-05', 'fit': 2}]
        runner.require_original_prefix(full, extended, old, receipt)
        changed = copy.deepcopy(full)
        changed['price_delay_d1']['2024-01-02']['weights']['SZ000001'] = .94
        with self.assertRaises(ValueError):
            runner.require_original_prefix(changed, extended, old, receipt)
        with self.assertRaises(ValueError):
            runner.require_original_prefix(full, [{'execution_session': '2024-01-02', 'fit': 3}] + extended[1:], old, receipt)


if __name__ == '__main__':
    unittest.main()
