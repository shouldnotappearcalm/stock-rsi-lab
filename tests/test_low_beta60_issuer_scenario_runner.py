import importlib
from pathlib import Path
import tempfile
import unittest

class ScenarioRunnerTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.run_low_beta60_issuer_schedule_scenario')
        except ModuleNotFoundError:self.fail('separate no-ROI account runner absent')
    def test_wrong_plan_sha_produces_no_output(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan.json';p.write_text('{}');out=Path(d)/'out'
            with self.assertRaises(ValueError):api.main(['--plan',str(p),'--expected-plan-sha256','0'*64,'--source-root',d,'--output-dir',str(out)])
            self.assertFalse(out.exists())
    def test_stale_or_incomplete_audit_cannot_score_or_create_result(self):
        import json
        api=importlib.import_module('scripts.score_low_beta60_issuer_schedule_scenario')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);audit=root/'audit.json';audit.write_text('{}');out=root/'result.json'
            with self.assertRaises(ValueError):api.main(['--source-root',d,'--audit',str(audit),'--expected-audit-sha256','0'*64,'--output',str(out)])
            self.assertFalse(out.exists())
    def test_late_profile_tamper_rejects_before_any_profile_return_is_computed(self):
        import json
        from datetime import date,timedelta
        from unittest.mock import patch
        from scripts import score_low_beta60_issuer_schedule_scenario as scorer
        from scripts.run_low_beta60_horizon_account import ARTIFACTS
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);results={}
            for label in ('100/20','100/40','500/20','500/40','1000/20','1000/40'):
                folder=root/label;folder.mkdir(parents=True)
                for name in (*ARTIFACTS.values(),'scenario_ledger.json'):
                    (folder/name).write_text('[]')
                days=[str(date(2023,12,29)+timedelta(days=i)) for i in range(674)]+['2025-12-31','2026-10-20']
                rows=['day,equity,exposure']+[day+',1000000,0' for day in days]
                (folder/'daily.csv').write_text('\n'.join(rows)+'\n')
                results[label]={'status':'CONDITIONAL_ENGINEERING_ACCOUNT_COMPLETE_UNSCORED','artifact_sha256':{name:scorer.file_sha(folder/name) for name in (*ARTIFACTS.values(),'scenario_ledger.json')}}
            summary={'plan_sha256':'plan','results_by_profile':results,'all_profiles_complete':True,'source_events_changed':False,'statutory_exemption_verified':False,'portfolio_returns_computed':False,'scenario_classification':'conditional','window':['2023-12-29','2026-10-20']}
            (root/'summary.json').write_text(json.dumps(summary))
            audit={**dict.fromkeys(scorer.AUDIT_FLAGS,True),'summary_sha256':scorer.file_sha(root/'summary.json'),'plan_sha256':'plan','portfolio_returns_computed':False,'critical_or_important_findings':0,'profiles':list(results)}
            ap=root/'audit.json';ap.write_text(json.dumps(audit))
            (root/'1000/40/fills.json').write_text('["changed after audit"]')
            with patch.object(scorer,'fixed_interval_returns',return_value={'three_numeric_conditions_met_at_interim_cutoff':False}) as returns:
                with self.assertRaises(ValueError):scorer.score(root,ap,scorer.file_sha(ap))
                self.assertEqual(0,returns.call_count)
    def test_every_extra_binding_is_required_before_base_loader_or_output(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            for field,names in api.BINDING_SCOPES.items():
                plan={key:dict.fromkeys(vals,'0'*64) for key,vals in api.BINDING_SCOPES.items()}
                del plan[field][names[0]]
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'binding scope'):
                    api.load_scenario(Path(d),Path(d),plan)

if __name__=='__main__':unittest.main()
