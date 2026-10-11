import json
import tempfile
import unittest
from pathlib import Path

from stock_rsi.skill import Skill
from stock_rsi.time import parse_time

DATA = Path(__file__).resolve().parents[1]/'data/fixtures/synthetic_cn_v1.json'
SPLITS = DATA.parent/'synthetic_cn_splits.json'


class CampaignTests(unittest.TestCase):
    def api(self):
        from stock_rsi.campaign import run_campaign
        return run_campaign

    def test_equal_attempt_budgets_and_complete_trial_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            report=self.api()(DATA,SPLITS,'development',2,Path(directory)/'run')
            self.assertEqual(report['status'],'ENGINEERING_NO_EFFICACY')
            self.assertEqual(set(report['arms']),{'fixed','grid','random','evidence','shuffled'})
            for arm in report['arms'].values():
                self.assertEqual(len(arm['trials']),2)
                self.assertEqual(arm['valid_evaluations'],2)
                self.assertTrue(all(t['status']=='EVALUATED' for t in arm['trials']))
            self.assertEqual(report['feedback_original_hash'],report['arms']['evidence']['feedback_hash'])
            self.assertNotEqual(report['feedback_original_hash'],report['arms']['shuffled']['feedback_hash'])
            self.assertEqual(report['arms']['fixed']['best_skill_hash'],Skill().sha256)

    def test_sealed_validation_unknown_split_and_overlapping_registry_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            for split in ('sealed','validation','missing'):
                with self.assertRaises(ValueError):self.api()(DATA,SPLITS,split,1,Path(directory)/split)
            bad=json.loads(SPLITS.read_text());bad['splits']['sealed']=bad['splits']['development'].copy()
            path=Path(directory)/'bad.json';path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):self.api()(DATA,path,'development',1,Path(directory)/'bad')

    def test_invalid_proposal_consumes_attempt_without_free_replacement(self):
        class Bad:
            calls=[]
            def propose(self,*_):return {'candidate_id':'disable-fees','reason':'bad','feedback_ids':[]}
        with tempfile.TemporaryDirectory() as directory:
            result=self.api()(DATA,SPLITS,'development',2,Path(directory)/'run',arms=('codex',),proposer=Bad())
            arm=result['arms']['codex']
            self.assertEqual(arm['valid_evaluations'],0)
            self.assertEqual([t['status'] for t in arm['trials']],['INVALID_PROPOSAL']*2)
            self.assertEqual(arm['best_skill_hash'],Skill().sha256)

    def test_catalog_and_feedback_identity_are_enforced(self):
        from stock_rsi.campaign import validate_proposal, CATALOG
        with self.assertRaises(ValueError):validate_proposal({'candidate_id':'unknown','reason':'x','feedback_ids':['e1']},CATALOG,[{'case_id':'e1'}],set())
        with self.assertRaises(ValueError):validate_proposal({'candidate_id':next(iter(CATALOG)),'reason':'x','feedback_ids':['future']},CATALOG,[{'case_id':'e1'}],set())

    def test_feedback_permutation_can_change_choice_and_skill_patch_changes_behavior(self):
        from stock_rsi.campaign import heuristic,shuffle_feedback
        feedback=[{'case_id':'old','context':{'end':'2024-09-01'},'outcome':{'market_return':'0.2','market_drawdown':'0.01'}},{'case_id':'new','context':{'end':'2024-09-02'},'outcome':{'market_return':'-0.2','market_drawdown':'0.2'}}]
        self.assertNotEqual(heuristic(feedback,set())['candidate_id'],heuristic(shuffle_feedback(feedback),set())['candidate_id'])
        with tempfile.TemporaryDirectory() as directory:
            r=self.api()(DATA,SPLITS,'development',4,Path(directory)/'run',arms=('grid',))
            trials=r['arms']['grid']['trials']
            self.assertGreater(len({t['metrics']['fills'] for t in trials}),1)
            self.assertEqual(len({t['skill_hash'] for t in trials}),4)

    def test_feedback_uses_latest_facts_and_matching_final_marks(self):
        from stock_rsi.campaign import feedback_cases
        from stock_rsi.data import Dataset
        with tempfile.TemporaryDirectory() as directory:
            r=self.api()(DATA,SPLITS,'development',1,Path(directory)/'run',arms=('fixed',))
            self.assertEqual(r['feedback'][-1]['outcome']['strategy_return'],r['baseline_metrics']['net_return'])
            payload=json.loads((Path(directory)/'run/development.json').read_text())
            record=next(row for row in payload['records'] if row['kind']=='bar' and row['payload']['trade_date']=='2024-09-24')
            revised=json.loads(json.dumps(record));revised['record_id']+=':revision';revised['payload']['close']=100
            revised['public_at']=revised['available_at']='2024-10-09T16:00:00+08:00'
            payload['records'].append(revised)
            path=Path(directory)/'revised.json';path.write_text(json.dumps(payload))
            baseline=json.loads((Path(directory)/'run/baseline/report.json').read_text())
            cases=feedback_cases(Dataset.load(path),baseline)
            self.assertEqual(sum(case['context']['observations'] for case in cases),21)
            self.assertEqual(cases[-1]['outcome']['market_return'],'-0.8702')

    def test_random_is_reproducible_and_feedback_is_development_only(self):
        with tempfile.TemporaryDirectory() as directory:
            first=self.api()(DATA,SPLITS,'development',2,Path(directory)/'a',arms=('random',))
            second=self.api()(DATA,SPLITS,'development',2,Path(directory)/'b',arms=('random',))
            self.assertEqual([r['candidate_id'] for r in first['arms']['random']['trials']],[r['candidate_id'] for r in second['arms']['random']['trials']])
            exported=json.loads((Path(directory)/'a/development.json').read_text())
            self.assertTrue(all(parse_time(r['available_at'])<=parse_time('2024-10-09T15:00:00+00:00') for r in exported['records']))
            self.assertFalse(any('2024-10-14' in json.dumps(row) for row in first['feedback']))


if __name__=='__main__':unittest.main()
