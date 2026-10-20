"""Exercise the actual standalone auditor guard without running a portfolio."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class IlliquidityAuditGuardTests(unittest.TestCase):
    def test_failed_scenario_needs_original_error_and_state_bytes_not_only_a_summary_label(self):
        source=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-21-illiquidity-independent-development-ledger.py'
        nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='authenticate_failed_case']
        self.assertEqual(len(nodes),1)
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        namespace={'json':json,'Path':Path,'sha':sha}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
        authenticate=namespace['authenticate_failed_case']
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);error={'status':'INVALID_SOURCE_OR_ACCOUNT','error':'fixture source unavailable'}
            (folder/'error.json').write_text(json.dumps(error));(folder/'failed_account_state.json').write_text('{"cash":"1000000"}')
            stated={**error,'failure_artifact_sha256':{p.name:sha(p) for p in folder.iterdir()}}
            authenticate(folder,stated)
            (folder/'failed_account_state.json').write_text('{"cash":"999999"}')
            with self.assertRaises(AssertionError):authenticate(folder,stated)
            (folder/'failed_account_state.json').unlink()
            with self.assertRaises((AssertionError,FileNotFoundError)):authenticate(folder,stated)
            (folder/'failed_account_state.json').write_text('{"cash":"1000000"}')
            with self.assertRaises(AssertionError):authenticate(folder,{**stated,'error':'changed failure claim'})
            with self.assertRaises(AssertionError):authenticate(folder,{**stated,'status':'DEVELOPMENT_INVALID_NOT_RUN_2026'})
