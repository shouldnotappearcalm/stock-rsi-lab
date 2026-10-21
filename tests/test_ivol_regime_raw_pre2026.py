"""Synthetic frozen-regime orchestration and old-failure preservation."""
import copy
import importlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from stock_rsi.calendar import TradingCalendar


class IvolRegimeRunnerTests(unittest.TestCase):
    def api(self):
        return importlib.import_module('scripts.run_ivol_regime_raw_pre2026')

    def context(self, m, root):
        frozen=Path(root)/'frozen';frozen.write_text('original')
        cal=TradingCalendar(['2023-12-29','2024-01-02','2024-01-03'])
        bars={'SH600001':{d.isoformat():dict(date=d.isoformat(),code='sh.600001',open='10',
          high='10',low='10',close='10',preclose='10',volume='1000000',amount='10000000',
          adjustflag='3',tradestatus='1',isST='0') for d in cal.days}}
        evidence={'contract':'SSE_MAINBOARD_RISK_WARNING_PRE2026_V1',
          'rule_document':{'source_file':'rule.docx','sha256':'a'*64,'published_on':'2023-02-17',
             'valid_from':'2023-12-29','valid_through':'2025-12-31'},'state_intervals':[],
          'account_capabilities':{'risk_warning_buy_permission':False}}
        return {'plan':{'initial_CNY':'1000000'},'calendar':cal,'bars':bars,'events':(),
          'targets':{'2024-01-02':{'as_of':'2023-12-29','weights':{'SH600001':.95}}},
          'lifecycles':{},'regime_evidence':evidence,'old_prefix':{},
          'known_hashes':{str(frozen):m.file_sha(frozen)}}

    def plan(self,m):
        return dict(status='FROZEN_IVOL_REGIME_RAW_PRE2026_DAILY_ENGINEERING_PLAN',
          initial_CNY='1000000',extra_cost_bps=[20,40],reference_extra_bps=40,
          window=['2023-12-29','2025-12-31'],policy_id=m.POLICY,
          allocator='plan_budgeted_raw_targets',source_guard='regime_source_rows_on',
          tax_reserve_rate='0.2',minimum_average_exposure_pct=90,candidate_budget=1,profile_budget=2,
          output_relative=m.OUTPUT,protocol_file=m.PROTOCOL,risk_warning_buy_permission=False,
          investment_rule_changed=False,new_2026_queries_allowed=False,
          old_failure_must_remain_unchanged=True,
          method_code_sha256=dict.fromkeys(m.METHOD_FILES,'a'*64),
          public_evidence_sha256=dict.fromkeys(m.PUBLIC_FILES,'b'*64),
          local_source_sha256=dict.fromkeys(m.LOCAL_FILES,'c'*64))

    def test_fixed_scope_permission_and_old_failure_binding_cannot_drift(self):
        m=self.api();p=self.plan(m);m.validate_plan(p)
        for key,value in [('risk_warning_buy_permission',True),('investment_rule_changed',True),
          ('new_2026_queries_allowed',True),('old_failure_must_remain_unchanged',False),
          ('minimum_average_exposure_pct',89),('profile_budget',True),('extra_cost_bps',[40]),
          ('method_code_sha256',{}),('local_source_sha256',{}),('public_evidence_sha256',{})]:
            changed=copy.deepcopy(p);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_plan(changed)

    def test_claimed_primary_documents_cannot_omit_actual_bytes_from_hash_map(self):
        m=self.api();manifest={'status':'HASH_VERIFIED_EXISTING_PRIMARY_READING_BYTES_IMPORTED_NO_NEW_NETWORK',
          'all_existing_inputs_unchanged':True,'SDK_queries':0,'HTTP_queries_in_this_import':0,
          'artifact_sha256':{},'documents':[{'file':'issuer-www-st-notice.pdf','sha256':'a'*64},
            {'file':'sse-trading-rules-2023.docx','sha256':'b'*64}]}
        calls=[]
        with self.assertRaisesRegex(ValueError,'complete primary'):
            m.validate_primary_evidence({},manifest,{},Path('/tmp'),lambda p,h:calls.append((p,h)))
        self.assertEqual(calls,[])
        manifest['artifact_sha256']=dict.fromkeys(['issuer-www-st-notice.pdf','sse-trading-rules-2023.docx',
          'reading-download-receipts-additional.json','issuer-st-notice-text.txt','sse-trading-rules-2023-text.txt'],'a'*64)
        with self.assertRaisesRegex(ValueError,'authenticated artifact'):
            m.validate_primary_evidence({},manifest,{},Path('/tmp'),lambda p,h:calls.append((p,h)))
        self.assertEqual(calls,[])

    def test_old_failed_financial_prefix_and_intents_must_stay_identical(self):
        m=self.api();days=[{'day':str(date(2024,1,1)+timedelta(days=i)),'cash':'100'} for i in range(474)]
        case={'days':days,'intents':[{'snapshot_sha256':'a'}]*24,'fills':[],
              'corporate_ledger':[],'ownership':{}}
        prefix={'trace':{'failed_session':'2025-12-16','days':copy.deepcopy(days),
          'intents':copy.deepcopy(case['intents']),'ownership':{}},
          'state':{'fills':[],'corporate_ledger':[]}}
        self.assertTrue(m.compare_preserved_prefix(case,prefix)['financial_prefix_byte_semantics_identical'])
        for field in ('cash','intent'):
            changed=copy.deepcopy(case)
            if field=='cash':changed['days'][12]['cash']='101'
            else:changed['intents'][1]['snapshot_sha256']='rewritten'
            with self.subTest(field=field),self.assertRaises(ValueError):m.compare_preserved_prefix(changed,prefix)

    def test_unknown_st_preserves_both_real_engine_failure_clocks_without_roi(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            ctx=self.context(m,d);ctx['bars']['SH600001']['2024-01-02']['isST']='1';out=Path(d)/m.OUTPUT
            with patch.object(m,'score_case',side_effect=AssertionError('ROI forbidden')) as score:
                result=m.run_profiles(ctx,out,plan_sha='a'*64)
            score.assert_not_called();self.assertFalse(result['annual_returns_computed'])
            for bps in ('20','40'):
                state=json.loads((out/bps/'failed_account_state.json').read_text())
                trace=json.loads((out/bps/'partial_engine_trace.json').read_text())
                self.assertEqual(state['last_account_clock'],['2023-12-29',1]);self.assertEqual(state['fills'],[])
                self.assertEqual(trace['failed_session'],'2024-01-02');self.assertEqual(len(trace['days']),1)
                self.assertIsNone(trace['following_target']);self.assertNotIn('2024_return_pct',result['results_by_extra_bps'][bps])

    def test_input_postcheck_and_second_score_failure_publish_no_first_roi(self):
        m=self.api()
        for mode in ('mutation','second_score'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                ctx=self.context(m,d);seen=[]
                def completed(*args,**kwargs):
                    seen.append('case')
                    if mode=='mutation':Path(next(iter(ctx['known_hashes']))).write_text('changed')
                    return {}
                def scorer(*args):
                    self.assertEqual(seen,['case','case'])
                    if len(scores):raise ValueError('second fixed profile scoring failed')
                    scores.append(1);return {'2024_return_pct':1,'2025_return_pct':2,'average_exposure_pct':95}
                scores=[]
                with patch.object(m,'validate_completed_case',return_value=([],{})),patch.object(m,'persist_case',return_value={}),patch.object(m,'score_case',side_effect=scorer):
                    result=m.run_profiles(ctx,Path(d)/m.OUTPUT,plan_sha='a'*64,simulator=completed)
                self.assertFalse(result['annual_returns_computed']);self.assertEqual(seen,['case','case'])
                self.assertEqual(len(scores),0 if mode=='mutation' else 1)
                for value in result['results_by_extra_bps'].values():self.assertNotIn('2024_return_pct',value)

    def test_source_preflight_does_not_create_or_run_accounts(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan';p.write_text('{}');out=Path(d)/m.OUTPUT
            args=['--source-root',d,'--plan',str(p),'--expected-plan-sha256',m.file_sha(p),
                  '--output-dir',str(out),'--source-preflight-only']
            with patch.object(m,'load_inputs',return_value={'known_hashes':{}}),patch.object(m,'run_profiles',side_effect=AssertionError('no account')):
                self.assertEqual(m.main(args),0)
            self.assertFalse(out.exists());out.mkdir()
            with patch.object(m,'load_inputs',side_effect=AssertionError('no read')):
                with self.assertRaises(ValueError):m.main(args)


if __name__=='__main__':unittest.main()
