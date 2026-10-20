import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS
from scripts.fundamental_query_journal import QueryJournal, file_sha
try:
    from scripts.capture_budgeted_residual_raw_pre2026 import load_reuse_packet, fetch_packet
except ImportError:
    load_reuse_packet = fetch_packet = None


def envelope(fields, rows):
    return ['provider_response'], [{'initial_error_code': '0', 'initial_error_msg': 'success',
        'fields': list(fields), 'rows': rows, 'iteration_error_type': None, 'iteration_error': None,
        'final_error_code': '0', 'final_error_msg': 'success'}]


def bar(day='2024-01-02'):
    return [day, 'sh.600001', '10', '11', '9', '10', '10', '10000', '100000', '3', '1', '0']


class BudgetedRawCaptureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(load_reuse_packet)
        self.assertIsNotNone(fetch_packet)

    def test_four_bounded_queries_produce_replayable_original_responses(self):
        calls=[]
        def fetch(component, parameters):
            calls.append((component, parameters))
            fields,rows=(BAR_FIELDS,[bar()]) if component=='daily' else (ADJUST_FIELDS,[]) if component=='adjustments' else (DIVIDEND_FIELDS,[])
            return envelope(fields,rows)
        with tempfile.TemporaryDirectory() as d:
            journal=QueryJournal(d,max_queries=4,max_attempts=1)
            packet=fetch_packet(journal,'SH600001','frozen',fetch)
            self.assertEqual(packet['bars'][0]['close'],'10')
            self.assertEqual(len(packet['source_query_receipts']),4)
            self.assertEqual(len(list(Path(d).rglob('reserved-1.json'))),4)
            again=fetch_packet(journal,'SH600001','frozen',fetch)
            self.assertEqual(packet,again)
            self.assertEqual(len(calls),4)
            self.assertEqual([c for c,_ in calls],['daily','dividend2024','dividend2025','adjustments'])
            self.assertTrue(all(p.get('end_date','2025-12-31')=='2025-12-31' for _,p in calls))
            self.assertEqual([p['year'] for c,p in calls if c.startswith('dividend')],['2024','2025'])

    def test_provider_future_row_is_retained_but_rejected_without_more_calls(self):
        calls=[]
        def fetch(component, parameters):
            calls.append(component)
            return envelope(BAR_FIELDS,[bar('2026-01-05')])
        with tempfile.TemporaryDirectory() as d:
            journal=QueryJournal(d,max_queries=4,max_attempts=1)
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'development cutoff'):
                    fetch_packet(journal,'SH600001','frozen',fetch)
            self.assertEqual(calls,['daily'])
            saved=json.loads(next(Path(d).rglob('response-1.json')).read_text())
            self.assertEqual(saved['payload']['rows'][0]['rows'][0][0],'2026-01-05')

    def test_reuse_keeps_incomplete_calendar_and_original_bytes(self):
        packet={'instrument':'SH600001','window':['2023-12-29','2025-12-31'],
            'bars':[dict(zip(BAR_FIELDS,bar()))],'distributions':[],'adjustments':[],'quarantine':[]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'SH600001.json';p.write_text(json.dumps(packet));data=p.read_bytes()
            result,diagnostic=load_reuse_packet(p,'SH600001',file_sha(p),['2023-12-29','2024-01-02'])
            self.assertEqual(result,packet)
            self.assertEqual(diagnostic['missing_sessions'],['2023-12-29'])
            self.assertFalse(diagnostic['missing_sessions_classified_as_prelisting'])
            self.assertEqual(p.read_bytes(),data)

    def test_reuse_rejects_tampered_or_later_window_instead_of_clipping(self):
        base={'instrument':'SH600001','window':['2023-12-29','2025-12-31'],
            'bars':[dict(zip(BAR_FIELDS,bar()))],'distributions':[],'adjustments':[],'quarantine':[]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'SH600001.json';p.write_text(json.dumps(base));h=file_sha(p)
            for change in ({'window':['2023-12-29','2026-10-16']},{'instrument':'SH600002'},
                           {'bars':[dict(zip(BAR_FIELDS,bar('2026-01-05')))]}):
                v=copy.deepcopy(base);v.update(change);p.write_text(json.dumps(v))
                with self.assertRaises(ValueError):load_reuse_packet(p,'SH600001',file_sha(p),['2024-01-02'])
            with self.assertRaisesRegex(ValueError,'checksum'):
                load_reuse_packet(p,'SH600001',h,['2024-01-02'])

    def test_transport_failure_consumes_one_attempt_and_survives_restart(self):
        calls=[]
        def fetch(component,parameters):calls.append(1);raise ConnectionError('synthetic disconnect')
        with tempfile.TemporaryDirectory() as d:
            for _ in range(2):
                with self.assertRaises(ValueError):
                    fetch_packet(QueryJournal(d,max_queries=4,max_attempts=1),'SH600001','frozen',fetch)
            self.assertEqual(len(calls),1)
            response=json.loads(next(Path(d).rglob('response-1.json')).read_text())
            self.assertEqual(response['status'],'SOURCE_ERROR')
            self.assertEqual(response['error_type'],'ConnectionError')
