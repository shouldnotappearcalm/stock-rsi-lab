import importlib.util,json,math,tempfile,unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from stock_rsi.blogger_batch4 import evaluate,rsi2
from scripts.audit_blogger_batch4 import independent_rule
from scripts.run_blogger_batch4 import selected,preserved

ROOT=Path(__file__).resolve().parents[1]

class Batch4Tests(unittest.TestCase):
    def test_alvarez_needs_two_strict_down_closes_but_no_trend_filter(self):
        p=[100.]*200+[99.,98.]
        self.assertEqual(evaluate('alvarez2',p,False)['action'],'BUY')
        self.assertEqual(evaluate('alvarez2',[100.]*200+[99.,99.],False)['action'],'HOLD')
        self.assertEqual(evaluate('alvarez2',[100.]*201,False)['action'],'HOLD')

    def test_rsi_strict_thresholds_and_exit_latch(self):
        p=[100.]*200+[99.,98.]
        with patch('stock_rsi.blogger_batch4.rsi2',return_value=5.):self.assertEqual(evaluate('alvarez2',p,False)['action'],'HOLD')
        with patch('stock_rsi.blogger_batch4.rsi2',return_value=50.):self.assertEqual(evaluate('alvarez2',p,True)['action'],'HOLD')
        with patch('stock_rsi.blogger_batch4.rsi2',return_value=50.01):self.assertEqual(evaluate('alvarez2',p,True)['action'],'SELL')
        self.assertEqual(evaluate('alvarez2',p,True,exit_latched=True)['action'],'SELL')

    def test_wilder_recursion_independent_witness(self):
        p=[100.]*200+[110.,108.,107.,111.,107.]
        _,d=independent_rule('alvarez2',p,False,100.,None,False)
        self.assertAlmostEqual(rsi2(p),d['rsi2'],places=11)
        self.assertEqual(rsi2([100.]*5),0.)

    def test_marwood_entry_both_means_and_equality(self):
        p=[100.]*200+[120.]*9+[110.]
        self.assertEqual(evaluate('marwood10',p,False,low=109.)['action'],'BUY')
        self.assertEqual(evaluate('marwood10',[100.]*200,False,low=100.)['action'],'HOLD')
        self.assertEqual(evaluate('marwood10',[120.]*200+[100.],False,low=99.)['action'],'HOLD')

    def test_stop_uses_completed_low_and_actual_filled_open_not_close(self):
        p=[100.]*200
        self.assertEqual(evaluate('marwood10',p,True,low=90.,entry_price=100.)['action'],'SELL')
        self.assertEqual(evaluate('marwood10',p,True,low=90.01,entry_price=100.)['action'],'HOLD')
        self.assertEqual(evaluate('marwood10',p,True,low=90.01,entry_price=101.)['action'],'SELL')
        self.assertEqual(evaluate('marwood10',p,True,low=99.,entry_price=100.,exit_latched=True)['action'],'SELL')
        with self.assertRaises(ValueError):evaluate('marwood10',p,True,low=99.)

    def test_invalid_data_fails_closed(self):
        for p in ([100.]*199,[100.]*200+[math.nan],[100.]*200+[0.]):
            with self.assertRaises(ValueError):evaluate('alvarez2',p,False)
        with self.assertRaises(ValueError):evaluate('marwood10',[100.]*200,False,low=101.)
        with self.assertRaises(ValueError):evaluate('invalid',[100.]*200,False)

    def test_prior_nine_skills_and_evidence_unchanged(self):self.assertEqual(len(preserved(ROOT)),306)

    def test_forward_gate_uses_both_development_years_and_no_exposure_veto(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);m={'2024_return_pct':1.,'2025_return_pct':1.,'unverified_held_marks':0,'average_exposure_pct':.1}
            for v in (-100.,100.):
                x={'complete':True,'phase':'development','all_inputs_unchanged':True,'passed_two_year_screen':['alvarez2'],'results':{'40/alvarez2':{**m,'2026_return_pct':v},'40/marwood10':{**m,'2025_return_pct':-1.,'2026_return_pct':-v}}}
                (p/'terminal.json').write_text(json.dumps(x));self.assertEqual(selected('forward',p),['alvarez2'])
            x['passed_two_year_screen']=['alvarez2','marwood10'];(p/'terminal.json').write_text(json.dumps(x))
            with self.assertRaises(ValueError):selected('forward',p)

@unittest.skipUnless(importlib.util.find_spec('qlib'),'optional Qlib unavailable')
class Batch4ClockTests(unittest.TestCase):
    def setup_strategy(self):
        import pandas as pd
        from stock_rsi.blogger_batch4_qlib import Batch4Strategy
        # Only explicit historical exchange dates; future fixture price calls fail.
        import csv
        sessions=[r['session'] for r in csv.DictReader((ROOT/'experiments/blogger-batch3/development-results/40/faber10/days.csv').read_text().splitlines())]
        days=tuple(map(date.fromisoformat,['2022-12-01']+sessions[:201]))
        class Snapshot:
            calendar=days
            def value(self,symbol,field,d):
                if date.fromisoformat(d)>days[-2] or field=='open':raise AssertionError('future or unobserved fill price read')
                if field=='close':return 98. if d==days[-2].isoformat() else 99. if d==days[-3].isoformat() else 100.
                if field=='low':return 97.
                return 1.
        state={'owned':{}}
        position=SimpleNamespace(get_stock_amount_dict=lambda:state['owned'],calculate_value=lambda:100000.,get_cash=lambda **kw:100000.)
        strategy=Batch4Strategy(config={'id':'alvarez2'},snapshot=Snapshot())
        strategy.common_infra=SimpleNamespace(get=lambda key:SimpleNamespace(current_position=position))
        strategy.level_infra=SimpleNamespace(get=lambda key:SimpleNamespace(get_step_time=lambda:(pd.Timestamp(days[-1]),pd.Timestamp(days[-1]))))
        return strategy,state

    def test_decision_never_reads_execution_open(self):
        strategy,state=self.setup_strategy();orders=strategy.generate_trade_decision().get_decision()
        self.assertEqual(len(orders),1);self.assertEqual(strategy.intents[-1]['actual_entry_price'],None)

    def test_unexplained_starting_inventory_cannot_be_assumed_fill(self):
        strategy,state=self.setup_strategy();state['owned']={'SH510050':100.}
        with self.assertRaises((ValueError,AssertionError)):strategy.generate_trade_decision()

if __name__=='__main__':unittest.main()
