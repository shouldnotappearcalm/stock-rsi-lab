from pathlib import Path
import unittest

from scripts.prepare_reversal_frozen_2026_targets import assert_cap_only_change


class ReversalTargetExtensionTests(unittest.TestCase):
    def test_date_permission_change_cannot_hide_changes_to_guard_or_factor(self):
        root=Path(__file__).resolve().parents[1]
        old=(root/'experiments/qlib/audit_sources/2026-10-17-return-families-development-source.py').read_text()
        new=(root/'src/stock_rsi/return_families.py').read_text()
        assert_cap_only_change(old,new)
        for altered in (new.replace('if start> end','if True or start> end'),new.replace('monthly[-13]','monthly[-12]')):
            with self.assertRaises(ValueError):assert_cap_only_change(old,altered)
