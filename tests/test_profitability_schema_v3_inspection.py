from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import inspect_profitability_fixed12_v3 as inspect
from tests.test_annual_profitability import pages


class ProfitabilitySchemaV3InspectionTests(unittest.TestCase):
    def document(self):
        return {'capture_key':'SYNTHETIC-2023','instrument':'SH600001','fiscal_year':2023,
                'day':'2024-04-27','captured_at_utc':'2026-10-22T00:00:00+00:00',
                'source_sha256':'a'*64,'announcement_id':'123456'}

    def source_pages(self):
        return ['公司代码：600001\n2023年年度报告',*pages()]

    def test_literal_cover_and_supported_cells_remain_unadmitted(self):
        result = inspect.inspect_document(self.document(), self.source_pages())
        self.assertEqual(result['status'],'SOURCE_CELL_PARSE_SUPPORTED_PENDING_VISUAL_REVIEW')
        self.assertEqual(len(result['source_observations']),2)
        self.assertFalse(result['investment_factor_admitted'])
        self.assertFalse(result['manual_numeric_visual_review_complete'])
        self.assertFalse(result['economic_sector_compatibility_verified'])
        self.assertEqual(result['source_observations'][0]['payload']['cells']['total_assets']['value_CNY'],'200.00')

    def test_wrong_cover_code_or_year_is_not_silently_parsed(self):
        for before,after in [('600001','600002'),('2023年年度报告','2024年年度报告')]:
            source = self.source_pages();source[0] = source[0].replace(before,after)
            result = inspect.inspect_document(self.document(),source)
            self.assertEqual(result['status'],'COVER_IDENTITY_UNVERIFIED')
            self.assertEqual(result['source_observations'],[])

    def test_unsupported_units_leave_source_failure_without_numeric_substitution(self):
        source = [p.replace('单位:元','单位:百万元') for p in self.source_pages()]
        result = inspect.inspect_document(self.document(),source)
        self.assertEqual(result['status'],'SOURCE_SCHEMA_UNSUPPORTED')
        self.assertEqual(result['source_observations'],[])
        self.assertIn('unit',result['error'])

    def test_interrupted_inspection_preserves_first_error_and_posthash(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary);raw = base/'original.pdf';raw.write_bytes(b'original')
            request = base/'request.json';request.write_text('{}')
            paths = {'source/original.pdf':raw};expected = {'source/original.pdf':inspect.file_sha(raw)}
            frozen = inspect.file_sha(request);original = KeyboardInterrupt('original source inspection interruption')
            def fail(path):
                raw.unlink();request.write_text('{"changed":true}');raise original
            document = self.document();document['source_path']='original.pdf'
            with patch.object(inspect,'verify',return_value=({'input_sha256':expected},paths,[document])), patch.object(
                    inspect,'pages_from_pdf',side_effect=fail):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    inspect.run(base,base,request,frozen,base/inspect.OUTPUT)
            self.assertIs(caught.exception,original)
            terminal = inspect.read(base/inspect.OUTPUT/'terminal.json')
            self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
            self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
                             {'source/original.pdf','frozen_source_request'})
            self.assertFalse((base/inspect.OUTPUT/'summary.json').exists())


if __name__=='__main__':unittest.main()
