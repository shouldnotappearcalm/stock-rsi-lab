import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import capture_low_operating_lifecycle_sources_pre2026 as source
    from scripts import audit_low_operating_lifecycle_sources_pre2026 as audit
except ImportError:
    source=audit=None
from tests.test_low_market_residual_vol_raw_capture import SDK,Response
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS
from stock_rsi.lifecycle_source_rows import source_rows_on


SESSIONS=['2023-12-29','2024-08-30','2024-09-02']
def packet(code,days):
    symbol=code[:2].lower()+'.'+code[2:]
    return {'instrument':code,'window':['2023-12-29','2025-12-31'],
            'bars':[dict(zip(BAR_FIELDS,[day,symbol,'10','11','9','10','10','10000','100000','3','1','0'])) for day in days],
            'distributions':[],'adjustments':[],'quarantine':[]}


class FullSDK(SDK):
    def query_history_k_data_plus(self,code,fields,**kw):
        original=super().query_history_k_data_plus(code,fields,**kw)
        return Response(BAR_FIELDS,[[r[k] for k in BAR_FIELDS] for r in packet(code[:2].upper()+code[3:],SESSIONS)['bars']])


class LowOperatingLifecycleSourceTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(source,'new lifecycle source wrapper missing');self.assertIsNotNone(audit)

    def test_original_public_evidence_hash_and_exact_primary_literal_are_bound(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(source.sha(root/source.LIFE),source.LIFE_SHA)
        good={'instrument':'SZ002505','day':'2024-08-30','file':Path(source.PDF).name,'sha256':source.PDF_SHA}
        source.validate_primary(source.BOUNDARIES['SZ002505'],good)
        for key,value in (('instrument','SZ002326'),('day','2024-08-29'),('sha256','0'*64),('file','missing.pdf')):
            with self.subTest(key=key),self.assertRaises(ValueError):source.validate_primary(source.BOUNDARIES['SZ002505'],{**good,key:value})

    def test_scope_cannot_expand_queries_issuer_dates_or_allow_returns(self):
        codes=[f'SH600{n:03d}' for n in range(41)]+['SZ002505','SZ002326']
        r={'status':source.STATUS,'candidate':source.CANDIDATE,'target_family':source.FAMILY,'window':[source.START,source.END],
           'codes':codes,'reuse_routes':dict.fromkeys(codes[:-1],{}),'fresh_codes':['SZ002326'],'boundaries':source.BOUNDARIES,
           'maximum_new_query_reservations':4,'maximum_administrative_login_attempts':1,'max_attempts_per_query':1,
           'socket_timeout_seconds':20,'baostock_version':'0.9.4','portfolio_returns_permitted':False,'2026_values_permitted':False}
        source.validate_scope(r)
        for key,value in (('maximum_new_query_reservations',5),('fresh_codes',['SZ002326','SH600000']),('boundaries',{}),
                          ('window',['2023-12-29','2026-01-05']),('portfolio_returns_permitted',True),('2026_values_permitted',True)):
            with self.subTest(key=key),self.assertRaises(ValueError):source.validate_scope({**r,key:value})

    def test_only_exact_primary_tail_is_classified_without_synthetic_prices(self):
        p=packet('SZ002505',SESSIONS[:2]);before=copy.deepcopy(p)
        c=source.coverage(p,SESSIONS,source.BOUNDARIES)
        self.assertFalse(c['full_explicit_calendar_covered']);self.assertTrue(c['source_coverage_explained'])
        self.assertEqual(c['missing_sessions'],['2024-09-02']);self.assertEqual(len(c['lifecycle_intervals']),2)
        self.assertTrue(c['lifecycle_intervals'][0]['original_row_present']);self.assertEqual(p,before)
        self.assertFalse(c['actual_flat_inventory_proven'])

    def test_interior_gap_other_issuer_unexpected_post_boundary_row_and_wrong_proof_fail(self):
        for p in (packet('SZ002505',SESSIONS[1:2]),packet('SZ002326',SESSIONS[:2]),packet('SZ002505',SESSIONS)):
            with self.subTest(code=p['instrument'],days=len(p['bars'])),self.assertRaises(ValueError):source.coverage(p,SESSIONS,source.BOUNDARIES)
        for override in ({'verified_primary_boundary':False},{'effective_date':'2024-09-02'},{'primary_document_sha256':'0'*64}):
            bad=copy.deepcopy(source.BOUNDARIES);bad['SZ002505'].update(override)
            with self.assertRaises(ValueError):source.coverage(packet('SZ002505',SESSIONS[:2]),SESSIONS,bad)

    def test_existing_evaluator_guard_still_rejects_any_required_inventory_order_or_price(self):
        p=packet('SZ002505',SESSIONS[:2]);bars={'SZ002505':{r['date']:r for r in p['bars']}}
        for day in SESSIONS[1:]:
            with self.assertRaisesRegex(ValueError,'still requires'):source_rows_on(bars,date.fromisoformat(day),{'SZ002505'},source.BOUNDARIES)

    def fixture(self,root,sdk,writer=None):
        original=root/'input.json';original.write_text('{"immutable":true}');origin=root/'original.json'
        source.write_once(origin,packet('SZ002505',SESSIONS[:2]))
        req={'codes':['SZ002505','SZ002326'],'fresh_codes':['SZ002326'],'maximum_new_query_reservations':4,
             'target_sha256':'a'*64,'reference_calendar_sha256':'b'*64}
        auth={'sessions':SESSIONS,'boundaries':source.BOUNDARIES,'reuse_routes':{'SZ002505':{'path':str(origin),'packet_sha256':source.sha(origin)}},
              'known_hashes':{str(p):source.sha(p) for p in (original,origin)}}
        kw={'request_bytes':b'{}\n','request_sha':source.hash_bytes(b'{}\n')}
        if writer is None:return source.execute(req,auth,root/'capture',sdk,**kw)
        with patch.object(source,'write_once',side_effect=writer):return source.execute(req,auth,root/'capture',sdk,**kw)

    def test_success_keeps_partial_source_manifest_and_new_identity_without_account_admission(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);sdk=FullSDK();r=self.fixture(root,sdk);out=root/'capture'
            self.assertTrue(r['complete']);self.assertFalse(source.read(out/'manifest.json')['all_source_calendars_complete'])
            self.assertFalse(r['physical_account_admitted']);self.assertFalse(r['portfolio_return_computed'])
            self.assertEqual(source.read(out/'followup-terminal.json'),r)
            self.assertEqual((out/'codes/SZ002505.json').read_bytes(),(root/'original.json').read_bytes())
            self.assertEqual(len(list(out.rglob('reserved-*.json'))),4)

    def test_sdk_error_logout_or_interruption_never_completes_or_retries(self):
        for sdk in (FullSDK(bad=True),FullSDK(interrupt=True),FullSDK(logout='1')):
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);r=self.fixture(root,sdk);self.assertFalse(r['complete'])
                self.assertEqual(sum(x[0]=='login' for x in sdk.calls),1)
                self.assertTrue((root/'capture/codes/SZ002505.json').exists())
                self.assertLessEqual(len(list((root/'capture').rglob('reserved-*.json'))),4)

    def test_future_quarantine_from_new_sdk_fails_and_retains_all_four_responses(self):
        class FutureSDK(FullSDK):
            def query_dividend_data(self,code,**kw):
                original=super().query_dividend_data(code,**kw)
                if kw['year']!='2025':return original
                row=dict.fromkeys(DIVIDEND_FIELDS,'');row.update(code=code,dividPlanDate='2026-01-05')
                return Response(DIVIDEND_FIELDS,[[row[k] for k in DIVIDEND_FIELDS]])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaises(ValueError):self.fixture(root,FutureSDK())
            out=root/'capture';self.assertFalse(source.read(out/'followup-terminal.json')['complete'])
            self.assertEqual(len(list(out.rglob('response-*.json'))),4)
            self.assertEqual(len(source.read(out/'codes/SZ002326.json')['quarantine']),1)

    def test_terminal_stage_input_mutation_fails_and_retains_failed_terminal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);real=source.write_once
            def write(p,v):
                if p.name=='.followup-terminal-pending.json':(root/'input.json').write_text('changed')
                real(p,v)
            with self.assertRaises(ValueError):self.fixture(root,FullSDK(),write)
            r=source.read(root/'capture/followup-terminal.json');self.assertFalse(r['complete']);self.assertFalse(r['all_inputs_unchanged'])

    def test_checker_independently_preserves_ST_noncash_and_lifecycle_limit(self):
        p=packet('SZ002505',SESSIONS[:2]);p['bars'][0]['isST']='1'
        row=dict.fromkeys(DIVIDEND_FIELDS,'');row.update(code='sz.002505',dividOperateDate='2024-06-10',
            dividCashPsBeforeTax='0',dividStocksPs='.1',dividReserveToStockPs='0');p['distributions']=[row]
        r=audit.source_risk(p,'SZ002505',SESSIONS,source.BOUNDARIES)
        self.assertEqual(len(r['nonordinary_or_suspended_source_rows']),1)
        self.assertEqual(len(r['noncash_distributions_requiring_primary_review']),1)
        self.assertEqual(r['lifecycle_coverage']['missing_sessions'],['2024-09-02'])
        self.assertFalse(r['physical_account_admitted'])
        for bad in (packet('SZ002505',SESSIONS[1:2]),packet('SZ002326',SESSIONS[:2])):
            with self.assertRaises(ValueError):audit.source_risk(bad,bad['instrument'],SESSIONS,source.BOUNDARIES)
