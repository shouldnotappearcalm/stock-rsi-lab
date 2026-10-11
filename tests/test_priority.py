import json
import tempfile
import unittest
from pathlib import Path


class PriorityTests(unittest.TestCase):
    def capture(self,root,adjust='raw'):
        (root/'calendar.stdout').write_text(json.dumps([{'date':'2025-01-02'},{'date':'2025-01-03'}]))
        rows=[{'time':'2025-01-02','open':30,'close':30,'high':31,'low':29,'volume':100},
              {'time':'2025-01-03','open':10,'close':10,'high':11,'low':9,'volume':100}]
        (root/'000001.stdout').write_text(json.dumps({'meta':{'source':'literal','adjust_actual':adjust},'data':rows}))

    def test_import_marks_assumptions_preserves_jump_and_rejects_adjusted_prices(self):
        from stock_rsi.priority import build_dataset
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.capture(root)
            data=build_dataset(root,['000001'])
            self.assertEqual(data['evidence_level'],'REAL_PRICE_ENGINEERING_ONLY')
            self.assertEqual(data['records'][1]['payload']['close'],10)
            self.assertEqual(len(data['provenance']['raw_discontinuities']),1)
            self.assertTrue(data['provenance']['assumptions'])
            self.capture(root,'qfq')
            with self.assertRaises(ValueError):build_dataset(root,['000001'])

    def test_daily_valuation_uses_fills_costs_and_flags_held_discontinuity(self):
        from stock_rsi.priority import build_dataset,summarize
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.capture(root);data=build_dataset(root,['000001'])
            report={'manifest':{'config':{'start':'2025-01-02T00:00:00+08:00','end':'2025-01-03T17:00:00+08:00','initial_cash':'10000'}},
                    'fills':[{'execution_at':'2025-01-02T01:30:00+00:00','security_id':'000001','action':'BUY','quantity':100,'price':'30','cost':'6','cash_after':'6994'}],
                    'orders':[],'account':{'equity':'7994','cash':'6994','positions':{}},'errors':[]}
            result=summarize(data,report)
            self.assertEqual(result['equity_curve'][0]['equity'],'9994')
            self.assertEqual(result['equity_curve'][-1]['equity'],'7994')
            self.assertEqual(result['metrics']['fees'],'6')
            self.assertEqual(result['discontinuity_exposure'][0]['held_before_open'],100)
            self.assertEqual(result['result_quality'],'KNOWN_DISCONTINUITY_EXPOSURE')
