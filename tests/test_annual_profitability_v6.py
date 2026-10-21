import copy
import json
from pathlib import Path
import unittest
from stock_rsi import annual_profitability_v6 as grammar
from tests.test_annual_profitability import pages


class AnnualProfitabilityV6Tests(unittest.TestCase):
    def source(self,claim='本公司所编制的财务报表符合企业会计准则的要求，真实、完整地反映了公司的财务状况。'):
        result=[p.replace('单位:元 币种:人民币','单位:元') for p in pages()]
        result.append('五、重要会计政策及会计估计\n1、遵循企业会计准则的声明\n'+claim+'\n2、会计期间\n自公历1月1日起至12月31日止。')
        return result

    def parse(self,source):return grammar.parse_consolidated_tables(source,2023,normative_basis=grammar.CAS19_REFERENCE)

    def test_every_old_explicit_success_is_identical_and_needs_no_regulatory_reference(self):
        self.assertEqual(grammar.parse_consolidated_tables(pages(),2023),grammar.prior.parse_consolidated_tables(pages(),2023))

    def test_compound_evidence_preserves_local_unit_quote_and_marks_regulatory_inference(self):
        data=self.parse(self.source());cell=data['2023-12-31']['revenue']
        self.assertEqual(cell['value_CNY'],'100.00');self.assertEqual(cell['unit_evidence_literal'],'单位:元')
        evidence=cell['currency_scope_evidence'][0]
        self.assertEqual(evidence['scope'],'INFERRED_FROM_EXPLICIT_CAS_COMPLIANCE_AND_CAS19_ART4')
        self.assertTrue(evidence['currency_is_regulatory_inference_not_literal_quote'])
        self.assertIn('符合企业会计准则',evidence['literal']);self.assertNotIn('unit',evidence)
        self.assertEqual(evidence['normative_reference'],grammar.CAS19_REFERENCE)
        self.assertEqual(set(data),{'2023-12-31','2022-12-31'})

    def test_missing_functional_only_IFRS_and_qualified_claims_are_not_CAS_proof(self):
        claims=['本公司采用人民币为记账本位币。','本财务报表符合国际财务报告准则的要求。',
                '母公司财务报表符合企业会计准则的要求。','本财务报表不符合企业会计准则的要求。',
                '本财务报表符合企业会计准则的要求，但是采用IFRS列报。',
                '本财务报表符合企业会计准则的要求。\n但是未遵循部分准则。']
        for claim in claims:
            with self.subTest(claim=claim),self.assertRaises(ValueError):self.parse(self.source(claim))

    def test_foreign_reporting_currency_and_primary_table_currency_override_inference(self):
        for change in (lambda p:[*p,'本财务报表以美元列示。'],
                       lambda p:[t.replace('单位:元','单位:元\n币种:美元') for t in p],
                       lambda p:[t.replace('单位:元','单位:美元') for t in p]):
            with self.subTest(change=change),self.assertRaises(ValueError):self.parse(change(self.source()))

    def test_normative_reference_is_required_pinned_and_after_its_publication_year(self):
        with self.assertRaisesRegex(ValueError,'archived pre2024 CAS19'):grammar.parse_consolidated_tables(self.source(),2023)
        bad=copy.deepcopy(grammar.CAS19_REFERENCE);bad['archived_body_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'archived pre2024 CAS19'):
            grammar.parse_consolidated_tables(self.source(),2023,normative_basis=bad)
        old=[p.replace('2023','2005').replace('2022','2004') for p in self.source()]
        with self.assertRaisesRegex(ValueError,'full fiscal year after'):
            grammar.parse_consolidated_tables(old,2005,normative_basis=grammar.CAS19_REFERENCE)

    def test_unscoped_cross_page_duplicate_and_overlong_CAS_claims_are_not_admitted(self):
        source=self.source();claim=source.pop()
        with self.assertRaises(ValueError):self.parse([claim,*source])
        with self.assertRaises(ValueError):self.parse([*self.source(),self.source()[-1]])
        source=self.source();source[-1]='1、遵循企业会计准则的声明\n本财务报表符合企业会计准则的要求，'
        source.append('真实、完整地反映了公司的财务状况。')
        with self.assertRaises(ValueError):self.parse(source)
        source=self.source('本财务报表符合企业会计准则的要求，\n真实、\n完整地\n反映了\n公司的财务状况。')
        with self.assertRaises(ValueError):self.parse(source)

    def test_Jan1_and_no_financial_proxy_rules_remain(self):
        source=[p.replace('2022年12月31日','2023年1月1日') for p in self.source()]
        self.assertEqual(set(self.parse(source)),{'2023-12-31'})
        for before,after in [('其中：营业收入','营业总收入'),('其中：营业成本','营业总成本')]:
            with self.subTest(after=after),self.assertRaises(ValueError):self.parse([p.replace(before,after) for p in self.source()])

    def test_reviewed_real_CAS_excerpts_are_scoped_without_modifying_quotes(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/annual-profitability-v6-CAS-compliance-excerpts.json').read_text())
        for record in fixture['records']:
            anchor=record['source_statement_scope_anchor'];page=record['physical_page']
            source=['']*page;source[anchor['page']-1]=anchor['literal'];source[page-1]+='\n'+record['source_excerpt']
            if anchor['kind']=='PRIMARY_FINANCIAL_STATEMENTS_SECTION':
                context={'kind':anchor['kind'],'end_page_exclusive':anchor['page'],'end_literal':anchor['literal']}
            else:context={'kind':anchor['kind']}
            result=grammar.cas_currency_evidence(source,[(anchor['page'],anchor['literal'])],context,grammar.CAS19_REFERENCE)
            self.assertEqual(len(result),1);self.assertEqual(result[0]['page'],page)


if __name__=='__main__':unittest.main()
