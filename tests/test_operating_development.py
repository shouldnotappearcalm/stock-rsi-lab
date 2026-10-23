import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
try:
    from scripts import run_qlib_operating_pre2026 as run
except ImportError:
    run=None


def protocol():
    return {'status':'FROZEN_BEFORE_ONE_OPERATING_PROFITABILITY_DEVELOPMENT_SCREEN','output_subdir':'operating-profitability-conditional-development-v1-20261023',
        'provider_relative':'qlib-price-delay-pre2026-clock-v2-20261021','candidate':'operating_profit_prior_assets_top_decile_conditional',
        'controls':['eligible_equal_weight','operating_profit_prior_assets_bottom_decile_control'],'candidate_budget':1,'operating_family_trial':1,
        'account_window':['2024-01-02','2025-12-31'],'capital_CNY':1000000,'extra_bps':[20,40],'target_exposure':.95,'ranking_fraction':'1/10',
        'minimum_eligible':100,'minimum_active_cohort_fraction':None,'freshness_rule':'YEAR_MINUS2_THROUGH_JUNE_YEAR_MINUS1_FROM_JULY',
        'conditional_engineering_assumptions_explicit':True,'network_permitted':False,'2026_financial_or_market_values_permitted':False,
        'execution_adapter':'scripts.run_qlib_profitability_pre2026.simulate'}


class OperatingDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run,'frozen operating development runner missing');t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.base=Path(t.name)
        p=self.base/'input';p.write_text('original');self.paths={'source/input':p}
        self.req={**protocol(),'input_sha256':{'source/input':run.sha(p)},'formations':[{'execution_session':'2024-01-02','as_of':'2023-12-29T15:05:00+08:00'}]}
        self.request=self.base/'request.json';run.write_once(self.request,self.req);self.h=run.sha(self.request)
        self.receipt={'formation_asof':'2023-12-29','latest_factor_price_read':'2023-12-29'}

    def form(self,base,req,out):
        folder=out/'formations';folder.mkdir();run.write_once(folder/'2024-01-02.json',{'retained':'completed source formation'})
        return {n:{'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}} for n in run.NAMES},[self.receipt]

    def simulation(self,provider,targets,*,name,extra_bps,out,base,req):
        run.write_once(out/'engine-witness.json',{'name':name,'extra_bps':extra_bps})
        return {'status':'DAILY_PROXY_DEVELOPMENT_RECONCILED','2024_return_pct':5.,'2025_return_pct':7.,'average_exposure_pct':94.,'turnover_x_initial':3.,'unverified_held_marks':0}

    def execute(self,**kwargs):
        with patch.object(run,'verify',return_value=(self.req,self.paths)):
            return run.run(self.base,self.base,self.base/'members',self.request,self.h,form_targets=kwargs.get('form',self.form),simulation=kwargs.get('sim',self.simulation))

    def test_all_six_profiles_and_primary_only_development_gate(self):
        s=self.execute();self.assertEqual(len(s['results_by_extra_bps_and_family']),6);self.assertEqual(s['selected_development_lead'],run.PRIMARY)
        self.assertFalse(s['objective_achieved']);self.assertFalse(s['2026_financial_or_market_values_read'])
        self.assertTrue(run.read(self.base/run.OUTPUT/'terminal.json')['completed'])
        with self.assertRaises(ValueError):self.execute()

    def test_profitable_controls_cannot_replace_failed_primary(self):
        def sim(*a,**kw):
            d=self.simulation(*a,**kw)
            if kw['name']==run.PRIMARY:d['2024_return_pct']=-1.
            return d
        self.assertIsNone(self.execute(sim=sim)['selected_development_lead'])

    def test_nonfinite_metrics_retain_profile_prefix_and_failure(self):
        def sim(*a,**kw):
            d=self.simulation(*a,**kw)
            if kw['name']=='eligible_equal_weight':d['2025_return_pct']=float('nan')
            return d
        with self.assertRaises(ValueError):self.execute(sim=sim)
        out=self.base/run.OUTPUT;t=run.read(out/'terminal.json');self.assertEqual(t['completed_profiles'],['20/'+run.PRIMARY]);self.assertFalse(t['completed']);self.assertFalse((out/'summary.json').exists())

    def test_source_initial_read_or_later_profile_error_retains_original_and_source_changes(self):
        original=KeyboardInterrupt('source read interrupted')
        def form(base,req,out):self.form(base,req,out);self.request.write_text('{}');raise original
        with self.assertRaises(KeyboardInterrupt) as got:self.execute(form=form)
        self.assertIs(got.exception,original);t=run.read(self.base/run.OUTPUT/'terminal.json')
        self.assertFalse(t['postcheck']['all_inputs_unchanged']);self.assertEqual(t['completed_profiles'],[])
        self.assertTrue((self.base/run.OUTPUT/'formations/2024-01-02.json').exists())

    def test_summary_persistence_interrupt_and_input_mutation_never_complete(self):
        writer=run.write_once;original=InterruptedError('summary interrupted')
        def write(path,value):
            if path.name=='.summary-pending.json':self.request.write_text('{}');raise original
            writer(path,value)
        with patch.object(run,'write_once',side_effect=write),self.assertRaises(InterruptedError) as got:self.execute()
        self.assertIs(got.exception,original);out=self.base/run.OUTPUT;t=run.read(out/'terminal.json')
        self.assertFalse(t['completed']);self.assertFalse(t['postcheck']['all_inputs_unchanged']);self.assertFalse((out/'summary.json').exists())

    def test_request_rejects_extra_candidate_future_and_lowered_coverage(self):
        run.validate_request(protocol())
        for k,v in [('candidate_budget',2),('minimum_eligible',99),('target_exposure',.5),('2026_financial_or_market_values_permitted',True),('candidate','eligible_equal_weight')]:
            d=protocol();d[k]=v
            with self.subTest(key=k),self.assertRaises(ValueError):run.validate_request(d)
