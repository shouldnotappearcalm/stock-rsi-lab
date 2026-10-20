import unittest
from tests.test_etf_action_sources import html
from scripts.derive_etf_actions_2026 import extract_typed_cashflows

class ETF2026ActionTests(unittest.TestCase):
 def test_only_frozen_interim2026_window_is_decoded_with_explicit_per10_unit(self):
  rows=('<tr><td>2025年</td><td>ignored</td><td>2025-12-31</td><td>past invalid units ignored</td><td>ignored</td></tr>'
    '<tr><td>2026年</td><td>2026-01-14</td><td>2026-01-15</td><td>每10份派现金0.9100元</td><td>2026-01-20</td></tr>'
    '<tr><td>2026年</td><td>ignored</td><td>2026-10-21</td><td>future amount not interpreted</td><td>ignored</td></tr>')
  raw=html(rows).replace('每份分红'.encode(),'每10份分红'.encode());before=bytes(raw)
  r=extract_typed_cashflows(raw,'SH510300')
  self.assertEqual(r['window'],['2026-01-01','2026-10-20']);self.assertEqual(len(r['dividends']),1)
  self.assertEqual(r['dividends'][0]['cash_per_unit'],'0.0910');self.assertEqual(r['outside_window_rows_excluded'],2)
  self.assertEqual(raw,before);self.assertFalse(r['primary_event_truth_certified'])

 def test_share_changes_are_reported_not_silently_admitted(self):
  raw=html('<tr><td colspan="5">暂无分红信息!</td></tr>','<tr><td>2026年</td><td>2026-06-17</td><td>份额折算</td><td>1:2</td></tr>')
  r=extract_typed_cashflows(raw,'SH510300');self.assertEqual(r['share_changes'][0]['day'],'2026-06-17')
  self.assertFalse(r['primary_event_truth_certified'])

 def test_empty_or_unknown_unit_still_rejects_instead_of_claiming_no_actions(self):
  with self.assertRaises(ValueError):extract_typed_cashflows(html(),'SH510300')
  raw=html('<tr><td>2026年</td><td>2026-01-14</td><td>2026-01-15</td><td>每份派现金0.9100元</td><td>2026-01-20</td></tr>').replace('每份分红'.encode(),'每10份分红'.encode())
  with self.assertRaises(ValueError):extract_typed_cashflows(raw,'SH510300')

if __name__=='__main__':unittest.main()
