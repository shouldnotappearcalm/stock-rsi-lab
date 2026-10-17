import unittest
from pathlib import Path
from scripts.prepare_szse_value_frozen_2026_targets import assert_cap_only_change
from stock_rsi.exchange_value_extended import build_targets

class ExtensionBoundaryTests(unittest.TestCase):
    def test_only_date_permission_can_change(self):
        root=Path(__file__).resolve().parents[1]
        old=(root/'src/stock_rsi/exchange_value.py').read_text()
        extended=(root/'src/stock_rsi/exchange_value_extended.py').read_text()
        assert_cap_only_change(old,extended)
        for edited in (extended.replace('.95/len(selected)','.99/len(selected)'),
                       extended.replace('highest_decile(scores)','highest_decile({})')):
            with self.assertRaises(ValueError):assert_cap_only_change(old,edited)

    def test_extension_is_denied_without_explicit_permission(self):
        with self.assertRaisesRegex(ValueError,'explicit date permission'):
            build_targets(None,None,None,end='2026-10-13')
