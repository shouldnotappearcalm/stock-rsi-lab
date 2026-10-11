import json
import tempfile
import unittest
from pathlib import Path

from stock_rsi.data import Dataset
from stock_rsi.time import parse_time

DATA=Path(__file__).resolve().parents[1]/'data/fixtures/synthetic_cn_v1.json'


class VerificationTests(unittest.TestCase):
    def test_negative_return_and_incomplete_research_data_allow_exploratory_run(self):
        from stock_rsi.verification import verify_run
        report={'status':'COMPLETED_ENGINEERING','errors':[],
                'account':{'cash':'900','equity':'900','market_value':'0','positions':{}},
                'manifest':{'evidence_level':'REAL_PRICE_ENGINEERING_ONLY',
                            'provenance':{'assumptions':['limits reconstructed','actions incomplete']}}}
        gate=verify_run(report)
        self.assertEqual(gate['hard_checks']['status'],'PASS')
        self.assertTrue(gate['exploratory_backtest_allowed'])
        self.assertFalse(gate['research_promotion_allowed'])
        self.assertIn('actions incomplete',gate['warnings'])

    def test_account_corruption_or_runtime_error_remains_hard_failure(self):
        from stock_rsi.verification import verify_run
        base={'status':'COMPLETED_ENGINEERING','errors':[],
              'account':{'cash':'-0.01','equity':'1','market_value':'0','positions':{}},
              'manifest':{'evidence_level':'REAL_PRICE_ENGINEERING_ONLY','provenance':{}}}
        self.assertFalse(verify_run(base)['exploratory_backtest_allowed'])
        base['account']['cash']='1';base['errors']=[{'stage':'agent','error':'invalid evidence'}]
        self.assertFalse(verify_run(base)['exploratory_backtest_allowed'])

    def test_equity_and_marked_holdings_must_conserve_account_value(self):
        from stock_rsi.verification import verify_run
        report={'status':'COMPLETED_ENGINEERING','errors':[],
                'account':{'cash':'900','equity':'1','market_value':'0','positions':{}},
                'manifest':{'evidence_level':'REAL_PRICE_ENGINEERING_ONLY','provenance':{}}}
        self.assertFalse(verify_run(report)['exploratory_backtest_allowed'])
        report['account']={'cash':'900','equity':'1000','market_value':'100','positions':{'A':{'quantity':100,'mark_price':'1'}}}
        self.assertTrue(verify_run(report)['exploratory_backtest_allowed'])
        report['account']['positions']['A']['mark_price']='0.5'
        self.assertFalse(verify_run(report)['exploratory_backtest_allowed'])

    def test_snapshot_window_keeps_recent_visible_bars_and_non_price_facts(self):
        data=Dataset.load(DATA);at=parse_time('2024-10-09T17:00:00+08:00')
        snap=data.snapshot(at,bar_limit=10).to_dict()
        bars=[r for r in snap['records'] if r['kind']=='bar']
        self.assertEqual(len(bars),10)
        self.assertEqual(max(r['payload']['trade_date'] for r in bars),'2024-10-09')
        self.assertIn('filing-v2',[r['record_id'] for r in snap['records']])
        self.assertTrue(all(parse_time(r['available_at'])<=at for r in snap['records']))
        for limit in (0,-1,True):
            with self.assertRaises(ValueError):data.snapshot(at,bar_limit=limit)

    def test_compact_run_keeps_decisions_ledger_and_replay_equal_to_full_history(self):
        from stock_rsi.runner import run,replay
        from stock_rsi.skill import RuleAgent,Skill
        config={'start':'2024-09-02T00:00:00+08:00','end':'2024-10-18T17:00:00+08:00'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            full=run(DATA,config,RuleAgent(Skill()),root/'full')
            compact=run(DATA,config|{'snapshot_bar_limit':10},RuleAgent(Skill()),root/'compact')
            self.assertEqual([r.get('decision') for r in full['wakes']],[r.get('decision') for r in compact['wakes']])
            self.assertEqual(full['account'],compact['account'])
            # Decision IDs bind different snapshots, so compare economic fill fields.
            def economics(fills):return [{k:v for k,v in f.items() if k!='order_id'} for f in fills]
            self.assertEqual(economics(full['fills']),economics(compact['fills']))
            self.assertEqual(replay(root/'compact',root/'replay')['fills'],compact['fills'])
            self.assertEqual(compact['verify_gate']['hard_checks']['status'],'PASS')
