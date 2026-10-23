import importlib.util
from pathlib import Path
import unittest
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-source-review.py'
s=importlib.util.spec_from_file_location('asset_tax_review',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class TaxSourceReviewTests(unittest.TestCase):
    def text(self):
        return ('证券代码：603737 公告编号2026-030 三棵树涂料股份有限公司 2025年年度权益分派实施公告 '
            '每股派发现金红利0.068元 每股转增0.2股 股本溢价发行所形成的资本公积金 本次转增股本不扣税 '
            '三棵树涂料股份有限公司董事会2026年5月26日 '
            '股份类别 股权登记日 最后交易日 除权（息）日 新增无限售条件流通股份上市日 现金红利发放日 '
            'A股 2026/5/29 — 2026/6/1 2026/6/1 2026/6/1')
    def test_two_date_formats_and_whitespace(self):
        facts=m.text_facts(self.text().replace('每股转增','每股\n转增'))
        self.assertTrue(facts['issuer_explicit_share_premium_and_no_tax_statement'])
        self.assertFalse(facts['statutory_tax_certification'])
    def test_wrong_issuer_or_year_or_ratio_cannot_supply_exemption(self):
        for before,after in [('603737','603738'),('2025年年度','2024年年度'),('0.068元','0.68元'),
                             ('0.2股','0.4股'),('本次转增股本不扣税','本次转增股本扣税'),('2026/5/29','2026/5/28')]:
            with self.subTest(before),self.assertRaises(ValueError):m.text_facts(self.text().replace(before,after))

    def test_dates_elsewhere_cannot_supply_missing_or_swapped_table_labels(self):
        for text in [self.text().replace('股权登记日','wrong label'),
                     self.text().replace('2026/5/29','2026/5/28')+'2026/5/29',
                     self.text().replace('股权登记日 最后交易日 除权（息）日','除权（息）日 最后交易日 股权登记日')]:
            with self.subTest(text),self.assertRaises(ValueError):m.text_facts(text)

    def test_posthash_failure_removes_usable_exemption_and_sets_failure_metadata(self):
        result={'status':'CACHED_ISSUER_TAX_TERMS_AND_BOTH_STRICT_FAILURES_CHECKED',
                'primary_proof_for_future_version':{'verified_exempt':True}}
        m.reject_receipt(result,KeyboardInterrupt('posthash interruption'))
        self.assertEqual(result['status'],'SOURCE_REVIEW_FAILURE_RETAINED')
        self.assertEqual(result['error_type'],'KeyboardInterrupt')
        self.assertNotIn('primary_proof_for_future_version',result)

    def test_main_changed_input_after_extraction_persists_failed_receipt_without_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';base=root/'base';repo.mkdir();base.mkdir()
            def write(p,v):
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps(v) if isinstance(v,(dict,list)) else v)
            method=repo/m.METHOD;write(method,'original method')
            archive=base/m.ARCHIVE;write(archive/m.PDF,'fake PDF')
            pdfsha=m.sha(archive/m.PDF)
            doc={'file':m.PDF,'sha256':pdfsha,'announcement_id':'1225328631','instrument':'SH603737',
                 'day':'2026-05-26','url':'https://static.cninfo.com.cn/finalpage/2026-05-26/1225328631.PDF'}
            write(archive/'manifest.json',{'documents':[doc],'query_sha256':{}})
            write(archive/'reviewed-manifest.json',{'documents':[doc]})
            write(base/m.FAILURE/'source_projection.json',{'events':[]})
            write(base/m.FAILURE/'summary.json',{'results_by_extra_bps':{c:{'status':'STRICT_ACCOUNT_FAILURE_RETAINED',
                'error':'applicable capital transfer tax treatment is unverified'} for c in ('20','40')}})
            write(base/'asset-expansion-raw-pre2026-20261022/manifest.json',{'per_code_sha256':{}})
            for c in ('20','40'):
                write(base/m.OLD/c/'daily.csv','day,cash\n2025-12-31,1\n')
                write(base/m.OLD/c/'ownership.json',{'2025-12-31':{}})
                for k in ('orders','fills','corporate_ledger'):write(base/m.OLD/c/(k+'.json'),[])
                write(base/m.FAILURE/c/'failed_account_state.json',{})
            request=root/'request.json';write(request,{'status':'FROZEN_ONE_CACHED_PRIMARY_TAX_SOURCE_NO_ROI',
                'network_queries':0,'bound_sha256':{'repo/'+m.METHOD:m.sha(method)}})
            out=base/m.OUTPUT
            def second_extractor(_):
                method.write_text('changed after extraction')
                return self.text()
            modules={'pypdf':SimpleNamespace(PdfReader=lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=self.text)])),
                     'pdfminer.high_level':SimpleNamespace(extract_text=second_extractor)}
            argv=['review','--repo-root',str(repo),'--source-root',str(base),'--request',str(request),
                  '--expected-request-sha256',m.sha(request),'--output',str(out)]
            with patch.dict(sys.modules,modules),patch.object(sys,'argv',argv), \
                 patch.object(m,'PDF_SHA',pdfsha),patch.object(m,'audit_failure',return_value={}):
                with self.assertRaisesRegex(ValueError,'source changed'):m.main()
            receipt=m.read(out)
            self.assertEqual(receipt['status'],'SOURCE_REVIEW_FAILURE_RETAINED')
            self.assertEqual(receipt['error_type'],'ValueError')
            self.assertEqual(receipt['changed_inputs'],[str(method)])
            self.assertNotIn('primary_proof_for_future_version',receipt)

if __name__=='__main__':unittest.main()
