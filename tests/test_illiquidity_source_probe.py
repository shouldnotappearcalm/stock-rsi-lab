import json
from pathlib import Path
import tempfile
import unittest
from scripts.fundamental_query_journal import QueryJournal
try:
    from scripts.probe_illiquidity_missing_minutes_pre2026 import persist_then_logout
except ImportError:persist_then_logout=None


class IlliquiditySourceProbeTests(unittest.TestCase):
    def test_logout_error_does_not_replace_a_captured_response_with_a_source_failure(self):
        self.assertIsNotNone(persist_then_logout)
        with tempfile.TemporaryDirectory() as directory:
            journal=QueryJournal(directory,max_queries=1,max_attempts=1)
            def fetch():return ['field'],[['saved source row']]
            def logout():raise RuntimeError('fixture logout failure')
            payload,receipt=persist_then_logout(journal,{'method':'fixture'},fetch,logout)
            self.assertEqual(payload['rows'],[['saved source row']])
            response=json.loads((Path(directory)/receipt['response_file']).read_text())
            self.assertEqual(response['status'],'CAPTURED')
            errors=list(Path(directory).glob('queries/*/logout-error.json'))
            self.assertEqual(len(errors),1);self.assertEqual(json.loads(errors[0].read_text())['error'],'fixture logout failure')
