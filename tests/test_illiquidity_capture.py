import json
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.capture_illiquidity_raw_development import preserve_response,calendar_diagnostic,read_vendor_response,unwrap_vendor_response
except ImportError:preserve_response=calendar_diagnostic=read_vendor_response=unwrap_vendor_response=None
from scripts.fundamental_query_journal import QueryJournal


class IlliquidityCaptureTests(unittest.TestCase):
    def test_response_survives_failed_validation_and_restart_does_not_requery(self):
        self.assertIsNotNone(preserve_response)
        with tempfile.TemporaryDirectory() as d:
            journal=QueryJournal(d,max_queries=1,max_attempts=1);calls=[]
            def fetch():calls.append(1);return ['date'],[['2024-03-01']]
            def reject(payload):raise ValueError('missing required baseline')
            with self.assertRaisesRegex(ValueError,'required baseline'):
                preserve_response(journal,{'instrument':'SH603341','end':'2025-12-31'},fetch,reject)
            saved=list(Path(d).rglob('response-1.json'));self.assertEqual(len(saved),1)
            self.assertEqual(json.loads(saved[0].read_text())['payload']['rows'],[['2024-03-01']])
            journal=QueryJournal(d,max_queries=1,max_attempts=1)
            result,receipt=preserve_response(journal,{'instrument':'SH603341','end':'2025-12-31'},fetch,lambda p:p['rows'])
            self.assertEqual(result,[['2024-03-01']]);self.assertEqual(len(calls),1)

    def test_incomplete_calendar_is_reported_without_inventing_rows_or_listing_status(self):
        self.assertIsNotNone(calendar_diagnostic)
        rows=[{'date':'2024-03-01'},{'date':'2024-03-04'}]
        diagnostic=calendar_diagnostic(rows,['2023-12-29','2024-03-01','2024-03-04'])
        self.assertFalse(diagnostic['full_explicit_calendar_covered'])
        self.assertEqual(diagnostic['missing_sessions'],['2023-12-29'])
        self.assertEqual(rows,[{'date':'2024-03-01'},{'date':'2024-03-04'}])
        self.assertFalse(diagnostic['missing_sessions_classified_as_prelisting'])
        self.assertTrue(calendar_diagnostic(rows,['2024-03-01','2024-03-04'])['full_explicit_calendar_covered'])
        with self.assertRaises(ValueError):calendar_diagnostic(rows+rows,['2024-03-01','2024-03-04'])
        with self.assertRaises(ValueError):calendar_diagnostic([{'date':'2026-01-05'}],['2024-03-01'])

    def test_protocol_error_retains_vendor_fields_codes_and_partial_rows_before_rejection(self):
        self.assertIsNotNone(read_vendor_response)
        class Response:
            fields=['date'];error_code='0';error_msg='success';calls=0
            def next(self):
                self.calls+=1
                if self.calls==1:return True
                self.error_code='10001';self.error_msg='truncated';return False
            def get_row_data(self):return ['2024-03-01']
        with tempfile.TemporaryDirectory() as d:
            journal=QueryJournal(d,max_queries=1,max_attempts=1);response=Response()
            with self.assertRaisesRegex(RuntimeError,'provider response'):
                preserve_response(journal,{'id':'partial'},lambda:read_vendor_response(response),unwrap_vendor_response)
            record=json.loads(next(Path(d).rglob('response-1.json')).read_text())['payload']['rows'][0]
            self.assertEqual(record['fields'],['date']);self.assertEqual(record['rows'],[['2024-03-01']])
            self.assertEqual(record['initial_error_code'],'0');self.assertEqual(record['final_error_code'],'10001')
        response=Response();response.error_code='2000';response.error_msg='initial error';response.fields=None
        fields,rows=read_vendor_response(response)
        self.assertEqual(rows[0]['initial_error_code'],'2000');self.assertEqual(response.calls,0)
        self.assertIsNone(rows[0]['fields'])
        with self.assertRaises(RuntimeError):unwrap_vendor_response({'fields':fields,'rows':rows})
