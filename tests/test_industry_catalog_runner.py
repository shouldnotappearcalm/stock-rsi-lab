from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import build_profitability_industry_catalog as build
from tests.test_industry_catalog import packet,PUBLIC,OBSERVED


class IndustryCatalogRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.pdf=self.base/'source.bin';self.pdf.write_bytes(b'%PDF-SYNTHETIC-CLASSIFICATION')
        self.sha=build.file_sha(self.pdf);self.cohort=['SH600001','SH600030','SZ000998']
        self.packets=[packet(1,[['农、林、牧、渔业(A)','01','农业','000998','隆平高科']]),
                      packet(2,[['金融业(J)','67','资本市场服务','600030','中信证券']])]
        for p in self.packets:p['source_sha256']=self.sha
        self.request={'source_pdf_relative_path':self.pdf.name,'source_pdf_sha256':self.sha,'physical_pages':2,
            'source_observed_at':OBSERVED,'public_content_available_by':PUBLIC,'snapshot_queries':build.queries(PUBLIC,OBSERVED),
            'input_sha256':{'source/source.bin':self.sha},'cohort':self.cohort}
        self.request_file=self.base/'request.json';build.write_once(self.request_file,self.request);self.reqsha=build.file_sha(self.request_file)

    def run_source(self,extractor=None):
        with patch.object(build,'verify',return_value=(self.request,{'source/source.bin':self.pdf},self.cohort)):
            return build.run(self.base,self.base,self.base/'membership',self.request_file,self.reqsha,self.base/build.OUTPUT,
                extractor=extractor or (lambda *args:iter(self.packets)))

    def test_all_pages_catalog_visibility_unknowns_and_fresh_only_output(self):
        result=self.run_source();self.assertEqual(result['physical_pages'],2);self.assertEqual(result['source_classification_records'],2)
        self.assertEqual(result['dated_cohort_count'],3)
        self.assertEqual(result['reconstructed2024_source_vintage_status_counts'],{'NOT_IN_SOURCE_VINTAGE':1,'FINANCIAL_IN_SOURCE_VINTAGE':1,'NONFINANCIAL_IN_SOURCE_VINTAGE':1})
        self.assertEqual(result['observed_pre2026_visible_classifications'],0)
        self.assertFalse(result['current_business_identity_verified']);self.assertFalse(result['investment_factor_admitted'])
        self.assertTrue(result['reconstructed2024_2025_record_ids_equal'])
        self.assertEqual(len(list((self.base/build.OUTPUT).glob('page-*.json'))),2)
        with self.assertRaisesRegex(ValueError,'no retry/resume'):self.run_source()

    def test_original_interrupt_keeps_prefix_and_rehashes_deleted_source_and_request(self):
        original=KeyboardInterrupt('classification extraction interrupted')
        def interrupted(*args):
            yield self.packets[0]
            self.pdf.unlink();self.request_file.write_text('{}');raise original
        with self.assertRaises(KeyboardInterrupt) as caught:self.run_source(interrupted)
        self.assertIs(caught.exception,original)
        out=self.base/build.OUTPUT;terminal=build.read(out/'terminal.json')
        self.assertEqual(terminal['completed_geometry_pages'],1);self.assertEqual(terminal['pending_physical_pages'],[2])
        self.assertEqual({m['input'] for m in terminal['postcheck']['mismatches']},{'source/source.bin','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())

    def test_duplicate_stock_code_cannot_produce_a_catalog_success(self):
        self.packets[1]=packet(2,[['金融业(J)','67','资本市场服务','000998','错误重复']]);self.packets[1]['source_sha256']=self.sha
        with self.assertRaisesRegex(ValueError,'unique six-digit'):self.run_source()
        out=self.base/build.OUTPUT;self.assertEqual(len(list(out.glob('page-*.json'))),2)
        self.assertFalse((out/'catalog.json').exists());self.assertFalse((out/'summary.json').exists())
        self.assertTrue(build.read(out/'input-postcheck.json')['all_inputs_unchanged'])

    def test_source_request_change_after_extraction_blocks_success_even_if_catalog_was_built(self):
        def changed(*args):
            yield from self.packets
            self.request_file.write_text('{}')
        with self.assertRaisesRegex(ValueError,'unchanged source'):self.run_source(changed)
        out=self.base/build.OUTPUT;self.assertTrue((out/'catalog.json').exists());self.assertFalse((out/'summary.json').exists())
        self.assertEqual(build.read(out/'input-postcheck.json')['mismatches'],[{'input':'frozen_source_request','reason':'SHA256_CHANGED'}])


if __name__=='__main__':unittest.main()
