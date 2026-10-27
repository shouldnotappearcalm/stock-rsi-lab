from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from scripts import run_cash_accrual_pre2026 as r
from scripts import audit_cash_accrual_wrapped_corpus as audit
from tests import test_cash_accrual_wrapped_corpus as fixtures


class CashAccrualDevelopmentTests(TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name);self.req=deepcopy(r.PROFILE)
        self.req['formations']=[{'execution_session':'2024-01-02'}];self.known={}
    def builder(self,base,root,req,known,out,save):
        receipt={'coverage_pass':True};save('formations/2024-01-02.json',receipt)
        return {n:{} for n in r.signal.NAMES},[receipt]
    def simulate(self,*args,**kw):
        (kw['out']/'evidence.json').write_text('{}')
        return {'status':'DAILY_PROXY_DEVELOPMENT_RECONCILED','2024_return_pct':5.,'2025_return_pct':6.,
                'average_exposure_pct':94.,'unverified_held_marks':0}
    def execute(self,**kw):
        return r.execute(self.base,self.base,self.req,self.known,'a'*64,builder=kw.pop('builder',self.builder),
                         simulation=kw.pop('simulation',self.simulate),**kw)
    def test_only_primary_high_cost_gate_can_pass_and_next_step_is_raw_validation(self):
        t=self.execute();self.assertTrue(t['complete']);self.assertEqual(t['selected_development_lead'],r.signal.PRIMARY)
        self.assertEqual(t['next_step'],'RAW_SHARE_SOURCE_AND_ACCOUNT_VALIDATION')
        self.assertFalse(t['physical_investment_admitted']);self.assertFalse(t['objective_achieved'])
        self.assertEqual(len(t['results_by_extra_bps']),6)
    def test_controls_or_low_cost_profit_cannot_rescue_failed_primary(self):
        def simulation(*args,**kw):
            v=self.simulate(*args,**kw)
            if kw['name']==r.signal.PRIMARY and kw['extra_bps']==40:v['2025_return_pct']=-1.
            return v
        t=self.execute(simulation=simulation);self.assertIsNone(t['selected_development_lead'])
        self.assertEqual(t['next_step'],'REJECT_THIS_FROZEN_CANDIDATE_NO2026_RUN')
    def test_unverified_marks_or_low_exposure_cannot_pass(self):
        for kind in ('marks','exposure'):
            results={f'40/{r.signal.PRIMARY}':{'2024_return_pct':3.,'2025_return_pct':5.,'average_exposure_pct':94.,'unverified_held_marks':0}}
            results[f'40/{r.signal.PRIMARY}']['unverified_held_marks' if kind=='marks' else 'average_exposure_pct']=1 if kind=='marks' else 89.
            self.assertIsNone(r.eligible_lead(results))
    def test_coverage_failure_saves_receipts_and_never_invokes_simulation(self):
        calls=[]
        def builder(base,root,req,known,out,save):
            save('formations/2024-01-02.json',{'coverage_pass':False,'eligible':99});raise ValueError('coverage')
        with self.assertRaisesRegex(ValueError,'coverage'):self.execute(builder=builder,simulation=lambda *a,**kw:calls.append(1))
        self.assertEqual(calls,[]);folder=self.base/r.OUTPUT;t=json.loads((folder/'terminal.json').read_text())
        self.assertFalse(t['complete']);self.assertFalse(t['portfolio_return_computed']);self.assertTrue((folder/'formations/2024-01-02.json').exists())
    def test_native_account_failure_keeps_prefix_without_complete_return(self):
        calls=[]
        def simulation(*args,**kw):
            calls.append(kw['name'])
            if len(calls)==2:raise ValueError('native account failure')
            return self.simulate(*args,**kw)
        with self.assertRaisesRegex(ValueError,'native account failure'):self.execute(simulation=simulation)
        folder=self.base/r.OUTPUT;t=json.loads((folder/'terminal.json').read_text())
        self.assertFalse(t['complete']);self.assertFalse(t['portfolio_return_computed']);self.assertFalse((folder/'results.json').exists())
        self.assertTrue((folder/f'20/{r.signal.PRIMARY}/metrics.json').exists())
    def test_mutated_input_quarantines_results_and_false_completion(self):
        path=self.base/'bound.txt';path.write_text('original');self.known[str(path.resolve())]=r.source.sha(path)
        def simulate(*a,**kw):
            v=self.simulate(*a,**kw)
            if kw['name']==r.signal.HIGH_CONTROL and kw['extra_bps']==40:path.write_text('mutated')
            return v
        with self.assertRaises(ValueError):self.execute(simulation=simulate)
        folder=self.base/r.OUTPUT;t=json.loads((folder/'terminal.json').read_text())
        self.assertFalse(t['complete']);self.assertFalse(t['portfolio_return_computed']);self.assertFalse((folder/'results.json').exists())
    def test_future_window_candidate_budget_controls_or_cost_changes_are_rejected(self):
        for key,value in [('account_window',['2024-01-02','2026-10-27']),('candidate_budget',2),
                          ('candidate','eligible_equal_weight'),('minimum_eligible',10),('extra_bps',[0]),
                          ('2026_financial_or_market_values_permitted',True)]:
            req={**self.req,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_profile(req)
    def test_source_audit_replays_and_counts_six_literal_cells(self):
        f=fixtures.CashAccrualWrappedCorpusTests('run');f.setUp();self.addCleanup(f.doCleanups)
        f.change_to_wrapped();d=f.docs[0];case=f.inspect();path=f.base/'case.json';path.write_text(json.dumps(case))
        subset={str(p.resolve()):f.known[str(p.resolve())] for p in audit.r.case_paths(f.base,d)}
        job=(f.base,d,None,subset,path,r.source.sha(path));checked=audit.check_one(job)
        self.assertEqual(checked['cells'],6);self.assertEqual(checked['source_parser_variant'],'V2_RECOVERED_LABEL')
        case['report']['parsed']['income']['2023-12-31']['net_profit']['value_CNY']='999.00';path.write_text(json.dumps(case))
        with self.assertRaises(ValueError):audit.check_one((*job[:-1],r.source.sha(path)))
