import json
import sys
import tempfile
import unittest
from pathlib import Path

from stock_rsi.data import Snapshot, canonical
from stock_rsi.scheduler import Wake
from stock_rsi.skill import Skill
from stock_rsi.time import parse_time
try:
    from stock_rsi.agents import CodexAgent
except ImportError:
    CodexAgent = None


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(CodexAgent, "Codex adapter implementation missing")

    def inputs(self):
        at = parse_time("2024-09-30T17:00:00+08:00")
        snapshot = Snapshot(canonical({"as_of":at.isoformat(),"records":[{"record_id":"e1","kind":"bar","security_id":"SYN_A","payload":{"close":10}}]}))
        return snapshot, Wake(at,("WEEKLY_REVIEW",)), {"cash":"10000","equity":"10000","positions":{}}

    def executable(self, directory, mode):
        path = Path(directory)/"cli.py"
        path.write_text("""import json,sys,time
from pathlib import Path
args=sys.argv
prompt=sys.stdin.read()
assert 'SNAPSHOT_ONLY' in prompt
assert '--sandbox' in args and args[args.index('--sandbox')+1]=='read-only'
mode="""+repr(mode)+"""
if mode=='timeout':time.sleep(10)
if mode=='exit':sys.stderr.write('fixture exit');sys.exit(7)
output=Path(args[args.index('--output-last-message')+1])
schema=json.loads(Path(args[args.index('--output-schema')+1]).read_text())
assert schema['additionalProperties'] is False
data={'action':'BUY','security_id':'SYN_A','quantity':100,'evidence_ids':['e1'],'reason':'fixture decision'}
if mode=='bad':data['quantity']=-1
if mode=='tool':print(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'cat future'}}))
output.write_text(json.dumps(data))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'cached_input_tokens':0,'output_tokens':10}}))
""")
        return [sys.executable, str(path)]

    def test_local_process_protocol_produces_evidence_bound_decision_and_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            agent=CodexAgent(Skill(),command=self.executable(directory,"ok"),timeout=5,max_calls=1)
            result=agent.decide(*self.inputs())
            self.assertEqual(result.action,"BUY")
            self.assertEqual(result.quantity,100)
            self.assertEqual(agent.calls[0]["usage"]["input_tokens"],10)
            with self.assertRaises(RuntimeError):
                agent.decide(*self.inputs())

    def test_tools_invalid_schema_and_process_error_fail_closed(self):
        for mode in ('tool','bad','exit'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                agent=CodexAgent(Skill(),command=self.executable(directory,mode),timeout=5,max_calls=1)
                with self.assertRaises((ValueError,RuntimeError)):
                    agent.decide(*self.inputs())
                self.assertEqual(len(agent.calls),1)
                self.assertNotEqual(agent.calls[0]["status"],"COMPLETED")

    def test_process_timeout_is_bounded_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            agent=CodexAgent(Skill(),command=self.executable(directory,'timeout'),timeout=.05,max_calls=1)
            with self.assertRaises(RuntimeError):
                agent.decide(*self.inputs())
            self.assertEqual(agent.calls[0]['status'],'TIMEOUT')

    def test_selected_model_is_passed_explicitly_and_part_of_runtime_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            command=self.executable(directory,'ok')
            path=Path(command[-1])
            path.write_text(path.read_text()+"\nassert '--model' in args and args[args.index('--model')+1]=='test-model'\n")
            agent=CodexAgent(Skill(),command=command,model='test-model',timeout=5,max_calls=1)
            agent.decide(*self.inputs())
            self.assertIn('test-model',agent.version)
            self.assertEqual(agent.calls[0]['model'],'test-model')


if __name__=='__main__':unittest.main()
