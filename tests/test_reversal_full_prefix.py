import json
from pathlib import Path
import tempfile
import unittest
from decimal import Decimal

try:
    from scripts.run_reversal_frozen_2026 import assert_development_control,combined_2025_2026
except ImportError:assert_development_control=combined_2025_2026=None


class ReversalFullPrefixTests(unittest.TestCase):
    def test_2025_to_2026_slice_uses_2024_year_end_not_2025_year_end(self):
        self.assertIsNotNone(combined_2025_2026,'combined slice missing')
        rows=[{'day':d,'equity':Decimal(v),'exposure':Decimal('.95')} for d,v in
              [('2024-12-31','100'),('2025-02-03','90'),('2025-12-31','110'),
               ('2026-03-02','100'),('2026-10-16','132')]]
        result=combined_2025_2026({'days':rows})
        self.assertAlmostEqual(result['net_compound_return_pct'],32)
        self.assertAlmostEqual(result['max_drawdown_pct'],-10)
        self.assertEqual(result['sessions'],4)

    def test_next_year_parent_is_not_misclassified_by_its_prior_close_submission(self):
        self.assertIsNotNone(assert_development_control,'full replay runner missing')
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'old';full=Path(tmp)/'full';old.mkdir();full.mkdir()
            for folder in (old,full):
                (folder/'daily.csv').write_text('day,equity\n2025-12-31,100\n')
                for file in ('orders','fills','intents','parent_instructions','corporate_ledger'):
                    (folder/(file+'.json')).write_text('[]')
                (folder/'ownership.json').write_text('{"2025-12-31":{}}')
            (full/'daily.csv').write_text('day,equity\n2025-12-31,100\n2026-01-05,101\n')
            (full/'parent_instructions.json').write_text(json.dumps([{'submitted_at':'2025-12-31T07:05:00+00:00',
                'eligible_at':'2026-01-05T01:30:00+00:00'}]))
            (full/'intents.json').write_text('[{"execution_session":"2026-01-05"}]')
            event={'day':'2025-12-30','kind':'EX_DATE_ENTITLEMENT','event_id':'new',
                   'registered_quantity':0,'cash_gross':'0','stress_tax_reserve':'0','capital_shares':0}
            (full/'corporate_ledger.json').write_text(json.dumps([event]))
            assert_development_control(full,old,set())
            event['registered_quantity']=1
            (full/'corporate_ledger.json').write_text(json.dumps([event]))
            with self.assertRaises(RuntimeError):assert_development_control(full,old,set())
