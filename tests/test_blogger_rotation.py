from datetime import date,timedelta
import importlib.util
import json,math
from pathlib import Path
from types import SimpleNamespace
import unittest

from stock_rsi.blogger_rotation import evaluate,development_pass
from scripts.prepare_blogger_etf_data import block_flags
from scripts.prepare_blogger_tencent_data import parse

ROOT=Path(__file__).resolve().parents[1]

def cfg(name):return json.loads((ROOT/'skills'/('a-share-blogger-'+name.replace('_','-'))/'skill.json').read_text())


class BloggerRuleTests(unittest.TestCase):
    def test_original20_sessions_and_supplement19_21_mean_are_distinct(self):
        c=cfg('fengji20');h={'SH518880':[100.]*20+[110.],'SZ159915':[100.]*21}
        self.assertEqual(evaluate(c,h,{})['leader'],'SH518880')
        c=cfg('fengji_mean');h={'SH518880':[1.,4.,4.]+[3.5]*19,'SZ159915':[1.]*22}
        self.assertEqual(evaluate(c,h,{})['leader'],'SH518880')
        self.assertEqual(evaluate(c,h,{})['scores_exact_ratio']['SH518880'],['1','6'])

    def test_nonpositive_returns_go_to_cash_without_inventing_bond_return(self):
        c=cfg('fengji20');h={s:[100.]*20+[99.] for s in c['signal_symbols']}
        self.assertIsNone(evaluate(c,h,{'SH518880':100})['leader'])
        h={s:[100.]*21 for s in c['signal_symbols']};self.assertIsNone(evaluate(c,h,{})['leader'])

    def test_positive_tie_retains_held_fund_otherwise_uses_declared_order(self):
        c=cfg('fengji20');h={s:[100.]*20+[101.] for s in c['signal_symbols']}
        self.assertEqual(evaluate(c,h,{'SZ159915':100})['leader'],'SZ159915')
        self.assertEqual(evaluate(c,h,{})['leader'],'SH518880')

    def test_plus2047_uses20_observations_and_strict_one_percentage_point(self):
        c=cfg('plus2047');h={'SH000016':[100.]*19+[102.],'SH000300':[100.]*19+[101.],'SH000905':[100.]*20}
        self.assertIsNone(evaluate(c,h,{})['leader'])
        h['SH000016'][-1]=102.1;self.assertEqual(evaluate(c,h,{})['leader'],'SH510050')

    def test_plus_does_not_rotate_out_of_a_positive_held_fund(self):
        c=cfg('plus2047');h={'SH000016':[100.]*19+[101.],'SH000300':[100.]*19+[130.],'SH000905':[100.]*20}
        self.assertEqual(evaluate(c,h,{'SH510050':100})['leader'],'SH510050')
        h['SH000016'][-1]=100.;self.assertIsNone(evaluate(c,h,{'SH510050':100})['leader'])

    def test_missing_future_or_multiple_held_inventory_fails_closed(self):
        c=cfg('fengji20');h={s:[100.]*21 for s in c['signal_symbols']}
        with self.assertRaises(ValueError):evaluate(c,{**h,'SH518880':[100.]*20},{})
        with self.assertRaises(ValueError):evaluate(c,{**h,'SH518880':[100.]*20+[math.nan]},{})
        with self.assertRaises(ValueError):evaluate(c,h,{'SH518880':100,'SZ159915':100})

    def test_profitability_screen_has_no_average_exposure_veto(self):
        m={'2024_return_pct':1.,'2025_return_pct':1.,'average_exposure_pct':1.,'unverified_held_marks':0}
        self.assertTrue(development_pass(m));self.assertFalse(development_pass({**m,'2025_return_pct':0}))

    def test_reference_bands_distinguish20_percent_chinext(self):
        row={'open':'11.500','provider_implied_preclose':'10.000'}
        self.assertEqual(block_flags(row,'SZ159915'),(0,0))
        with self.assertRaises(ValueError):block_flags(row,'SH510050')
        self.assertEqual(block_flags({'open':'11.000','provider_implied_preclose':'10.000'},'SH518880'),(1,0))

    def test_tencent_adjustment_mode_never_falls_back_to_raw(self):
        b={'code':0,'data':{'sh518880':{'day':[['2025-12-31','10','10','10','10','100']]}}}
        with self.assertRaisesRegex(ValueError,'adjustment'):parse(b,'SH518880','hfq',['2025-12-31'])
        self.assertEqual(len(parse(b,'SH518880','raw',['2025-12-31'])['bars']),1)
        b['data']['sh518880']['day'][0][0]='2026-01-05'
        with self.assertRaises(ValueError):parse(b,'SH518880','raw',['2026-01-05'])

    def test_separate_source_audit_reconstructs_ex_right_reference(self):
        from decimal import Decimal
        from scripts.audit_blogger_pre2026 import derived_fields
        raw={'open':'9.000','close':'9.000','high':'9.000','low':'9.000','volume_provider_units':'100'}
        adjusted={'close':'10.000'}
        fields,norm=derived_fields('SH510050',raw,adjusted,Decimal(1),Decimal(10))
        self.assertEqual(norm,Decimal(1));self.assertEqual(fields['change'],0)
        self.assertEqual(fields['buyblock'],0);self.assertEqual(fields['sellblock'],0)
        bad={**raw,'open':'12.000'}
        with self.assertRaisesRegex(ValueError,'reference'):derived_fields('SH510050',bad,adjusted,Decimal(1),Decimal(10))

    def test_sources_have_original_pre2024_time_and_document_nonrunnable_sources(self):
        s=json.loads((ROOT/'experiments/blogger-strategies/sources.json').read_text())
        self.assertEqual(s['candidate_budget'],3)
        self.assertEqual(s['sources'][0]['published_at'],'2016-04-17T13:22:00+08:00')
        self.assertLess(s['sources'][1]['snapshot_at'],'2024-01-01')
        self.assertTrue(any(x['admission']=='NOT_RUNNABLE_YET' for x in s['sources']))


