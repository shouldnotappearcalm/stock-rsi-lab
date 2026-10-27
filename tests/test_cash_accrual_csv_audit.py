from copy import deepcopy
import csv,json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from scripts.audit_cash_accrual_development import audit_case

class CashAccrualCsvAuditTests(TestCase):
    def fixture(self,folder,change=None):
        dates=['2024-12-31','2025-12-31']
        days=[{'session':s,'cash':89,'stock_value':10,'account_value':99,'cost':1 if i==0 else 0} for i,s in enumerate(dates)]
        orders=[{'session':dates[0],'signal_date':'2024-12-30','instrument':'SH600001','side':'BUY','filled_normalized_units':10,'signed_trade_value':10,'cost':1,'normalized_price':1}]
        holds=[{'session':s,'instrument':'SH600001','normalized_units':10,'normalized_price':1,'value':10} for s in dates]
        metrics={'2024_return_pct':-1,'2025_return_pct':0,'average_exposure_pct':10/99*100,'max_drawdown_pct':-1,'final_account_CNY':99,'cost_pct_initial':1,'turnover_x_initial':.1,'unverified_held_marks':0}
        if change=='fee':orders[0]['cost']=0
        if change=='nav':days[1]['account_value']=100
        if change=='quantity':holds[0]['normalized_units']=11
        if change=='return':metrics['2025_return_pct']=1
        for name,rows in [('days.csv',days),('orders.csv',orders),('holdings.csv',holds)]:
            with (folder/name).open('w') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        (folder/'suspension_mark_audit.json').write_text('[]');return metrics,dates
    def test_manual_continuous_account_annual_denominators_and_cash_flows(self):
        with TemporaryDirectory() as t:
            folder=Path(t);m,s=self.fixture(folder);p=audit_case(folder,m,s,100)
            self.assertAlmostEqual(p['2024_return_pct'],-1);self.assertEqual(p['2025_return_pct'],0)
    def test_erased_fee_forged_nav_quantity_or_return_fails_arithmetic_without_hash_gate(self):
        for kind in ('fee','nav','quantity','return'):
            with self.subTest(kind=kind),TemporaryDirectory() as t:
                folder=Path(t);m,s=self.fixture(folder,kind)
                with self.assertRaises(ValueError):audit_case(folder,m,s,100)

    def test_signed_sell_units_reduce_inventory_and_keep_annual_denominator(self):
        with TemporaryDirectory() as t:
            f=Path(t);m,dates=self.fixture(f)
            with (f/'orders.csv').open('a') as o:o.write('2025-12-31,2025-12-30,SH600001,SELL,-10,-10,1,1\n')
            (f/'holdings.csv').write_text('session,instrument,normalized_units,normalized_price,value\n2024-12-31,SH600001,10,1,10\n')
            (f/'days.csv').write_text('session,cash,stock_value,account_value,cost\n2024-12-31,89,10,99,1\n2025-12-31,98,0,98,1\n')
            m.update({'2025_return_pct':(98/99-1)*100,'average_exposure_pct':10/99*50,'max_drawdown_pct':-2,'final_account_CNY':98,'cost_pct_initial':2,'turnover_x_initial':.2})
            self.assertAlmostEqual(audit_case(f,m,dates,100)['2025_return_pct'],(98/99-1)*100)
