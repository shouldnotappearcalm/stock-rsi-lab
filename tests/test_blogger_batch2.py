import importlib.util,json,math,tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from stock_rsi.blogger_batch2 import evaluate,rsi10
from scripts.audit_blogger_batch2 import independent_rule
from scripts.prepare_blogger_batch2_data import parse,merge
from scripts.run_blogger_batch2 import selected,preserved

ROOT=Path(__file__).resolve().parents[1]

class BloggerBatch2Tests(unittest.TestCase):
    def test_inclusive_close_channel_not_strict_high_low_channel(self):
        p=[100.]*19+[101.];self.assertEqual(evaluate('bigquant20',p,False)['action'],'BUY')
        p=[101.]+[100.]*19;self.assertEqual(evaluate('bigquant20',p,False)['action'],'HOLD')
        p=[100.]*20;self.assertEqual(evaluate('bigquant20',p,False)['action'],'BUY');self.assertEqual(evaluate('bigquant20',p,True,1)['action'],'SELL')

    def test_wilder_rsi_seed_and_recursion_have_independent_witness(self):
        p=[100.+i for i in range(11)]+[100.,102.,98.,101.]
        self.assertEqual(rsi10(p)[0],100.)
        _,d=independent_rule('rayner10',[80.]*200+p,False,0,False)
        self.assertAlmostEqual(rsi10([80.]*200+p)[-1],d['rsi10'],places=10)
        self.assertEqual(rsi10([100.]*12),[0.,0.])

    def test_mean_reversion_requires_both_uptrend_and_oversold(self):
        p=[100.]*200+[200.]+[198.-2*i for i in range(30)]
        o=evaluate('rayner10',p,False);self.assertEqual(o['action'],'BUY');self.assertLess(o['details']['rsi10'],30)
        self.assertEqual(evaluate('rayner10',[200.]*200+[198.-2*i for i in range(30)],False)['action'],'HOLD')
        with patch('stock_rsi.blogger_batch2.rsi10',return_value=[29.,30.]):self.assertEqual(evaluate('rayner10',[100.]*200+[110.],False)['action'],'HOLD')

    def test_tenth_actual_holding_close_triggers_next_open_exit(self):
        p=[100.]*200
        self.assertEqual(evaluate('rayner10',p,True,9)['action'],'HOLD')
        self.assertEqual(evaluate('rayner10',p,True,10)['action'],'SELL')

    def test_unfilled_exit_remains_latched_until_actually_flat(self):
        self.assertEqual(evaluate('rayner10',[100.]*200,True,2,True)['action'],'SELL')
        with patch('stock_rsi.blogger_batch2.rsi10',return_value=[40.,40.]):self.assertEqual(evaluate('rayner10',[100.]*200,True,1)['action'],'HOLD')
        with patch('stock_rsi.blogger_batch2.rsi10',return_value=[40.,40.01]):self.assertEqual(evaluate('rayner10',[100.]*200,True,1)['action'],'SELL')

    def test_missing_nonfinite_short_or_malformed_state_fails(self):
        for p in ([100.]*19,[100.]*19+[math.nan],[100.]*19+[0]):
            with self.assertRaises(ValueError):evaluate('bigquant20',p,False)
        with self.assertRaises(ValueError):evaluate('rayner10',[100.]*199,False)
        with self.assertRaises(ValueError):evaluate('rayner10',[100.]*200,True,-1)

    def test_warmup_parse_rejects_future_and_wrong_adjustment_field(self):
        b={'code':0,'data':{'sh510050':{'day':[['2023-07-31','10','10','10','10','100']]}}}
        self.assertEqual(len(parse(b,'raw',['2023-07-31'])['bars']),1)
        with self.assertRaises(ValueError):parse(b,'hfq',['2023-07-31'])
        b['data']['sh510050']['day'][0][0]='2026-01-05'
        with self.assertRaises(ValueError):parse(b,'raw',['2026-01-05'])

    def test_warmup_cannot_rewrite_original_prices(self):
        earlier={'bars':[{'date':'2023-06-30','close':'9.000'},{'date':'2023-07-03','close':'10.0'}]};original={'bars':[{'date':'2023-07-03','close':'10.000'}]}
        merged,n=merge(earlier,original,['2023-06-30','2023-07-03']);self.assertEqual(n,1);self.assertEqual(merged['bars'][-1],original['bars'][0])
        with self.assertRaises(ValueError):merge({'bars':[earlier['bars'][0],{'date':'2023-07-03','close':'10.001'}]},original,['2023-06-30','2023-07-03'])

    def test_all_five_prior_strategies_remain_hash_identical(self):
        old=preserved(ROOT);self.assertGreaterEqual(len(old),171)
        self.assertEqual(selected('development',None),['bigquant20','rayner10'])

    def test_forward_selection_is_exactly_all_profitable_development_rules(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);m={'2024_return_pct':1.,'2025_return_pct':1.,'unverified_held_marks':0,'average_exposure_pct':0.1}
            for future in (-100.,1000.):
                term={'complete':True,'all_inputs_unchanged':True,'phase':'development','passed_two_year_screen':['bigquant20'],
                      'results':{'40/bigquant20':{**m,'2026_return_pct':future},'40/rayner10':{**m,'2025_return_pct':-1.,'2026_return_pct':-future}}}
                (p/'terminal.json').write_text(json.dumps(term));self.assertEqual(selected('forward',p),['bigquant20'])
            term['passed_two_year_screen']=['bigquant20','rayner10'];(p/'terminal.json').write_text(json.dumps(term))
            with self.assertRaises(ValueError):selected('forward',p)


