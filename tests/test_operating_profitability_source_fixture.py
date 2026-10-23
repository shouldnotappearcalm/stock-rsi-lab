import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from scripts import build_operating_profitability_source_fixture as build
except ImportError:
    build = None


class OperatingSourceFreezeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build, 'operating source fixture builder missing')
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/'repo';self.base = Path(temporary.name)/'source'
        self.paths = build.required_paths(self.base, self.root)
        for key,path in self.paths.items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic bound source '+key)
        documents = []
        for stem,pages in build.CASES:
            year = int(stem.split('-')[1]);filename = stem+'.pdf'
            documents.append({'file':filename,'statDate':f'{year}-12-31','instrument':'SH600166',
                'day':f'{year+1}-04-27','captured_at_utc':'2026-10-23T00:00:00+00:00',
                'announcement_id':stem.split('-')[-1], 'sha256':build.sha(self.base/build.OLD/filename)})
        build.write(self.root/build.OLD_REQUEST,{'documents':documents})
        capture = {'documents':documents,'request_sha256':build.sha(self.root/build.OLD_REQUEST)}
        build.write(self.root/build.CAPTURE,capture)
        build.write(self.root/build.REVIEW,{'status':build.REVIEW_STATUS,'contract':build.CONTRACT,
            'instrument':'SH600166','expected_cells_CNY':{'2023':{},'2024':{}},
            'source_pdf_sha256':{d['file']:d['sha256'] for d in documents},
            'source_mapping_review_sha256':build.sha(self.root/build.MAPPING_REVIEW),
            'expected_current_measure_is_not_precomputed':True})
        self.request = {'status':build.STATUS,'contract':build.CONTRACT,'instrument':'SH600166',
            'report_years':[2023,2024],'pypdf_version':'6.10.0','max_publication_day':'2025-12-31',
            'portfolio_returns_permitted':False,'ranking_permitted':False,
            '2026_financial_or_market_values_permitted':False,
            'method_sha256':{name:build.sha(self.root/name) for name in build.METHODS},
            'input_sha256':{k:build.sha(p) for k,p in self.paths.items()}}
        self.request_file = self.root/'request.json';build.write(self.request_file,self.request)

    def verify(self, changed=None):
        if changed is not None:build.write(self.request_file,changed)
        return build.verify(self.base,self.root,self.request_file,build.sha(self.request_file))

    def test_exact_synthetic_source_request_is_admitted_for_source_inspection_only(self):
        request,paths,capture,review = self.verify()
        self.assertEqual(len(capture['documents']),2)
        self.assertEqual(set(paths),set(self.request['input_sha256']))
        self.assertFalse(request['portfolio_returns_permitted'])

    def test_future_returns_rank_scope_and_reader_cannot_be_silently_widened(self):
        for key,value in [('portfolio_returns_permitted',True),('ranking_permitted',True),
            ('2026_financial_or_market_values_permitted',True),('report_years',[2024,2025]),
            ('max_publication_day','2026-10-23'),('pypdf_version','unfrozen')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.verify({**self.request,key:value})

    def test_omitted_or_changed_source_and_rewritten_request_fail_before_generation(self):
        missing = copy.deepcopy(self.request);missing['input_sha256'].pop(next(iter(self.paths)))
        with self.assertRaises(ValueError):self.verify(missing)
        build.write(self.request_file,self.request)
        original = self.base/build.OLD/(build.CASES[0][0]+'.pdf');original.write_text('changed source')
        with self.assertRaises(ValueError):self.verify()
        with self.assertRaises(ValueError):build.verify(self.base,self.root,self.request_file,'0'*64)

    def test_original_failed_output_is_never_overwritten(self):
        out = self.base/'existing';out.mkdir();marker=out/'terminal.json';marker.write_text('old strict failure')
        with self.assertRaises(ValueError):build.generate(self.base,self.root,self.request_file,build.sha(self.request_file),out)
        self.assertEqual(marker.read_text(),'old strict failure')

    def test_interruption_retains_original_error_and_checks_source_and_request_mutation(self):
        original = KeyboardInterrupt('source decode interrupted')
        def interrupted(path):
            path.unlink();build.write(self.request_file,{})
            raise original
        out = self.base/'interrupted'
        with patch.object(build,'pdf_pages',side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt) as caught:
                build.generate(self.base,self.root,self.request_file,build.sha(self.request_file),out)
        self.assertIs(caught.exception,original)
        terminal = build.read(out/'terminal.json')
        self.assertFalse(terminal['completed'])
        self.assertEqual(terminal['original_error']['type'],'KeyboardInterrupt')
        self.assertEqual({r['input'] for r in terminal['postcheck']['mismatches']},
            {'source/'+build.OLD+'/'+build.CASES[0][0]+'.pdf','frozen_source_request'})
        self.assertFalse((out/'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
