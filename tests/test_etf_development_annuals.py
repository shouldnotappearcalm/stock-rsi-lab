import unittest
from decimal import Decimal as D
from stock_rsi.calendar import TradingCalendar
from scripts.run_etf_relative_pre2026 import summarize_development

class ETFAnnualTests(unittest.TestCase):
 def test_each_year_uses_previous_year_close_not_initial_cash(self):
  cal=TradingCalendar(['2023-12-29','2024-01-02','2024-12-31','2025-01-02','2025-12-31'])
  rows=[{'day':day,'equity':D(eq),'exposure':D('.95')} for day,eq in [('2024-01-02','9000'),('2024-12-31','11000'),('2025-01-02','12100'),('2025-12-31','9900')]]
  r=summarize_development(cal,rows,'10000')
  self.assertEqual(r['2024']['sessions'],2);self.assertEqual(r['2025']['sessions'],2)
  self.assertEqual(r['2024']['net_return'],D('.1'));self.assertEqual(r['2025']['net_return'],D('-.1'))
  self.assertEqual(r['2024']['max_drawdown'],D('-.1'))
  with self.assertRaises(ValueError):summarize_development(cal,rows[:-1],'10000')
  with self.assertRaises(ValueError):summarize_development(cal,[rows[0],rows[0]]+rows[1:],'10000')
  with self.assertRaises(ValueError):summarize_development(cal,rows+[{'day':'2026-01-05','equity':D('10000'),'exposure':D('.95')}],'10000')

if __name__=='__main__':unittest.main()