@unittest.skipUnless(importlib.util.find_spec('qlib'),'optional Qlib unavailable')
class Batch2ClockTests(unittest.TestCase):
    def test_execution_prices_and_future_values_are_not_decision_inputs(self):
        import pandas as pd
        from stock_rsi.blogger_batch2_qlib import Batch2PriorCloseStrategy
        # Explicit actual exchange sessions, not a weekday-generated calendar.
        dates='2023-12-04 2023-12-05 2023-12-06 2023-12-07 2023-12-08 2023-12-11 2023-12-12 2023-12-13 2023-12-14 2023-12-15 2023-12-18 2023-12-19 2023-12-20 2023-12-21 2023-12-22 2023-12-25 2023-12-26 2023-12-27 2023-12-28 2023-12-29 2024-01-02'.split()
        days=tuple(map(date.fromisoformat,dates))
        class Snapshot:
            calendar=days
            future=100.
            def value(self,symbol,field,d):
                if date.fromisoformat(d)>days[-2] or field=='open':raise AssertionError('future or execution open accessed')
                if field=='close':return 102. if d==dates[-2] else 100.
                return 1.
        snap=Snapshot();p=SimpleNamespace(get_stock_amount_dict=lambda:{},calculate_value=lambda:100000.,get_cash=lambda **kw:100000.)
        strategy=Batch2PriorCloseStrategy(config={'id':'bigquant20'},snapshot=snap)
        strategy.common_infra=SimpleNamespace(get=lambda key:SimpleNamespace(current_position=p))
        strategy.level_infra=SimpleNamespace(get=lambda key:SimpleNamespace(get_step_time=lambda:(pd.Timestamp(days[-1]),pd.Timestamp(days[-1]))))
        a=[(o.stock_id,o.amount) for o in strategy.generate_trade_decision().get_decision()];snap.future=99999.
        b=[(o.stock_id,o.amount) for o in strategy.generate_trade_decision().get_decision()]
        self.assertEqual(a,b);self.assertEqual(a,[('SH510050',900.)]);self.assertEqual(strategy.intents[0]['holding_sessions'],0)

if __name__=='__main__':unittest.main()
