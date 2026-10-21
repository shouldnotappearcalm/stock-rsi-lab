import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


CODE = Path(__file__).resolve().parents[1] / 'experiments/qlib/audit_sources/2026-10-22-profitability-schema-run-integrity.py'
spec = importlib.util.spec_from_file_location('profitability_schema_integrity', CODE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class SchemaRunIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.base = Path(self.temp.name) / 'source'
        self.run = self.base / 'run'
        self.req = self.root / 'request.json'
        cases, documents, coverage = {}, [], {}
        for issuer in range(12):
            code = f'SH{issuer:06d}'
            coverage[code] = {}
            for year in (2022, 2023, 2024):
                key = f'{code}-{year}'
                document = {'capture_key': key, 'instrument': code, 'fiscal_year': year,
                            'source_sha256': 'a' * 64}
                documents.append(document)
                case = {**document, 'page_count': 1, 'cover_code_consistent': False,
                        'cover_annual_year_consistent': True, 'all_extracted_page_text_sha256': {'1': 'b' * 64},
                        'source_observations': [], 'status': 'COVER_IDENTITY_UNVERIFIED'}
                for flag in ('financial_version_history_complete', 'historical_arrival_verified',
                             'economic_sector_compatibility_verified', 'manual_numeric_visual_review_complete',
                             'investment_factor_admitted'):
                    case[flag] = False
                cases[key] = case
                coverage[code][str(year)] = {'capture_key': key, 'status': case['status'], 'error': None}
                put(self.run / (key + '.json'), case)
        docs_name = 'gross-profitability-fixed12-annual-pdfs-20261022/documents.json'
        put(self.base / docs_name, documents)
        inputs = {'source/' + docs_name: audit.sha(self.base / docs_name)}
        for i in range(281):
            p = self.root / f'bound/{i}.json'
            put(p, {'synthetic_bound_input': i})
            inputs[f'repo/bound/{i}.json'] = audit.sha(p)
        put(self.req, {'status': 'FROZEN_BEFORE_FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION',
            'document_count': 36, 'security_ranking_or_returns_permitted': False,
            '2026_financial_or_market_values_permitted': False, 'input_sha256': inputs})
        self.expected_sha = audit.sha(self.req)
        put(self.run / 'input-before.json', {**inputs, 'frozen_source_request': self.expected_sha})
        post = {'all_inputs_unchanged': True, 'count': 283, 'mismatches': [],
                'source_request_rehashed_after_processing': True}
        put(self.run / 'input-postcheck.json', post)
        put(self.run / 'terminal.json', {'status': 'FIXED36_SCHEMA_INSPECTION_TERMINAL',
            'completed_documents': 36, 'pending': [], 'original_error': None, 'postcheck': post,
            'persistence_errors': [], 'portfolio_returns_computed': False})
        put(self.run / 'case_results.json', cases)
        summary = {'status': 'FIXED36_FINANCIAL_SOURCE_SCHEMA_INSPECTION_COMPLETE_NOT_FACTOR_ADMITTED',
            'documents': 36, 'issuer_count': 12, 'request_sha256': self.expected_sha,
            'status_counts': {'COVER_IDENTITY_UNVERIFIED': 36}, 'coverage_by_issuer': coverage,
            'source_observations': 0, 'all3_year_supported_parse_issuers': 0, 'input_count': 283,
            'all_inputs_unchanged': True}
        for flag in ('financial_version_history_complete', 'historical_arrival_verified',
                     'economic_sector_compatibility_verified', 'manual_numeric_visual_review_complete',
                     'investment_factor_admitted', 'original_parser_or_financial_source_changed',
                     'security_ranking_or_portfolio_returns_computed', '2026_financial_or_market_values_read',
                     'objective_achieved'):
            summary[flag] = False
        put(self.run / 'summary.json', summary)

    def inspect(self):
        return audit.inspect(self.root, self.base, self.req, self.expected_sha, self.run)

    def test_complete_all_rejected_run_is_integrity_pass_without_data_admission(self):
        result = self.inspect()
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['PDF_text_or_cells_independently_rederived'])
        self.assertEqual(41, len(result['all41_output_sha256']))

    def test_summary_cannot_claim_an_extra_observation(self):
        path = self.run / 'summary.json'
        summary = audit.read(path)
        summary['source_observations'] = 1
        put(path, summary)
        with self.assertRaisesRegex(AssertionError, 'summary rebuilt'):
            self.inspect()

    def test_rejected_case_cannot_emit_a_financial_observation(self):
        cases = audit.read(self.run / 'case_results.json')
        key = next(iter(cases))
        cases[key]['source_observations'] = [{'invented': 'value'}]
        put(self.run / (key + '.json'), cases[key])
        put(self.run / 'case_results.json', cases)
        with self.assertRaisesRegex(AssertionError, 'rejected source emits no'):
            self.inspect()

    def test_mutated_bound_input_and_escaping_artifact_are_rejected(self):
        (self.root / 'bound/0.json').write_text('changed')
        with self.assertRaisesRegex(AssertionError, 'unchanged input before'):
            self.inspect()
        with self.assertRaisesRegex(AssertionError, 'relative bound artifact'):
            audit.safe_child(self.root, '../escape')


if __name__ == '__main__':
    unittest.main()
