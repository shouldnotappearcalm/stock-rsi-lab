"""Hand-checked original source witnesses; CI does not fetch/authenticate PDFs."""
import json
from pathlib import Path
import unittest
from stock_rsi import annual_cash_accruals as cash

class CashAccrualRealWitnessTests(unittest.TestCase):
    def test_four_original_reports_reproduce_twenty_four_visually_checked_cells(self):
        p=Path(__file__).parent/'fixtures/annual-cash-accrual-real-witnesses.json';fixture=json.loads(p.read_text());self.assertFalse(fixture['CI_authenticates_original_PDF']);self.assertEqual(fixture['physical_PDF_pages_visually_reviewed'],20);self.assertEqual(len(fixture['documents']),4);n=0
        for d in fixture['documents']:
            with self.subTest(capture_key=d['metadata']['capture_key']):
                report=cash.make_report(d['metadata'],d['report']['parsed']);self.assertEqual(report,d['report'])
                for kind,expected in d['hand_checked_literals_and_CNY'].items():
                    field=cash.STATEMENTS[kind][2]
                    for period,(literal,amount) in expected.items():
                        cell=report['parsed'][kind][period] if kind=='balances' else report['parsed'][kind][period][field];self.assertEqual(cell['literal'],literal);self.assertEqual(cell['value_CNY'],amount);n+=1
        self.assertEqual(n,24)
