import json
import tempfile
import unittest
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.run_low_risk_intraday_replay import authenticate_development, PARTICIPATION, EXTRA_BPS, CAPITALS


class IntradayControlTests(unittest.TestCase):
    def test_frozen_summary_does_not_authenticate_tampered_control_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);label='100/0/100000';folder=root/label;folder.mkdir(parents=True)
            artifacts={}
            for name in ('daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'):
                (folder/name).write_text('[]\n');artifacts[name]=sha256_file(folder/name)
            results={f'{p}/{e}/{c}':{'status':'INVALID_SOURCE_OR_ACCOUNT','error':'fixture'}
                     for p in PARTICIPATION for e in EXTRA_BPS for c in CAPITALS}
            results[label]={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED','artifact_sha256':artifacts}
            (root/'summary.json').write_text(json.dumps({'phase':'dev','method_code_sha256':{},'results_by_profile':results}))
            plan={'development_summary_sha256':sha256_file(root/'summary.json'),'method_code_sha256':{}}
            self.assertEqual(authenticate_development(root,plan),results)
            (folder/'daily.csv').write_text('modified\n')
            with self.assertRaisesRegex(ValueError,'development artifact changed'):
                authenticate_development(root,plan)
