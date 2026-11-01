from datetime import date
import importlib.util,json,math,tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from stock_rsi.blogger_batch3 import month_ends,monthly_regime,annual_targets,annual_orders,lot_floor,STOCK,BOND
from scripts.prepare_blogger_batch3_data import parse,bond_values
from scripts.run_blogger_batch3 import selected,preserved

ROOT=Path(__file__).resolve().parents[1]
MONTHS='2023-01-31 2023-02-28 2023-03-31 2023-04-28 2023-05-31 2023-06-30 2023-07-31 2023-08-31 2023-09-28 2023-10-31 2023-11-30 2023-12-29'.split()

class Batch3RulesTests(unittest.TestCase):
    def test_month_sampling_uses_actual_month_ends_including_latest(self):
        history=[[d,float(90+i)] for i,d in enumerate(MONTHS)];result=month_ends(history)
        self.assertEqual(len(result),10);self.assertEqual(result[0][0],'2023-03-31');self.assertEqual(result[-1][0],'2023-12-29')
        regime,detail=monthly_regime(result,False);self.assertTrue(regime);self.assertEqual(detail['ma10'],96.5)

    def test_same_month_daily_prices_are_not_ten_months(self):
        with self.assertRaises(ValueError):month_ends([['2023-12-'+str(i).zfill(2),100.] for i in range(1,22)])
        with self.assertRaises(ValueError):month_ends([[MONTHS[0],100.],[MONTHS[0],101.]])

    def test_equal_monthly_price_retains_state_and_initializes_flat(self):
        h=[[d,100.] for d in MONTHS[-10:]]
        self.assertFalse(monthly_regime(h,None)[0]);self.assertTrue(monthly_regime(h,True)[0]);self.assertFalse(monthly_regime(h,False)[0])
        self.assertFalse(monthly_regime(h[:-1]+[[h[-1][0],99.]],True)[0])

    def test_actual_prior_nav_forms_equal_budgeted_targets(self):
        targets=annual_targets(100000.,{STOCK:10.,BOND:100.},{STOCK:1.,BOND:1.})
        self.assertEqual(targets,{STOCK:4700.,BOND:400.})
        self.assertLessEqual(targets[STOCK]*10+targets[BOND]*100,95000)

    def test_sells_must_finish_before_any_paired_buys(self):
        target={STOCK:4700.,BOND:400.};prices={STOCK:10.,BOND:100.};factors={STOCK:1.,BOND:1.}
        orders=annual_orders(target,150000.,50000.,{STOCK:6000.,BOND:300.},prices,factors,40)
        self.assertEqual(orders,[{'instrument':STOCK,'side':'SELL','normalized_units':1300.}])
        orders=annual_orders(target,107000.,20000.,{STOCK:4700.,BOND:300.},prices,factors,40)
        self.assertEqual(orders,[{'instrument':BOND,'side':'BUY','normalized_units':100.}])

    def test_multiple_buys_reserve_fees_and_never_overcommit_observed_cash(self):
        orders=annual_orders({STOCK:5000.,BOND:500.},100000.,100000.,{}, {STOCK:10.,BOND:100.},{STOCK:1.,BOND:1.},40)
        total=sum(o['normalized_units']*({STOCK:10.,BOND:100.}[o['instrument']]) for o in orders)
        fees=sum(max(5,o['normalized_units']*({STOCK:10.,BOND:100.}[o['instrument']])*.0045) for o in orders)
        self.assertLessEqual(total+fees,95000.)
        self.assertTrue(all(o['normalized_units']%100==0 for o in orders))

    def test_sub_lot_residuals_do_not_generate_rebalance_churn(self):
        self.assertEqual(annual_orders({STOCK:1000.,BOND:100.},20000.,5000.,{STOCK:995.,BOND:100.},{STOCK:10.,BOND:100.},{STOCK:1.,BOND:1.},40),[])
        self.assertLessEqual(lot_floor(100.00000000000001,.99999999),100.00000000000001)

    def test_bad_actual_inventory_or_factor_fails_closed(self):
        with self.assertRaises(ValueError):annual_targets(100000.,{STOCK:10.,BOND:100.},{STOCK:0.,BOND:1.})
        with self.assertRaises(ValueError):annual_orders({STOCK:100.,BOND:100.},100000.,10000.,{'OTHER':1.},{STOCK:10.,BOND:100.},{STOCK:1.,BOND:1.},40)
        with self.assertRaises(ValueError):lot_floor(math.nan,1.)

    def test_zero_trade_activity_keeps_mark_but_blocks_both_directions(self):
        b={'code':0,'data':{'sh511010':{'day':[['2023-07-03','0','100','0','0','0']]}}}
        packet=parse(b,'raw',['2023-07-03']);fields=bond_values(packet['bars'],packet['bars'])
        self.assertEqual(fields['close'],[1.]);self.assertEqual(fields['open'],[0.]);self.assertEqual(fields['buyblock'],[1]);self.assertEqual(fields['sellblock'],[1])
        with self.assertRaises(ValueError):parse(b,'hfq',['2023-07-03'])

    def test_selection_uses_only_development_profits_without_exposure_veto(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);m={'2024_return_pct':1.,'2025_return_pct':1.,'average_exposure_pct':1.,'unverified_held_marks':0}
            for future in (-100.,1000.):
                terminal={'complete':True,'all_inputs_unchanged':True,'phase':'development','passed_two_year_screen':['glaozi50'],
                    'results':{'40/faber10':{**m,'2024_return_pct':-1.,'2026_return_pct':future},'40/glaozi50':{**m,'2026_return_pct':-future}}}
                (p/'terminal.json').write_text(json.dumps(terminal));self.assertEqual(selected('forward',p),['glaozi50'])
        self.assertGreaterEqual(len(preserved(ROOT)),210)


