"""Synthetic calendar/prices only; no provider, outcomes or network."""
import ast
import copy
import importlib
import inspect
import math
import unittest
from datetime import date, timedelta

from stock_rsi import low_market_residual_vol as old


class SyntheticSource:
    """An explicitly synthetic weekday lattice, not the real exchange calendar."""
    def __init__(self):
        days=[];at=date(2023,11,30)
        excluded={date(2024,1,1),date(2025,1,1),date(2026,1,1),date(2026,1,2)}
        while at<=date(2026,10,22):
            if at.weekday()<5 and at not in excluded:days.append(at)
            at+=timedelta(days=1)
        self.calendar=tuple(days);self.reads=[];self.bad={};self.maximum_read='2026-09-30'
        symbols=[old.MARKET]+[f'SH600{i:03d}' for i in range(10)]
        self.values={c:{days[0]:100.} for c in symbols}
        for i,day in enumerate(days[1:]):
            x=(-.01,0.,.01)[i%3];noise=(.0001,-.0002,.0001)[i%3]
            for j,c in enumerate(symbols):
                value=x if c==old.MARKET else .00001*j+.1*j*x+j*noise
                self.values[c][day]=self.values[c][days[i]]*(1+value)

    def value(self,code,field,day):
        self.reads.append((code,field,day))
        if day>self.maximum_read:raise AssertionError('execution/future quote read')
        if code==old.MARKET and field!='close':raise AssertionError('index has close only')
        if (code,field,day) in self.bad:return self.bad[code,field,day]
        if field in ('factor','volume'):return 1.
        return self.values[code].get(date.fromisoformat(day))


def members():
    return {f'SH600{i:03d}':[('2020-01-01','2026-10-20')] for i in range(10)}


class ResidualVolHorizonTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('stock_rsi.low_market_residual_vol_horizon')
        except ModuleNotFoundError:self.fail('independent horizon factor entry missing')

    def test_34_synthetic_formations_have_exact_old24_prefix_targets_and_receipts(self):
        m=self.api();source=SyntheticSource();prior=SyntheticSource();prior.maximum_read='2025-11-28'
        expected_t,expected_r=old.build_targets(prior,members())
        got_t,got_r=m.build_targets(source,members())
        self.assertEqual(len(expected_r),24);self.assertEqual(len(got_r),34)
        self.assertEqual(got_r[:24],expected_r)
        for family in expected_t:
            self.assertEqual({d:v for d,v in got_t[family].items() if d<='2025-12-31'},expected_t[family])
            self.assertEqual(len(got_t[family]),34)
        self.assertTrue(all(r['controls_selectable'] is False for r in got_r))
        self.assertEqual(old.END,'2025-12-31');self.assertEqual(m.END,'2026-10-20')

    def test_2026_january_uses_entire_previous_december_and_previous_november_baseline(self):
        m=self.api();source=SyntheticSource();source.maximum_read='2025-12-31'
        targets,receipts=m.build_targets(source,members(),start='2026-01-05',end='2026-01-31')
        self.assertEqual(len(receipts),1);r=receipts[0]
        december=[d.isoformat() for d in source.calendar if d.year==2025 and d.month==12]
        self.assertEqual(r['execution_session'],'2026-01-05');self.assertEqual(r['formation_asof'],'2025-12-31')
        self.assertEqual(r['formation_at'],'2025-12-31T15:05:00+08:00');self.assertEqual(r['return_month'],'2025-12')
        self.assertEqual(r['sample_dates'],december);self.assertEqual(r['close_dates'],['2025-11-28']+december)
        self.assertEqual(r['baseline_close_day'],'2025-11-28');self.assertEqual(r['n'],23)
        self.assertEqual(r['selected'],['SH600000','SH600001']);self.assertAlmostEqual(sum(targets[m.FAMILIES[0]]['2026-01-05']['weights'].values()),.95)
        self.assertEqual(max(d for _,_,d in source.reads),'2025-12-31')

    def test_bad_stock_entire_month_excluded_and_bad_market_fails_without_neutral_values(self):
        m=self.api()
        for field,bad in [('close',None),('factor',math.nan),('volume',0.),('close',math.inf)]:
            source=SyntheticSource();source.bad['SH600000',field,'2025-12-08']=bad
            targets,receipts=m.build_targets(source,members(),start='2026-01-05',end='2026-01-05')
            self.assertEqual(receipts[0]['eligible'],9);self.assertEqual(receipts[0]['n'],23)
            self.assertNotIn('SH600000',targets['eligible_equal_weight']['2026-01-05']['weights'])
            self.assertIn('SH600000',receipts[0]['excluded'])
        for bad in (None,math.nan,0.):
            source=SyntheticSource();source.bad[old.MARKET,'close','2025-12-08']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):m.build_targets(source,members(),start='2026-01-05',end='2026-01-05')

    def test_short_or_missing_complete_month_and_missing_baseline_rejected_before_values(self):
        m=self.api()
        for kind in ('14sessions','missing_month','missing_baseline'):
            source=SyntheticSource();dec=[d for d in source.calendar if d.year==2025 and d.month==12]
            if kind=='14sessions':source.calendar=(date(2025,11,28),*dec[:14],date(2026,1,5))
            if kind=='missing_month':source.calendar=(date(2025,11,28),date(2026,1,5))
            if kind=='missing_baseline':source.calendar=(date(2025,10,31),*dec,date(2026,1,5))
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.build_targets(source,members(),start='2026-01-05',end='2026-01-05')
            self.assertEqual(source.reads,[])

    def test_future_poison_not_read_and_beyond_cap_rejected_before_snapshot_access(self):
        m=self.api();source=SyntheticSource();before=copy.deepcopy(source.values)
        _,receipts=m.build_targets(source,members())
        self.assertEqual(len(receipts),34);self.assertEqual(source.values,before)
        self.assertTrue(all(d<='2026-09-30' for _,_,d in source.reads))
        class Forbidden:
            @property
            def calendar(self):raise AssertionError('out-of-scope calendar accessed')
        for start,end in [('2024-01-02','2026-10-21'),('2023-12-29','2025-12-31'),('2026-10-20','2026-01-05')]:
            with self.subTest(start=start,end=end),self.assertRaises(ValueError):m.build_targets(Forbidden(),members(),start=start,end=end)
        prior=SyntheticSource()
        with self.assertRaises(ValueError):old.build_targets(prior,members(),end='2026-01-05')
        self.assertEqual(prior.reads,[])

    def test_inherited_pure_helpers_and_loop_ast_parity_supplement_behavior_tests(self):
        m=self.api()
        for name in ('residual_volatility_1m','lowest_quintile','_active','_target','_previous_month'):
            self.assertIs(getattr(m,name),getattr(old,name))
        a=ast.parse(inspect.getsource(old.build_targets)).body[0]
        b=ast.parse(inspect.getsource(m.build_targets)).body[0]
        # The date-guard error string alone differs; no loop or receipt logic changes.
        self.assertEqual(ast.dump(ast.Module(body=a.body[3:],type_ignores=[])),ast.dump(ast.Module(body=b.body[3:],type_ignores=[])))

if __name__=='__main__':unittest.main()
