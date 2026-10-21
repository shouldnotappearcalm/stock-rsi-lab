"""Synthetic frozen-baseline regression; never opens a provider or account."""
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    m = importlib.import_module('scripts.run_qlib_low_market_residual_vol_budgeted_pre2026')
except ModuleNotFoundError:
    m = None

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

class FrozenBaselineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'budgeted orchestration is not implemented')

    def fixture(self, root):
        baseline = root / 'low-market-residual-vol1m-pre2026-development-20261021'
        results = {}
        for cost in (20, 40):
            for family in ('eligible_equal_weight', 'low_total_vol_1m_control', 'low_market_residual_vol_1m'):
                label = f'{cost}/{family}'
                folder = baseline / label
                folder.mkdir(parents=True)
                hashes = {}
                for name in ('report.pkl', 'positions.pkl', 'days.csv', 'orders.csv', 'holdings.csv', 'decision_intents.json', 'suspension_mark_audit.json'):
                    p = folder / name
                    p.write_bytes(b'SYNTHETIC PRESERVED FINANCIAL ARTIFACT')
                    hashes[name] = digest(p)
                results[label] = {'artifact_sha256': hashes}
        prefix = 'experiments/qlib/low-market-residual-vol1m-pre2026-'
        files = [prefix + tail + '.json' for tail in ('development-plan', 'development-results', 'development-independent-audit', 'cash-drag-attribution')]
        for name in files:
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}')
        p = baseline / 'summary.json'
        p.write_text(json.dumps({'plan_sha256': digest(root/files[0]), 'results_by_extra_bps_and_family': results}))
        plan = {'baseline_summary_sha256': digest(p), 'baseline_evidence_sha256': {}}
        self.bind_metadata(root, baseline, plan)
        return baseline, plan

    def bind_metadata(self, root, baseline, plan):
        prefix = 'experiments/qlib/low-market-residual-vol1m-pre2026-'
        plan_file = root / (prefix+'development-plan.json')
        audit = root / (prefix+'development-independent-audit.json')
        audit.write_text(json.dumps({'summary_sha256': digest(baseline/'summary.json'), 'plan_sha256': digest(plan_file)}))
        result = root / (prefix+'development-results.json')
        result.write_text(json.dumps({'actual_summary_sha256': digest(baseline/'summary.json'), 'plan_sha256': digest(plan_file), 'independent_audit_sha256': digest(audit)}))
        names = [prefix+tail+'.json' for tail in ('development-plan','development-results','development-independent-audit','cash-drag-attribution')]
        plan['baseline_summary_sha256'] = digest(baseline/'summary.json')
        plan['baseline_evidence_sha256'] = {n: digest(root/n) for n in names}

    def test_all42_baseline_financial_bytes_preserved_and_never_unpickled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline, plan = self.fixture(root)
            self.assertEqual(m.verify_baseline(root, baseline, plan), 42)
            p = baseline / '40/low_market_residual_vol_1m/positions.pkl'
            p.write_bytes(b'changed original inventory')
            with self.assertRaises(ValueError):
                m.verify_baseline(root, baseline, plan)

    def test_missing_case_or_artifact_cannot_hide_behind_new_summary_hash(self):
        for missing in ('case', 'artifact'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                baseline, plan = self.fixture(root)
                p = baseline / 'summary.json'
                obj = json.loads(p.read_text())
                if missing == 'case':
                    obj['results_by_extra_bps_and_family'].pop('20/eligible_equal_weight')
                else:
                    obj['results_by_extra_bps_and_family']['40/low_market_residual_vol_1m']['artifact_sha256'].pop('holdings.csv')
                p.write_text(json.dumps(obj))
                self.bind_metadata(root, baseline, plan)
                with self.assertRaises(ValueError):
                    m.verify_baseline(root, baseline, plan)

    def test_baseline_evidence_cannot_be_omitted_or_self_consistently_rebound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline, plan = self.fixture(root)
            original = dict(plan['baseline_evidence_sha256'])
            plan['baseline_evidence_sha256'] = {}
            with self.assertRaises(ValueError):
                m.verify_baseline(root, baseline, plan)
            plan['baseline_evidence_sha256'] = original
            p = baseline/'summary.json'
            p.write_text(p.read_text()+'\n')
            plan['baseline_summary_sha256'] = digest(p)
            with self.assertRaises(ValueError):
                m.verify_baseline(root, baseline, plan)

    def test_wrong_request_or_existing_output_never_reads_source_or_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / 'plan.json'
            plan.write_text('{}')
            out = root / 'low-market-residual-vol1m-budgeted-pre2026-development-20261021'
            args = ['--provider-uri', str(root/'no-source'), '--gap-states', str(root/'no-gaps'), '--plan', str(plan), '--expected-plan-sha256', '0'*64, '--output-dir', str(out)]
            with self.assertRaises(ValueError):
                m.main(args)
            self.assertFalse(out.exists())
            out.mkdir()
            (out/'original').write_text('preserve')
            with self.assertRaises(ValueError):
                m.main(args)
            self.assertEqual((out/'original').read_text(), 'preserve')

if __name__ == '__main__':
    unittest.main()
