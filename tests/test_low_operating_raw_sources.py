import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
try:
    from scripts import capture_low_operating_raw_pre2026 as source
except ImportError:
    source=None
from tests.test_low_market_residual_vol_raw_capture import SDK,Response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS


class LowOperatingRawSourceTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(source,'low operating follow-up source wrapper missing')

    def test_selection_retains_old_rejection_and_marks_adaptive_known_control(self):
        s=source.selection(Path(__file__).resolve().parents[1])
        self.assertEqual(s['candidate'],'low_operating_profitability_followup_v1');self.assertEqual(s['original_target_family'],'operating_profit_prior_assets_bottom_decile_control')
        self.assertEqual(s['seen_operating_policies'],3);self.assertIsNone(s['original_primary_lead']);self.assertTrue(s['selected_from_seen_development_control'])
        self.assertFalse(s['fresh_independent_hypothesis']);self.assertFalse(s['objective_achieved'])

    def scope(self):
        codes=[f'SH600{n:03d}' for n in range(42)]+['SZ002326']
        return {'status':'FROZEN_LOW_OPERATING_FOLLOWUP_PRE2026_SOURCE_CAPTURE','candidate':'low_operating_profitability_followup_v1',
         'window':['2023-12-29','2025-12-31'],'codes':codes,'reuse_routes':dict.fromkeys(codes[:42],{}),'fresh_codes':['SZ002326'],
         'maximum_new_query_reservations':4,'maximum_administrative_login_attempts':1,'max_attempts_per_query':1,'socket_timeout_seconds':20,
         'baostock_version':'0.9.4','portfolio_returns_permitted':False,'2026_values_permitted':False,'target_family':'operating_profit_prior_assets_bottom_decile_control'}

    def test_scope_cannot_widen_queries_dates_or_promote_original_control_in_place(self):
        r=self.scope();source.validate_scope(r)
        for k,v in [('candidate','high_operating'),('fresh_codes',['SZ002326','SH600999']),('maximum_new_query_reservations',5),('max_attempts_per_query',2),
                    ('maximum_administrative_login_attempts',2),('window',['2023-12-29','2026-01-05']),('portfolio_returns_permitted',True),('2026_values_permitted',True)]:
            c=copy.deepcopy(r);c[k]=v
            with self.subTest(key=k),self.assertRaises(ValueError):source.validate_scope(c)

    def execute_fixture(self,root,sdk,writer=None):
        original=root/'input.json';original.write_text('{"immutable":true}');h=source.sha(original)
        req={'codes':['SZ002326'],'fresh_codes':['SZ002326'],'maximum_new_query_reservations':4,'target_sha256':'a'*64,'reference_calendar_sha256':'b'*64}
        auth={'sessions':['2023-12-29'],'reuse_routes':{},'known_hashes':{str(original):h}}
        out=root/'capture'
        # The unchanged adapter has its own full SDK/schema tests; this layer exercises real output boundaries.
        if writer is None:return source.execute(req,auth,out,sdk,request_bytes=b'{}\n',request_sha=source.hash_bytes(b'{}\n')),out,original
        with patch.object(source,'write_once',side_effect=writer):return source.execute(req,auth,out,sdk,request_bytes=b'{}\n',request_sha=source.hash_bytes(b'{}\n')),out,original

    def test_complete_capture_keeps_adapter_origin_and_followup_identity(self):
        with tempfile.TemporaryDirectory() as t:
            result,out,_=self.execute_fixture(Path(t),SDK())
            self.assertTrue(result['complete']);self.assertEqual(result['candidate'],'low_operating_profitability_followup_v1')
            self.assertEqual(source.read(out/'manifest.json')['status'],'LOW_MARKET_RESIDUAL_VOL1M_RAW_SOURCES_CAPTURED_ADMISSION_SEPARATE')
            self.assertEqual(source.read(out/'followup-terminal.json'),result);self.assertFalse(result['portfolio_return_computed'])
            self.assertEqual(len(list(out.rglob('reserved-*.json'))),4)

    def test_sdk_failure_or_interruption_remains_incomplete_without_retry(self):
        for sdk in (SDK(bad=True),SDK(interrupt=True),SDK(logout='1')):
            with tempfile.TemporaryDirectory() as t:
                result,out,_=self.execute_fixture(Path(t),sdk)
                self.assertFalse(result['complete']);self.assertLessEqual(len(list(out.rglob('reserved-*.json'))),4)
                self.assertEqual(sum(c[0]=='login' for c in sdk.calls),1)
                self.assertTrue((out/'manifest.json').exists())

    def test_new_sdk_future_corporate_metadata_fails_with_all_evidence_retained(self):
        for operate_date in ('','2025-05-10'):
            class FutureSDK(SDK):
                def query_dividend_data(self,code,**kw):
                    original=super().query_dividend_data(code,**kw)
                    if str(kw['year'])!='2025':return original
                    row=dict.fromkeys(DIVIDEND_FIELDS,'')
                    row.update(code=code,dividOperateDate=operate_date,dividPlanDate='2026-01-05',
                               dividCashPsBeforeTax='.2',dividStocksPs='0',dividReserveToStockPs='0')
                    return Response(DIVIDEND_FIELDS,[[row[k] for k in DIVIDEND_FIELDS]])
            with self.subTest(operate_date=operate_date),tempfile.TemporaryDirectory() as t:
                root=Path(t);sdk=FutureSDK()
                with self.assertRaisesRegex(ValueError,'corporate/quarantine dates'):
                    self.execute_fixture(root,sdk)
                out=root/'capture';terminal=source.read(out/'followup-terminal.json')
                self.assertFalse(terminal['complete']);self.assertTrue(terminal['all_inputs_unchanged'])
                self.assertEqual(terminal['candidate'],source.CANDIDATE)
                self.assertFalse(terminal['portfolio_return_computed'])
                self.assertEqual(terminal['original_error']['type'],'ValueError')
                packet=source.read(out/'codes/SZ002326.json')
                self.assertEqual(len(packet['quarantine'] if not operate_date else packet['distributions']),1)
                self.assertEqual(len(list(out.rglob('reserved-*.json'))),4)
                self.assertEqual(len(list(out.rglob('response-*.json'))),4)
                self.assertEqual(sum(c[0]=='login' for c in sdk.calls),1)

    def test_outer_terminal_stage_input_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);writer=source.write_once
            def write(path,value):
                if path.name=='.followup-terminal-pending.json':(root/'input.json').write_text('changed during outer persistence')
                writer(path,value)
            with self.assertRaises(ValueError):self.execute_fixture(root,SDK(),write)
            result=source.read(root/'capture/followup-terminal.json');self.assertFalse(result['complete']);self.assertFalse(result['all_inputs_unchanged'])

    def test_every_overlap_action_or_calendar_conflict_remains_a_rejection(self):
        good={'directory':'a','packet_sha256':'1','fingerprint':'same','complete_calendar':True}
        self.assertEqual(source.choose_route([good,{**good,'directory':'b'}]),good)
        for bad in ({**good,'fingerprint':'changed_action'},{**good,'complete_calendar':False}):
            with self.assertRaises(ValueError):source.choose_route([good,bad])

    def test_quarantined_future_notice_date_cannot_escape_the_source_cutoff(self):
        p={'instrument':'SZ002326','window':['2023-12-29','2025-12-31'],'bars':[],'distributions':[],'adjustments':[],
           'quarantine':[{'reason':'MISSING_OPERATE_DATE','record':{'dividOperateDate':'','dividPlanDate':'2026-01-05'}}]}
        with self.assertRaises(ValueError):source.source_fingerprint(p)
