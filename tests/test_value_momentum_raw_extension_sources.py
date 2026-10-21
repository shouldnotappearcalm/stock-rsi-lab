import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from scripts.fundamental_query_journal import QueryJournal
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS
try:
    from scripts import value_momentum_raw_extension_sources as subject
except ImportError:
    subject = None

CODE='SZ000001'
DAYS=['2023-12-29','2025-12-31','2026-10-16','2026-10-19','2026-10-20']
def bar(day,code=CODE):
    return dict(zip(BAR_FIELDS,[day,code[:2].lower()+'.'+code[2:],'10','11','9','10','10','1000','10000','3','1','0']))
def packet(days= DAYS,code=CODE):
    return {'instrument':code,'window':['2023-12-29','2026-10-20'],'bars':[bar(d,code) for d in days],
            'distributions':[],'adjustments':[],'quarantine':[]}
def prefix(code=CODE):
    p=packet(DAYS[:2],code);p['window'][1]='2025-12-31';return p
def envelope(fields,rows):
    return ['provider_response'],[{'initial_error_code':'0','initial_error_msg':'ok','fields':list(fields),'rows':rows,
          'iteration_error_type':None,'iteration_error':None,'final_error_code':'0','final_error_msg':'ok'}]

class ExtensionTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(subject,'new independent extension module required')
    def test_partition_budget_uses_each_baseline_and_does_not_reuse_old_76_limit(self):
        codes=[f'SZ000{i:03d}' for i in range(1,128)]
        full=dict.fromkeys(codes[:15]);baseline=dict.fromkeys(codes[:114])
        route=subject.partition(codes,baseline,full)
        self.assertEqual((len(route['incremental']),len(route['cold']),route['budget']),(99,13,362))
        with self.assertRaises(ValueError):subject.partition(codes,{}, {})
    def test_original_prefix_preserved_and_conflicting_common_core_or_events_rejected(self):
        old=prefix();old['provenance']={'immutable':'old'};before=copy.deepcopy(old)
        source=packet(DAYS[2:]);source['window'][0]='2026-01-01'
        cache=packet(DAYS[:3]);cache['window'][1]='2026-10-16'
        actual=subject.compose_packet(CODE,source,old,DAYS,caches=[cache])
        self.assertEqual(actual['bars'][:2],old['bars']);self.assertEqual(old,before)
        bad=copy.deepcopy(cache);bad['bars'][-1]['close']='10.01'
        with self.assertRaises(ValueError):subject.compose_packet(CODE,source,old,DAYS,caches=[bad])
        bad=copy.deepcopy(cache);bad['adjustments']=[{'code':'sz.000001','dividOperateDate':'2025-06-01','foreAdjustFactor':'1','backAdjustFactor':'1','adjustFactor':'1'}]
        with self.assertRaises(ValueError):subject.compose_packet(CODE,source,old,DAYS,caches=[bad])
    def test_only_bound_listing_allows_missing_prelisting_and_never_synthesizes_rows(self):
        days=['2023-12-29','2024-04-01','2024-04-02','2026-10-20']
        src=packet(days[2:], 'SZ001389')
        with self.assertRaises(ValueError):subject.compose_packet('SZ001389',src,None,days)
        result=subject.compose_packet('SZ001389',src,None,days,listed_on='2024-04-02')
        self.assertEqual([r['date'] for r in result['bars']],days[2:])
        with self.assertRaises(ValueError):subject.compose_packet('SZ000001',packet(days[2:]),None,days,listed_on='2024-04-02')
    def test_future_daily_retained_in_journal_but_rejected_before_further_queries(self):
        calls=[]
        def fetch(c,k,p):calls.append(k);return envelope(BAR_FIELDS,[list(bar('2026-10-21').values())])
        with tempfile.TemporaryDirectory() as d:
            j=QueryJournal(d,max_queries=3,max_attempts=1)
            with self.assertRaises(ValueError):subject.fetch_packet(j,CODE,'frozen',fetch,prefix())
            self.assertEqual(calls,['daily']);self.assertIn('2026-10-21',next(Path(d).rglob('response-1.json')).read_text())
    def test_future_dividend_quarantined_before_amount_interpretation_and_exact_three_queries(self):
        calls=[];future=dict.fromkeys(DIVIDEND_FIELDS,'');future.update(code='sz.000001',dividOperateDate='2026-11-01',dividCashPsBeforeTax='UNREADABLE_FUTURE')
        def fetch(c,k,p):
            calls.append((k,p))
            if k=='daily':return envelope(BAR_FIELDS,[list(bar(d).values()) for d in DAYS[2:]])
            if k=='dividend2026':return envelope(DIVIDEND_FIELDS,[[future[k] for k in DIVIDEND_FIELDS]])
            return envelope(ADJUST_FIELDS,[])
        with tempfile.TemporaryDirectory() as d:
            v=subject.fetch_packet(QueryJournal(d,max_queries=3,max_attempts=1),CODE,'frozen',fetch,prefix())
            self.assertEqual(v['distributions'],[]);self.assertEqual(v['quarantine'][0]['record'],future)
            self.assertEqual([c for c,p in calls],['daily','dividend2026','adjustments']);self.assertEqual(calls[0][1]['end_date'],'2026-10-20')
    def test_three_failures_stop_and_output_is_never_resumed(self):
        codes=['SZ000001','SZ000002','SZ000003','SZ000004'];calls=[]
        def fail(c,k,p):calls.append(c);raise ConnectionError('offline disconnect')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'capture'
            m=subject.capture_packets(out,codes,DAYS,{c:prefix(c) for c in codes},{},'frozen',fail)
            self.assertEqual(len(m['errors_sha256']),3);self.assertEqual(m['pending_codes'],['SZ000004'])
            self.assertEqual(m['query_reservations_consumed'],3);self.assertTrue((out/'stopped.json').exists())
            with self.assertRaises(ValueError):subject.capture_packets(out,codes,DAYS,{}, {},'frozen',fail)
            self.assertEqual(len(calls),3)
    def test_failed_login_is_one_attempt_and_cleanup_runs_once(self):
        class SDK:
            def __init__(self):self.logins=self.logouts=0
            def login(self):self.logins+=1;return SimpleNamespace(error_code='1',error_msg='offline')
            def logout(self):self.logouts+=1;return SimpleNamespace(error_code='0',error_msg='ok')
        with tempfile.TemporaryDirectory() as d:
            sdk=SDK();session=subject.SourceSession(d,'frozen',sdk)
            for _ in range(3):
                with self.assertRaises(RuntimeError):session(CODE,'daily',{})
            session.close();session.close()
            self.assertEqual((sdk.logins,sdk.logouts),(1,1));self.assertTrue((Path(d)/'cleanup.json').exists())
            self.assertEqual(json.loads((Path(d)/'login-response-1.json').read_text()).get('error_code'),'1')
    def test_partial_success_preserved_with_failed_later_code(self):
        codes=[CODE,'SZ000002']
        def fetch(c,k,p):
            if c!=CODE:raise OSError('offline')
            if k=='daily':return envelope(BAR_FIELDS,[list(bar(d).values()) for d in DAYS[2:]])
            return envelope(ADJUST_FIELDS if k=='adjustments' else DIVIDEND_FIELDS,[])
        with tempfile.TemporaryDirectory() as d:
            m=subject.capture_packets(Path(d)/'capture',codes,DAYS,{c:prefix(c) for c in codes},{},'frozen',fetch)
            self.assertEqual(m['names'],1);self.assertEqual(m['query_reservations_consumed'],4)
            self.assertEqual(set(m['errors_sha256']),{'SZ000002'});self.assertFalse(m['admitted_for_account_replay'])

    def test_overlap_compares_only_shared_window_and_rejects_left_duplicate_dates(self):
        old=prefix();cache=packet();r=dict.fromkeys(DIVIDEND_FIELDS,'');r.update(code='sz.000001',dividOperateDate='2026-06-01',dividCashPsBeforeTax='.1')
        cache['distributions']=[r]
        try:subject.verify_overlap(old,cache)
        except ValueError as exc:self.fail(str(exc))
        changed=copy.deepcopy(old);changed['bars'].append(copy.deepcopy(changed['bars'][-1]))
        with self.assertRaises(ValueError):subject.verify_overlap(changed,cache)
    def test_cold_name_uses_five_window_bound_queries(self):
        calls=[]
        def fetch(c,k,p):
            calls.append((k,p))
            return envelope(BAR_FIELDS,[list(bar(d).values()) for d in DAYS]) if k=='daily' else envelope(ADJUST_FIELDS if k=='adjustments' else DIVIDEND_FIELDS,[])
        with tempfile.TemporaryDirectory() as d:
            v=subject.fetch_packet(QueryJournal(d,max_queries=5,max_attempts=1),CODE,'frozen',fetch,None)
            self.assertEqual([c for c,p in calls],['daily','dividend2024','dividend2025','dividend2026','adjustments'])
            self.assertEqual(calls[0][1]['start_date'],'2023-12-29');self.assertEqual(v['bars'][-1]['date'],'2026-10-20')
    def test_missing_postlisting_or_end_session_is_retained_error_not_completed_packet(self):
        def fetch(c,k,p):
            if k=='daily':return envelope(BAR_FIELDS,[list(bar(d).values()) for d in DAYS[2:-1]])
            return envelope(ADJUST_FIELDS if k=='adjustments' else DIVIDEND_FIELDS,[])
        with tempfile.TemporaryDirectory() as d:
            m=subject.capture_packets(Path(d)/'out',[CODE],DAYS,{CODE:prefix()},{},'frozen',fetch)
            self.assertEqual(m['names'],0);self.assertEqual(m['query_reservations_consumed'],3);self.assertIn(CODE,m['errors_sha256'])
    def test_hard_interruption_preserves_consumed_unknown_attempt_and_pending(self):
        def interrupted(c,k,p):raise KeyboardInterrupt('synthetic interruption')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out'
            with self.assertRaises(KeyboardInterrupt):subject.capture_packets(out,[CODE],DAYS,{CODE:prefix()},{},'frozen',interrupted)
            m=json.loads((out/'manifest.json').read_text());self.assertEqual(m['pending_codes'],[CODE]);self.assertEqual(m['query_reservations_consumed'],1)
            self.assertEqual(m['abnormal_exit']['error_type'],'KeyboardInterrupt');self.assertFalse(list(out.rglob('response-1.json')))

    def test_full_cache_never_queries_and_keeps_exact_old_prefix_and_lineage(self):
        old=prefix();cache=packet();cache['bars'][0]['close']='10.000';cache['provenance']={'kind':'ancestor'};cache['source_query_receipts']={'daily':{'sha':'old-response'}}
        def forbidden(*args):self.fail('full cache caused a provider call')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out';m=subject.capture_packets(out,[CODE],DAYS,{CODE:old},{CODE:cache},'frozen',forbidden,lineage={CODE:{'source_sha':'bound-original'}})
            self.assertEqual(m['query_reservations_consumed'],0);v=json.loads((out/'codes'/ (CODE+'.json')).read_text())
            self.assertEqual(v['bars'][:2],old['bars']);self.assertEqual(v['provenance']['source_provenance'],{'kind':'ancestor'})
            self.assertEqual(v['provenance']['source_query_receipts']['daily']['sha'],'old-response')
            self.assertEqual(v['provenance']['registered_source_lineage'],{'source_sha':'bound-original'})

class CaptureEntryTests(unittest.TestCase):
    def test_existing_output_refuses_before_request_reads_or_sdk_import(self):
        try:
            from scripts.capture_value_momentum_raw_extension import main
        except ImportError:
            self.fail('new guarded capture entry required')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'keep';out.mkdir();marker=out/'original';marker.write_text('immutable')
            with self.assertRaisesRegex(ValueError,'existing'):
                main(['--source-root',d,'--request',str(Path(d)/'absent.json'),
                      '--expected-request-sha256','unused','--output-dir',str(out),'--preflight-only'])
            self.assertEqual(marker.read_text(),'immutable')

    def test_postcapture_authentication_failure_is_persisted_not_claimed_unchanged(self):
        from scripts import capture_value_momentum_raw_extension as entry
        self.assertTrue(hasattr(entry,'verify_postcapture'),'postcapture input verification required')
        with tempfile.TemporaryDirectory() as d:
            def changed():raise ValueError('original packet changed')
            record=entry.verify_postcapture(Path(d),changed)
            self.assertFalse(record['source_inputs_unchanged_after_capture'])
            self.assertEqual(record['error_type'],'ValueError')
            self.assertEqual(json.loads((Path(d)/'source-postcheck.json').read_text()),record)
