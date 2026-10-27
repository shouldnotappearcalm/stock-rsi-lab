import json
from pathlib import Path
from unittest import TestCase
from scripts import inspect_cash_accrual_2026_sources as r

class Cash2026RealWitnessTests(TestCase):
    def test_eight_hand_read2026original_values_from_two_exchanges(self):
        f=json.loads((Path(__file__).parent/'fixtures/cash-accrual2026-real-cells.json').read_text());self.assertFalse(f['CI_authenticates_original_PDF'])
        for d in f['documents']:
            for kind,expected in d['hand_checked_literals'].items():
                table=d['original_tables'][kind];contract=table['metadata']['parser_contract']
                if contract==r.cash.v1.CONTRACT:cells=r.cash.v1.table_cells(table,2025,kind)
                elif contract==r.cash.previous.CONTRACT:cells=r.cash.previous.table_cells(table,2025,kind)
                else:cells=r.cash.table_cells(table,2025,kind)
                for i,literal in enumerate(expected):
                    cell=cells[f'{2025-i}-12-31'];self.assertEqual(cell['literal'],literal);self.assertEqual(cell['value_CNY'],literal.replace(',',''))
