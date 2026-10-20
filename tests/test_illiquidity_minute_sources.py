import unittest
from scripts.fundamental_query_journal import QueryJournal
try:
    from scripts.illiquidity_minute_sources import prefix_minute_requirements,query_minute_packet
except ImportError:
    prefix_minute_requirements=query_minute_packet=None


class IlliquidityMinuteSourceTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(prefix_minute_requirements)

    def test_fixed_seen_prefix_uses_source_status_and_primary_boundaries_without_deleting_targets(self):
        targets={'2024-06-03':{'as_of':'2024-05-31','weights':{'A':'.95'}},
                 '2024-07-01':{'as_of':'2024-06-28','weights':{'B':'.95'}}}
        bars={'A':{'2024-06-03':{'date':'2024-06-03','tradestatus':'1'},'2024-07-01':{'date':'2024-07-01','tradestatus':'0'}},
              'B':{'2024-07-01':{'date':'2024-07-01','tradestatus':'1'}}}
        active,skipped=prefix_minute_requirements(targets,bars,{})
        self.assertEqual(active,[['A','2024-06-03'],['B','2024-07-01']])
        self.assertEqual(skipped[0]['reason'],'SOURCE_HALT')
        bars['A'].pop('2024-07-01')
        proof={'A':{'kind':'DELISTING_END','effective_date':'2024-06-28','verified_primary_boundary':True,
            'primary_document_sha256':'a'*64}}
        active,skipped=prefix_minute_requirements(targets,bars,proof)
        self.assertEqual(skipped[0]['reason'],'AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY')
        self.assertFalse(skipped[0]['actual_inventory_proven_zero'])
        with self.assertRaises(ValueError):prefix_minute_requirements(targets,bars,{})

    def test_future_request_is_rejected_before_any_source_fetch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            journal=QueryJournal(directory,max_queries=1,max_attempts=1);calls=[]
            with self.assertRaises(ValueError):
                query_minute_packet(journal,'SH600001','2026-01-05','host',lambda:calls.append(1))
            self.assertEqual(calls,[])

    def test_success_and_failure_are_immutable_and_restart_does_not_repeat_source_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            journal=QueryJournal(directory,max_queries=2,max_attempts=1);calls=[]
            def fetch():calls.append(1);return {'points':[],'trading_date':'2024-06-03'}
            first=query_minute_packet(journal,'SH600001','2024-06-03','host',fetch)
            again=query_minute_packet(journal,'SH600001','2024-06-03','host',fetch)
            self.assertEqual(first,again);self.assertEqual(len(calls),1);self.assertEqual(first['status'],'RESPONSE_CAPTURED')
            def fail():calls.append(1);raise RuntimeError('fixture source failure')
            first=query_minute_packet(journal,'SH600002','2024-06-03','host',fail)
            again=query_minute_packet(journal,'SH600002','2024-06-03','host',fail)
            self.assertEqual(first,again);self.assertEqual(len(calls),2);self.assertEqual(first['status'],'REQUEST_FAILED')

    def test_failed_query_cannot_hide_a_changed_immutable_request(self):
        import tempfile,json
        from scripts.fundamental_query_journal import digest
        with tempfile.TemporaryDirectory() as directory:
            journal=QueryJournal(directory,max_queries=1,max_attempts=1)
            def fail():raise RuntimeError('fixture source failure')
            first=query_minute_packet(journal,'SH600001','2024-06-03','host',fail)
            self.assertEqual(first['status'],'REQUEST_FAILED')
            requests=list(journal.root.glob('queries/*/request.json'))
            requests[0].write_text(json.dumps({'changed':'source identity'}))
            with self.assertRaises(ValueError):query_minute_packet(journal,'SH600001','2024-06-03','host',fail)

    def test_all_reused_prefix_files_including_primary_are_authenticated_before_capture(self):
        import tempfile,json,hashlib
        from pathlib import Path
        from scripts.illiquidity_minute_sources import authenticate_reused_minutes
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);folder=base/'primary'/'sessions';folder.mkdir(parents=True)
            name='SH600001-2024-06-03.json';path=folder/name
            path.write_text(json.dumps({'instrument':'SH600001','requested_day':'2024-06-03',
                'status':'RESPONSE_CAPTURED','response':{'points':[]}}))
            index={name:{'root':'primary','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
            active=[['SH600001','2024-06-03'],['SH600002','2024-06-03']]
            self.assertEqual(set(authenticate_reused_minutes(base,index,active)),{name})
            path.write_text('changed')
            with self.assertRaises(ValueError):authenticate_reused_minutes(base,index,active)
            path.unlink()
            with self.assertRaises((ValueError,FileNotFoundError)):authenticate_reused_minutes(base,index,active)
