import ast
from pathlib import Path
import unittest

from scripts.return_family_development_inputs import prepare_events as prepare_development
import scripts.reversal_full_inputs as full
from scripts.reversal_full_inputs import prepare_events as prepare_full
from stock_rsi.data import digest


class ReversalFullInputsTests(unittest.TestCase):
    def test_adapter_opens_only_new_date_scope_while_development_stays_closed(self):
        row={'code':'sh.600001','dividPlanDate':'2026-05-01','dividRegistDate':'2026-05-07',
             'dividOperateDate':'2026-05-08','dividPayDate':'2026-05-08','dividStockMarketDate':'',
             'dividCashPsBeforeTax':'.1','dividStocksPs':'0','dividReserveToStockPs':'0'}
        packets={'SH600001':{'instrument':'SH600001','distributions':[row]}}
        targets={'2026-06-01':{'as_of':'2026-05-29','weights':{'SH600001':.95}}}
        with self.assertRaises(ValueError):prepare_development(packets,targets,{})
        _,events,_=prepare_full(packets,targets,{})
        self.assertEqual(events[0].ex_date.isoformat(),'2026-05-08')
        targets={'2026-11-02':{'as_of':'2026-10-30','weights':{'SH600001':.95}}}
        with self.assertRaises(ValueError):prepare_full(packets,targets,{})

    def test_corporate_algorithm_matches_the_frozen_development_function(self):
        root=Path(__file__).resolve().parents[1]
        functions=[]
        for file in ('return_family_development_inputs.py','reversal_full_inputs.py'):
            tree=ast.parse((root/'scripts'/file).read_text())
            functions.append(ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_events')))
        self.assertEqual(*functions)

    def test_cash_component_resolution_is_source_bound_and_conserves_declared_amount(self):
        self.assertTrue(hasattr(full,'resolve_cash_components'),'primary cash resolver missing')
        import copy
        base={'code':'sh.601966','dividPlanDate':'2024-06-07','dividRegistDate':'2024-06-13',
              'dividOperateDate':'2024-06-14','dividPayDate':'2024-06-14','dividStockMarketDate':'',
              'dividStocksPs':'0','dividReserveToStockPs':'0'}
        rows=[base|{'dividCashPsBeforeTax':v} for v in ('.286','.091')]
        original={'SH601966':{'distributions':rows}};saved=copy.deepcopy(original)
        rule={'instrument':'SH601966','ex_date':'2024-06-14','source_row_digests':[digest(r) for r in rows],
              'replacement_record':base|{'dividCashPsBeforeTax':'.377'},'source_file':'notice.pdf','source_sha256':'proof'}
        result,receipts=full.resolve_cash_components(original,{'resolved_cash_components':[rule]})
        self.assertEqual(original,saved);self.assertEqual(result['SH601966']['distributions'],[rule['replacement_record']])
        self.assertEqual(len(receipts),1)
        wrong=copy.deepcopy(rule);wrong['replacement_record']['dividCashPsBeforeTax']='.5'
        with self.assertRaises(ValueError):full.resolve_cash_components(original,{'resolved_cash_components':[wrong]})
        altered=copy.deepcopy(original);altered['SH601966']['distributions'][0]['dividCashPsBeforeTax']='.5'
        with self.assertRaises(ValueError):full.resolve_cash_components(altered,{'resolved_cash_components':[rule]})
        wrong=copy.deepcopy(rule);wrong['replacement_record']['dividPayDate']='2024-06-17'
        with self.assertRaises(ValueError):full.resolve_cash_components(original,{'resolved_cash_components':[wrong]})
