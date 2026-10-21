"""Synthetic raw runner state preservation; no source projection or real replay."""
import copy
import importlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
from stock_rsi.calendar import TradingCalendar
from stock_rsi.stock_distribution_account import StockDistribution


class IvolRawRunnerTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.run_ivol_raw_pre2026')
        except ModuleNotFoundError:self.fail('IVOL raw runner missing')

    def context(self,m,root):
        p=Path(root)/'immutable';p.write_text('original')
        cal=TradingCalendar(['2023-12-29','2024-01-02','2024-01-03'])
        bars={'SH600001':{d.isoformat():dict(date=d.isoformat(),code='sh.600001',open='10',high='10',low='10',close='10',preclose='10',volume='100000',amount='1000000',adjustflag='3',tradestatus='1',isST='0') for d in cal.days}}
        return {'plan':{'initial_CNY':'1000000','extra_cost_bps':[20,40],'policy_id':m.POLICY},
                'calendar':cal,'bars':bars,'events':(),'targets':{'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}},
                'lifecycles':{},'known_hashes':{str(p):m.file_sha(p)}}

    def test_guard_failure_preserves_actual_partial_trace_and_both_profiles_without_roi(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            ctx=self.context(m,d);ctx['bars']['SH600001']['2024-01-02']['isST']='1';out=Path(d)/m.OUTPUT
            with patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                result=m.run_profiles(ctx,out,plan_sha='a'*64)
            score.assert_not_called();self.assertFalse(result['annual_returns_computed'])
            self.assertEqual(set(result['results_by_extra_bps']),{'20','40'})
            for bps in ('20','40'):
                case=result['results_by_extra_bps'][bps];self.assertEqual(case['status'],'INVALID_ACCOUNT_OR_SOURCE')
                state=json.loads((out/bps/'failed_account_state.json').read_text())
                self.assertEqual(state['last_account_clock'],['2023-12-29',1])
                self.assertEqual(state['fills'],[]);self.assertEqual(state['cash'],'1000000')
                trace=json.loads((out/bps/'partial_engine_trace.json').read_text())
                self.assertEqual(trace['failed_session'],'2024-01-02');self.assertEqual(len(trace['days']),1);self.assertEqual(len(trace['intents']),1)
                deps=json.loads((out/bps/'required_source_dependencies.json').read_text())
                self.assertEqual(deps['required_codes'],['SH600001']);self.assertEqual(deps['source_rows']['SH600001']['isST'],'1')
                self.assertNotIn('2024_return_pct',case)

    def test_interruption_records_terminal_summary_without_annual_score(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            ctx=self.context(m,d)
            def interrupt(*args,**kwargs):raise KeyboardInterrupt('synthetic interrupt')
            with patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                result=m.run_profiles(ctx,Path(d)/m.OUTPUT,plan_sha='a'*64,simulator=interrupt)
            self.assertFalse(result['annual_returns_computed']);score.assert_not_called()
            self.assertEqual(result['abnormal_exit']['error_type'],'KeyboardInterrupt')
            self.assertEqual(result['results_by_extra_bps']['40']['status'],'NOT_RUN_AFTER_INTERRUPTION')
            self.assertTrue((Path(d)/m.OUTPUT/'summary.json').exists())

    def test_returned_case_survives_validation_or_persistence_failure(self):
        m=self.api()
        for stage in ('validation','persistence'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as d:
                ctx=self.context(m,d);out=Path(d)/m.OUTPUT
                with patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                    if stage=='validation':result=m.run_profiles(ctx,out,plan_sha='a'*64)
                    else:
                        with patch.object(m,'validate_completed_case',return_value=[]),patch.object(m,'persist_case',side_effect=ValueError('synthetic persistence rejection')):
                            result=m.run_profiles(ctx,out,plan_sha='a'*64)
                score.assert_not_called();self.assertFalse(result['annual_returns_computed'])
                for bps in ('20','40'):
                    saved=json.loads((out/bps/'returned_case_before_validation.json').read_text())
                    trace=json.loads((out/bps/'partial_engine_trace.json').read_text())
                    self.assertEqual(len(saved['days']),3);self.assertEqual(len(saved['intents']),1);self.assertGreater(len(saved['fills']),0)
                    self.assertEqual(trace['days'],saved['days']);self.assertEqual(trace['intents'],saved['intents'])
                    self.assertEqual(trace['failure_stage'],'POST_SIMULATION_VALIDATION_OR_PERSISTENCE')
                    self.assertIsNone(trace['failed_session']);self.assertEqual(trace['last_completed_session'],'2024-01-03')

    def test_postcheck_mutation_blocks_all_scores_and_retains_two_results(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            ctx=self.context(m,d);calls=[]
            def completed(*args,**kwargs):
                calls.append(1);Path(next(iter(ctx['known_hashes']))).write_text('changed');return {'days':[], 'intents':[], 'corporate_ledger':[]}
            with patch.object(m,'validate_completed_case',return_value=[]),patch.object(m,'persist_case',return_value={}),patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                result=m.run_profiles(ctx,Path(d)/m.OUTPUT,plan_sha='a'*64,simulator=completed)
            self.assertEqual(len(calls),2);self.assertFalse(result['source_inputs_unchanged_after_replay']);self.assertFalse(result['annual_returns_computed']);score.assert_not_called()

    def test_both_completed_and_postcheck_precede_any_scoring(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            ctx=self.context(m,d);seen=[]
            def completed(*args,**kwargs):seen.append('case');return {}
            def score(*args):
                self.assertEqual(seen,['case','case']);return {'2024_return_pct':1.,'2025_return_pct':2.,'average_exposure_pct':91.}
            with patch.object(m,'validate_completed_case',return_value=[]),patch.object(m,'persist_case',return_value={}),patch.object(m,'score_case',side_effect=score) as scored:
                result=m.run_profiles(ctx,Path(d)/m.OUTPUT,plan_sha='a'*64,simulator=completed)
            self.assertTrue(result['annual_returns_computed']);self.assertEqual(scored.call_count,2);self.assertTrue(result['raw_daily_proxy_development_gate_passes'])

    def test_unknown_tax_needs_exact_six_zero_record_and_ex_rows(self):
        m=self.api();events=[];ledger=[]
        for i in range(6):
            event=StockDistribution(str(i),'SH60000'+str(i),date(2024,6,1),date(2024,6,12),date(2024,6,13),date(2024,6,13),date(2024,6,13),D('.1'),D('.2'),False)
            events.append(event);ledger.extend([{'kind':'RECORD_DATE_OWNERSHIP','event_id':event.event_id,'instrument':event.instrument,'day':event.recorded,'quantity':0},{'kind':'EX_DATE_ENTITLEMENT','event_id':event.event_id,'instrument':event.instrument,'day':event.ex_date,'registered_quantity':0}])
        self.assertEqual(len(m.verify_unknown_zero(events,ledger)),6)
        for change in ('missing','duplicate','positive','wrongclock','bool'):
            bad=copy.deepcopy(ledger)
            if change=='missing':bad.pop()
            if change=='duplicate':bad.append(copy.deepcopy(bad[0]))
            if change=='positive':bad[1]['registered_quantity']=100
            if change=='wrongclock':bad[0]['day']=date(2024,6,13)
            if change=='bool':bad[0]['quantity']=False
            with self.subTest(change=change),self.assertRaises(ValueError):m.verify_unknown_zero(events,bad)

    def test_positive_unknown_tax_and_fractional_entitlement_fail_before_ex_mutation(self):
        m=self.api()
        for kind in ('stock_tax','fractional_capital'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                ctx=self.context(m,d)
                event=StockDistribution('event','SH600001',date(2023,12,28),date(2024,1,2),date(2024,1,3),date(2024,1,3),date(2024,1,3),D('.1'),D('0') if kind=='stock_tax' else D('.000001'),kind!='stock_tax',stock_per_share=D('.4') if kind=='stock_tax' else D('0'))
                ctx['events']=(event,);out=Path(d)/m.OUTPUT
                with patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                    result=m.run_profiles(ctx,out,plan_sha='a'*64)
                score.assert_not_called();self.assertFalse(result['annual_returns_computed'])
                for bps in ('20','40'):
                    state=json.loads((out/bps/'failed_account_state.json').read_text())
                    self.assertEqual(state['last_account_clock'],['2024-01-02',1]);self.assertGreater(state['entitlements']['event'],0)
                    self.assertEqual(state['cash_claims'],[]);self.assertEqual(state['stock_claims'],[])
                    self.assertFalse(any(x['kind']=='EX_DATE_ENTITLEMENT' for x in state['corporate_ledger']))
                    text=result['results_by_extra_bps'][bps]['error'];self.assertIn('stock dividend tax basis' if kind=='stock_tax' else 'fractional corporate entitlement',text)

    def test_continuous_annual_denominator_and_fixed_protocol(self):
        m=self.api();days=[{'day':'2023-12-29','equity':D('100'),'exposure':D(0),'fees':D(0)}]
        dates=[date(2024,1,2)+timedelta(days=i) for i in range(241)]+[date(2024,12,31)]
        dates += [date(2025,1,1)+timedelta(days=i) for i in range(242)]+[date(2025,12,31)]
        for d in dates:days.append({'day':d.isoformat(),'equity':D('110') if d.year==2024 else D('99'),'exposure':D('.95'),'fees':D(0)})
        got=m.score_case({'days':days,'orders':[],'fills':[],'intents':[]},'100')
        self.assertEqual(got['2024_return_pct'],10.);self.assertEqual(got['2025_return_pct'],-10.);self.assertEqual(got['net_compound_return_pct'],-1.)
        plan=dict(status='FROZEN_IVOL_RAW_PRE2026_DAILY_ENGINEERING_PLAN',initial_CNY='1000000',extra_cost_bps=[20,40],reference_extra_bps=40,
            window=['2023-12-29','2025-12-31'],policy_id=m.POLICY,allocator='plan_budgeted_raw_targets',source_guard='ordinary_source_rows_on',
            tax_reserve_rate='0.2',minimum_average_exposure_pct=90,candidate_budget=1,profile_budget=2,output_relative=m.OUTPUT,
            protocol_file=m.PROTOCOL,source_request_file=m.SOURCE_REQUEST,new_2026_queries_allowed=False,investment_rule_changed=False,
            method_code_sha256=dict.fromkeys(m.METHOD_FILES,'a'*64),public_evidence_sha256=dict.fromkeys(m.PUBLIC_FILES,'b'*64),local_source_sha256=dict.fromkeys(m.LOCAL_FILES,'c'*64))
        m.validate_plan(plan)
        for field,value in [('local_source_sha256',{}),('public_evidence_sha256',{}),('method_code_sha256',{}),('allocator','plan_integer_targets'),('source_guard','source_rows_on'),('profile_budget',True),('minimum_average_exposure_pct',89),('extra_cost_bps',[40])]:
            changed=copy.deepcopy(plan);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate_plan(changed)

    def test_output_hash_preflight_and_scope_are_fail_closed(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);out=base/m.OUTPUT;plan=base/'plan.json';plan.write_text('{}')
            args=['--source-root',d,'--plan',str(plan),'--expected-plan-sha256','0'*64,'--output-dir',str(out),'--source-preflight-only']
            with self.assertRaises(ValueError):m.main(args)
            self.assertFalse(out.exists());args[5]=m.file_sha(plan)
            with patch.object(m,'load_inputs',return_value={'known_hashes':{},'plan':{}}),patch.object(m,'run_profiles',side_effect=AssertionError('account forbidden')) as run:
                self.assertEqual(m.main(args),0);run.assert_not_called()
            self.assertFalse(out.exists());out.mkdir()
            with patch.object(m,'load_inputs',side_effect=AssertionError('load forbidden')):
                with self.assertRaises(ValueError):m.main(args)
        self.assertFalse(m.valid_negative_controls({}));self.assertFalse(m.valid_negative_controls({'a':True,'b':True,'c':True,'d':1}))
        self.assertTrue(m.valid_negative_controls(dict.fromkeys(('a','b','c','d'),True)))

if __name__=='__main__':unittest.main()