@unittest.skipUnless(importlib.util.find_spec('qlib'),'optional Qlib unavailable')
class BloggerExecutionTests(unittest.TestCase):
    def test_rotation_requires_observed_exit_cash_and_never_tops_up_a_hold(self):
        from stock_rsi.blogger_qlib_strategy import plan
        p=plan('B',100000,5000,{'A':9500},{'A':10,'B':10},{'A':1,'B':1})
        self.assertEqual(p,[{'instrument':'A','side':'SELL','normalized_units':9500}])
        self.assertEqual(plan('B',100000,100000,{}, {'B':10},{'B':1})[0]['normalized_units'],9500)
        self.assertEqual(plan('B',100000,20000,{'B':8000},{'B':10},{'B':1}),[])

    def test_future_market_changes_cannot_change_decision(self):
        import pandas as pd
        from qlib.backtest.position import Position
        from stock_rsi.blogger_qlib_strategy import BloggerPriorCloseStrategy
        c=cfg('fengji20');days=tuple(date(2023,11,1)+timedelta(days=i) for i in range(22))
        class Snapshot:
            calendar=days
            future=100
            def value(self,symbol,field,day):
                d=date.fromisoformat(day)
                if d>days[-2] or field=='open':raise AssertionError('future or execution market queried')
                if field=='close':return 110. if symbol=='SH518880' and d==days[-2] else 100.
                return 1.
        snap=Snapshot();strategy=BloggerPriorCloseStrategy(config=c,snapshot=snap)
        strategy.common_infra=SimpleNamespace(get=lambda key:SimpleNamespace(current_position=Position(cash=100000)))
        strategy.level_infra=SimpleNamespace(get=lambda key:SimpleNamespace(get_step_time=lambda:(pd.Timestamp(days[-1]),pd.Timestamp(days[-1]))))
        first=[(o.stock_id,o.amount) for o in strategy.generate_trade_decision().get_decision()]
        snap.future=99999.;second=[(o.stock_id,o.amount) for o in strategy.generate_trade_decision().get_decision()]
        self.assertEqual(first,second);self.assertEqual(first,[('SH518880',800.)])


if __name__=='__main__':unittest.main()
