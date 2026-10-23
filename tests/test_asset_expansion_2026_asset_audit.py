import importlib.util
from pathlib import Path
import unittest


class IndependentAssetRowGeometryTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-assets-source-audit.py'
        spec=importlib.util.spec_from_file_location('separate_asset_source_check',path)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)

    def lines(self):
        return [(10,100,100,110,'合并资产负债表'),(10,70,70,80,'资产总计'),
            (100,70,150,80,'200.00'),(200,70,250,80,'100.00'),
            (10,50,100,60,'母公司资产负债表'),(10,20,70,30,'资产总计'),
            (100,20,150,30,'999.00'),(200,20,250,30,'888.00')]

    def test_pdfminer_row_uses_same_height_columns_and_excludes_parent_statement(self):
        result=self.m.asset_row(self.lines(),['200.00','100.00'])
        self.assertEqual(result['literal_values'],['200.00','100.00'])
        self.assertEqual(result['row_mid_y'],75.)

    def test_parent_values_or_values_from_different_row_are_not_accepted(self):
        with self.assertRaises(ValueError):self.m.asset_row(self.lines(),['999.00','888.00'])
        lines=self.lines();lines[3]=(200,61,250,65,'100.00')
        with self.assertRaises(ValueError):self.m.asset_row(lines,['200.00','100.00'])

    def test_duplicate_matching_consolidated_rows_are_ambiguous_not_auto_selected(self):
        lines=self.lines();lines[4:4]=[(10,84,70,94,'资产总计'),(100,84,150,94,'200.00'),(200,84,250,94,'100.00')]
        with self.assertRaises(ValueError):self.m.asset_row(lines,['200.00','100.00'])

    def test_different_font_baselines_keep_columns_with_majority_vertical_overlap(self):
        # Original SH600598 page75 has 2.0332pt midpoint drift, but >81% overlap.
        lines=[(10,158.703,70,169.753,'资产总计'),
            (100,156.6698,150,167.7198,'200.00'),(200,156.6698,250,167.7198,'100.00')]
        result=self.m.asset_row(lines,['200.00','100.00'])
        self.assertEqual(result['literal_values'],['200.00','100.00'])
        lines[2]=(200,149,250,160,'100.00')
        with self.assertRaises(ValueError):self.m.asset_row(lines,['200.00','100.00'])

    def test_spaced_glyphs_inside_amounts_preserve_two_columns_and_exact_digits(self):
        lines=[(10,70,70,80,'资产总计'),
            (100,70,250,80,'2 2,775,795,123.88   2 0,637,624,991.90')]
        expected=['22,775,795,123.88','20,637,624,991.90']
        self.assertEqual(self.m.asset_row(lines,expected)['literal_values'],expected)
        with self.assertRaises(ValueError):self.m.asset_row(lines,['22,775,795,123.89',expected[1]])


if __name__=='__main__':unittest.main()
