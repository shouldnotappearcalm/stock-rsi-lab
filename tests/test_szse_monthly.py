"""Synthetic original-table fragments exercise parsing, not market returns."""
import unittest

try:
    from stock_rsi.szse_monthly import parse_transactions, discover_transaction_url, month_shift
except ImportError:
    parse_transactions = discover_transaction_url = month_shift = None


def table(code='000001', name='平安银行', pe='4.80', month='2024.04'):
    cells = [code, name, '1,940,592', '1,940,551', '11.240', '8.960', '100', '200']
    first = ''.join('<td class="c'+str(i)+'">'+c+'</td>' for i,c in enumerate(cells,1))
    last = ''.join('<td class="c'+str(i)+'">'+c+'</td>' for i,c in enumerate(['11.030','10.040','10.790','2.57','100','200',pe],9))
    return ('<caption>证券成交统计 TRANSACTION OF SECURITIES - （'+month+'）</caption>'
            '<table><tr>'+first+'<td class="separator"/>'+last+'</tr></table>')


class SzseMonthlyTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(parse_transactions, 'monthly source reader missing')

    def test_gb_source_leading_zeros_separator_and_reported_units_are_preserved(self):
        r = parse_transactions(table().encode('gb18030'), '2024-04', minimum_mainboard_rows=1)
        row = r['stocks']['SZ000001']
        self.assertEqual(row['pe'], '4.80')
        self.assertEqual(row['close'], '10.790')
        self.assertEqual(row['issued_10k_shares'], '1940592')
        self.assertFalse(row['reported_special_name'])
        self.assertEqual(r['encoding'], 'gb18030')

    def test_blank_pe_is_not_zero_and_duplicate_or_wrong_month_is_rejected(self):
        row = parse_transactions(table(pe='&nbsp;',name='*ＳＴ样本').encode(), '2024-04', minimum_mainboard_rows=1)['stocks']['SZ000001']
        self.assertIsNone(row['pe'])
        self.assertTrue(row['reported_special_name'])
        for raw in [table()+table(),table(month='2026.04'),table(pe='NaN')]:
            with self.assertRaises(ValueError): parse_transactions(raw.encode(),'2024-04',minimum_mainboard_rows=1)

    def test_link_label_excludes_stale_empty_anchors_and_url_day_is_not_period_day(self):
        parent='https://www.szse.cn/market/periodical/month/t20240513_607186.html'
        expected='https://docs.static.szse.cn/www/market/periodical/month/W020240513367375224505.html'
        html='<a href="http://docs.static.szse.cn/old.html"></a><a href="'+expected+'">证券成交统计</a>'
        self.assertEqual(discover_transaction_url(html,parent),expected)
        with self.assertRaises(ValueError): discover_transaction_url(html.replace('docs.static.szse.cn','example.com'),parent)
        self.assertEqual(month_shift('2024-01',-2),'2023-11')

    def test_capture_rejects_wrong_host_and_2026_file_before_source_access(self):
        from scripts.capture_szse_monthly_pre2026 import source_query
        class NoSource:
            def query(self,*args):raise AssertionError('forbidden source query')
        for url in ['https://example.com/t20240513_1.html',
                    'http://www.szse.cn/market/periodical/month/t20240513_1.html',
                    'https://www.szse.cn/market/periodical/month/t20260107_1.html']:
            with self.assertRaises(ValueError):source_query(NoSource(),url)
