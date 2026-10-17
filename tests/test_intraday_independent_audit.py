"""Exercise real standalone verifier functions without running data ingestion."""
import ast
import copy
from collections import defaultdict
from datetime import datetime
from decimal import Decimal as D, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from stock_rsi.data import digest


class IndependentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-17-intraday-independent-ledger.py'
        tree=ast.parse(source.read_text())
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef)
                   and node.name in ('audit_children','authenticate_parents','cents','fee_for')]
        cls.scope={'datetime':datetime,'ZoneInfo':ZoneInfo,'defaultdict':defaultdict,'digest':digest,
                   'D':D,'ROUND_DOWN':ROUND_DOWN,'ROUND_UP':ROUND_UP,'ROUND_HALF_UP':ROUND_HALF_UP}
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),cls.scope)

    def test_rejects_duplicate_security_window_before_individual_capacity_checks(self):
        children=[{'submitted_at':'2024-01-03T01:35:00+00:00','security_id':'A','parent_id':'P','quantity':q}
                  for q in (100,200)]
        with self.assertRaisesRegex(AssertionError,'duplicate security/window'):
            self.scope['audit_children']('2024-01-03',children,[],[],1000,0,10000)

    def test_parent_binds_to_intent_and_rejects_extra_or_negative_remaining(self):
        decision={'action':'BUY','security_id':'A','quantity':100,'evidence_ids':['e'],'reason':'fixture'}
        intent={'as_of':'2024-01-02T07:05:00+00:00','snapshot_sha256':'snapshot',
                'execution_session':'2024-01-03','decisions':[decision]}
        parent={'order_id':'P','decision_id':digest({'decision':decision,'snapshot':'snapshot'}),
                'action':'BUY','security_id':'A','quantity':100,'submitted_at':intent['as_of'],
                'eligible_at':'2024-01-03T01:30:00+00:00','expires_at':'2024-01-03T06:55:00+00:00',
                'remaining':0,'filled_quantity':100}
        check=self.scope['authenticate_parents'];check([parent],[intent])
        for change in ({'remaining':-100,'filled_quantity':200},{'quantity':200},{'eligible_at':'2024-01-04T01:30:00+00:00'}):
            changed=copy.deepcopy(parent);changed.update(change)
            with self.assertRaises(AssertionError):check([changed],[intent])
        with self.assertRaises(AssertionError):check([parent,parent|{'order_id':'extra'}],[intent])

    def test_verifier_rejects_odd_share_partial_fill(self):
        at=datetime.fromisoformat('2024-01-03T01:35:00+00:00');end=datetime.fromisoformat('2024-01-03T01:40:00+00:00')
        prev={'start':datetime.fromisoformat('2024-01-03T01:30:00+00:00'),'end':at,'volume':10000,'evidence':'previous'}
        current={'start':at,'end':end,'volume':10000,'buy':D(10),'sell':D(10),'evidence':'current'}
        self.scope['tape']=lambda code,day:[prev,current]
        self.scope['bars']={'A':{'2024-01-03':{'preclose':'10'}}}
        parent={'order_id':'P','security_id':'A','action':'SELL','quantity':100,
                'submitted_at':'2024-01-02T07:05:00+00:00','eligible_at':'2024-01-03T01:30:00+00:00',
                'expires_at':'2024-01-03T06:55:00+00:00'}
        child={'parent_id':'P','security_id':'A','action':'SELL','quantity':100,'limit_price':'9.05',
               'submitted_at':at.isoformat(),'expires_at':end.isoformat(),'source_volume_as_of':at.isoformat(),
               'source_evidence_id':'previous','source_volume_lower_shares':10000,'reserved_cash':'0',
               'filled_quantity':3,'status':'PARTIAL_WINDOW_EXPIRED'}
        child['order_id']=digest({'parent':'P','start':at.isoformat(),'end':end.isoformat(),
                                 'quantity':100,'previous_volume':10000,'evidence_id':'previous'})
        fill={'order_id':child['order_id'],'parent_id':'P','security_id':'A','action':'SELL',
              'quantity':3,'price':'10','execution_at':end.isoformat(),'current_evidence_id':'current',
              'current_volume_lower_shares':10000,'cost':'5','cash_after':'10025'}
        with self.assertRaisesRegex(AssertionError,'illegal odd-share partial fill'):
            self.scope['audit_children']('2024-01-03',[child],[parent],[fill],1000,0,D(10000))
