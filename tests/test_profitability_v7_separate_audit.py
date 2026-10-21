import copy
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-22-profitability-all1236-v7-source-cells.py'
spec=importlib.util.spec_from_file_location('v7_separate_QA',p);qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)


class CurrentDateSourceQATests(unittest.TestCase):
    def cell(self):
        return {'comparative_date_is_unresolved':True,'reported_comparative_balance_date':None,
            'balance_header_semantics':'GENERIC_CURRENT_AND_UNDATED_OPENING','current_column_date_is_inferred_from_explicit_statement_date':True,
            'header_page':1,'header_line':'项目 期末余额 期初余额',
            'balance_current_date_anchor':{'page':1,'date':'2024-12-31','literal':'2024 年12月31日','scope':'SAME_PAGE_STATEMENT_DATE_BEFORE_GENERIC_BALANCE_HEADER'}}

    def test_generic_period_is_current_only_and_a_fabricated_prior_record_rejects(self):
        obs={'fiscal_end':'2024-12-31','payload':{'cells':{'total_assets':self.cell()}}};case={'fiscal_year':2024,'source_observations':[obs]}
        self.assertEqual(qa.admitted_periods(case),{'2024-12-31'})
        prior=copy.deepcopy(obs);prior['fiscal_end']='2023-12-31';case['source_observations'].append(prior)
        with self.assertRaises(AssertionError):qa.admitted_periods(case)

    def test_explicit_Jan1_does_not_become_prior_Dec31(self):
        c=self.cell();c['comparative_date_is_unresolved']=False;c['reported_comparative_balance_date']='2024-01-01'
        case={'fiscal_year':2024,'source_observations':[{'fiscal_end':'2024-12-31','payload':{'cells':{'total_assets':c}}}]}
        self.assertEqual(qa.admitted_periods(case),{'2024-12-31'})
        c['reported_comparative_balance_date']=None
        with self.assertRaises(AssertionError):qa.admitted_periods(case)

    def test_date_must_be_literal_same_page_before_header_with_inference_label(self):
        cell=self.cell();segment=[(1,'合并资产负债表'),(1,'2024 年12月31日'),(1,'项目 期末余额 期初余额')]
        direct=lambda p:'\n'.join(t for page,t in segment if page==p)
        qa.verify_anchor(cell,2024,direct,segment)
        for field,value in [('page',2),('date','2023-12-31'),('literal','2023 年12月31日')]:
            bad=copy.deepcopy(cell);bad['balance_current_date_anchor'][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):qa.verify_anchor(bad,2024,direct,segment)
        cell['current_column_date_is_inferred_from_explicit_statement_date']=False
        with self.assertRaises(AssertionError):qa.verify_anchor(cell,2024,direct,segment)

    def test_date_after_header_or_duplicate_anchor_cannot_supply_current_period(self):
        cell=self.cell()
        for segment in [[(1,'项目 期末余额 期初余额'),(1,'2024 年12月31日')],
                        [(1,'2024 年12月31日'),(1,'2024 年12月31日'),(1,'项目 期末余额 期初余额')]]:
            direct=lambda p:'\n'.join(t for page,t in segment if page==p)
            with self.assertRaises(AssertionError):qa.verify_anchor(cell,2024,direct,segment)


if __name__=='__main__':unittest.main()