@unittest.skipUnless(importlib.util.find_spec('qlib'),'optional Qlib unavailable')
class Batch3ScheduleTests(unittest.TestCase):
    def strategy(self,name,dates,prices,account):
        import pandas as pd
        from stock_rsi.blogger_batch3_qlib import Batch3Strategy
        days=tuple(map(date.fromisoformat,dates));state={'step':len(dates)-3}
        class Snapshot:
            calendar=days
            def value(self,c,f,d):
                if d>=dates[state['step']] or f=='open':raise AssertionError('future or execution-day price read')
                return prices.get((c,d),100.) if f=='close' else 1.
        config={'id':name,'symbols':[STOCK] if name=='faber10' else [STOCK,BOND]};s=Batch3Strategy(config=config,snapshot=Snapshot(),extra=40)
        p=SimpleNamespace(get_stock_amount_dict=lambda:account['owned'],calculate_value=lambda:account['equity'],get_cash=lambda **kw:account['cash'])
        s.common_infra=SimpleNamespace(get=lambda key:SimpleNamespace(current_position=p));s.level_infra=SimpleNamespace(get=lambda key:SimpleNamespace(get_step_time=lambda:(pd.Timestamp(days[state['step']]),pd.Timestamp(days[state['step']]))))
        return s,state

    def test_midmonth_crash_does_not_replace_frozen_month_end_signal(self):
        # Synthetic sparse fixture with explicit real session anchors, not a generated production calendar.
        dates=MONTHS+['2024-01-02','2024-01-03','2024-01-04'];prices={(STOCK,d):90.+i for i,d in enumerate(MONTHS)};prices[STOCK,'2024-01-02']=1.
        s,state=self.strategy('faber10',dates,prices,{'owned':{},'equity':100000.,'cash':100000.});s.generate_trade_decision();before=s.intents[-1]
        state['step']+=1;s.generate_trade_decision();after=s.intents[-1]
        self.assertTrue(before['formation']);self.assertFalse(after['formation']);self.assertTrue(after['regime_after']);self.assertEqual(after['signal_rows'],before['signal_rows']);self.assertEqual(after['orders'][0]['side'],'BUY')

    def test_yearly_target_execution_ends_then_ignores_midyear_nav_changes(self):
        dates=['2023-12-29','2024-01-02','2024-01-03','2024-01-04'];prices={(STOCK,d):10. for d in dates};account={'owned':{},'equity':100000.,'cash':100000.}
        s,state=self.strategy('glaozi50',dates,prices,account);s.generate_trade_decision();target=s.intents[-1]['target_normalized_units'].copy();self.assertEqual(target,{STOCK:4700.,BOND:400.})
        account['owned']=target.copy();account['cash']=13000.;state['step']+=1;s.generate_trade_decision();self.assertFalse(s.intents[-1]['execution_active_after'])
        account['equity']=200000.;account['cash']=50000.;state['step']+=1;s.generate_trade_decision();self.assertFalse(s.intents[-1]['formation']);self.assertEqual(s.intents[-1]['orders'],[]);self.assertEqual(s.intents[-1]['target_normalized_units'],target)

if __name__=='__main__':unittest.main()
