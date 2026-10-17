import json
from pathlib import Path
import tempfile
import unittest

try:
    from scripts.fundamental_query_journal import QueryJournal, write_packet_once
except ImportError:
    QueryJournal = write_packet_once = None


class FundamentalJournalTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(QueryJournal, 'per-query source journal missing')

    def test_response_reused_after_restart_without_another_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            fetch = lambda: (calls.append(1) or (['code'], [['sh.600166']]))
            first = QueryJournal(tmp, max_queries=2).query({'method': 'profit', 'quarter': 1}, fetch)
            second = QueryJournal(tmp, max_queries=2).query({'method': 'profit', 'quarter': 1}, fetch)
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(list(Path(tmp).rglob('reserved-*.json'))), 1)

    def test_interrupted_request_consumes_budget_and_never_overwrites_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            def interrupted(): raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                QueryJournal(tmp, max_queries=1).query({'method': 'profit'}, interrupted)
            reservation = next(Path(tmp).rglob('reserved-*.json')); before = reservation.read_bytes()
            def forbidden(): self.fail('consumed request budget was reused')
            with self.assertRaises(ValueError):
                QueryJournal(tmp, max_queries=1).query({'method': 'profit'}, forbidden)
            self.assertEqual(reservation.read_bytes(), before)

    def test_interrupted_then_retried_request_keeps_both_attempts_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            def interrupted(): raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                QueryJournal(tmp, max_queries=2).query({'method': 'profit'}, interrupted)
            journal = QueryJournal(tmp, max_queries=2)
            data, receipt = journal.query({'method': 'profit'}, lambda: (['x'], [['1']]))
            self.assertEqual(data['rows'], [['1']])
            self.assertEqual(len(list(Path(tmp).rglob('reserved-*.json'))), 2)
            response = Path(tmp)/receipt['response_file']
            changed = json.loads(response.read_text()); changed['payload']['rows'] = [['2']]
            response.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                journal.query({'method': 'profit'}, lambda: self.fail('tamper caused a new query'))

    def test_completed_unregistered_packet_can_be_adopted_but_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'code.json'
            write_packet_once(path, {'raw': 'original'})
            before = path.read_bytes()
            write_packet_once(path, {'raw': 'original'})
            with self.assertRaises(ValueError): write_packet_once(path, {'raw': 'replacement'})
            self.assertEqual(path.read_bytes(), before)

    def test_partial_stock_capture_keeps_completed_request_when_later_query_interrupts(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = QueryJournal(tmp, max_queries=3)
            daily, receipt = journal.query({'kind': 'daily'}, lambda: (['price'], [['10']]))
            before = (Path(tmp)/receipt['response_file']).read_bytes()
            def interrupted(): raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt): journal.query({'kind': 'quarter'}, interrupted)
            restarted = QueryJournal(tmp, max_queries=3)
            cached, _ = restarted.query({'kind': 'daily'}, lambda: self.fail('completed daily query repeated'))
            restarted.query({'kind': 'quarter'}, lambda: (['profit'], [['100']]))
            self.assertEqual(cached, daily)
            self.assertEqual((Path(tmp)/receipt['response_file']).read_bytes(), before)
            self.assertEqual(len(list(Path(tmp).rglob('reserved-*.json'))), 3)
