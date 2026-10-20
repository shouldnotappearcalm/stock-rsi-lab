import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
try:
    from scripts.capture_etf_action_sources import extract_actions,capture_sources
except ImportError:
    extract_actions=capture_sources=None


def html(rows='',split='<tr><td colspan="4">暂无拆分信息!</td></tr>'):
    return ('<html><title>510300 分红送配</title><body><span>2026 current quotation deliberately ignored</span>'
      '<table><tr><th>年份</th><th>权益登记日</th><th>除息日</th><th>每份分红</th><th>分红发放日</th></tr>'+rows+'</table>'
      '<table><tr><th>年份</th><th>拆分折算日</th><th>拆分类型</th><th>拆分折算比例</th></tr>'+split+'</table></body></html>').encode()


class ETFActionSourceTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(extract_actions)

    def test_extracts_only_past_actions_and_expands_rowspan_without_reading_live_quote_into_packet(self):
        rows=('<tr><td rowspan="2">2025年</td><td>2025-01-15</td><td>2025-01-16</td><td>每份派现金0.1200元</td><td>2025-01-21</td></tr>'
              '<tr><td>2025-05-14</td><td>2025-05-15</td><td>每份派现金0.0500元</td><td>2025-05-20</td></tr>'
              '<tr><td>2026年</td><td>2026-01-14</td><td>2026-01-15</td><td>future amount not interpreted</td><td>2026-01-20</td></tr>')
        got=extract_actions(html(rows),'SH510300')
        self.assertEqual([(r['recorded'],r['ex_date'],r['cash_per_unit'],r['pay_date']) for r in got['dividends']],
            [('2025-01-15','2025-01-16','0.1200','2025-01-21'),('2025-05-14','2025-05-15','0.0500','2025-05-20')])
        self.assertEqual(got['outside_window_rows_excluded'],1);self.assertEqual(got['share_changes'],[])
        self.assertNotIn('quotation',json.dumps(got));self.assertFalse(got['historical_arrival_certified'])

    def test_missing_table_wrong_security_ambiguous_unit_or_duplicate_cannot_become_zero_actions(self):
        row='<tr><td>2025年</td><td>2025-01-15</td><td>2025-01-16</td><td>每份派现金0.1200元</td><td>2025-01-21</td></tr>'
        for raw in [html(row).replace(b'510300',b'510500'),b'<title>510300</title>',html(row+row),
                    html(row.replace('每份派现金','每10份派现金')),html(row.replace('2025-01-21','2025-01-10'))]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):extract_actions(raw,'SH510300')
        empty=extract_actions(html('<tr><td colspan="5">暂无分红信息!</td></tr>'),'SH510300')
        self.assertEqual(empty['dividends'],[]);self.assertTrue(empty['provider_asserts_no_dividends'])
        self.assertFalse(empty['primary_event_truth_certified'])

    def test_share_changes_are_retained_without_inventing_a_distribution_or_tax_status(self):
        split='<tr><td>2024年</td><td>2024-06-17</td><td>份额折算</td><td>1:2</td></tr>'
        got=extract_actions(html('<tr><td colspan="5">暂无分红信息!</td></tr>',split),'SH510300')
        self.assertEqual(got['share_changes'],[{'day':'2024-06-17','kind_provider_raw':'份额折算','ratio_provider_raw':'1:2'}])
        self.assertFalse(got['primary_event_truth_certified'])

    def test_all_original_bodies_and_failures_survive_terminal_restart_without_new_calls(self):
        sources=[{'id':'SH510300','url':'https://fundf10.eastmoney.com/fhsp_510300.html','kind':'fund_actions','file':'SH510300.html'},
                 {'id':'rule','url':'https://www.sse.com.cn/example','kind':'rule_html','file':'rule.html'}]
        with TemporaryDirectory() as name:
            calls=[]
            def fetch(url,allowed):
                calls.append(url)
                if 'example' in url:raise TimeoutError('synthetic timeout')
                data=html('<tr><td colspan="5">暂无分红信息!</td></tr>')
                return ['http_response'],[{'status':200,'final_url':url,'body_base64':base64.b64encode(data).decode(),
                    'body_truncated':False,'body_complete':True,'read_error_type':None}]
            m=capture_sources(Path(name),sources,'synthetic',fetch=fetch,minimum_interval=0)
            self.assertEqual(len(calls),2);self.assertEqual(m['captured_documents'],1);self.assertEqual(m['extracted_fund_pages'],1)
            self.assertEqual(m['HTTP_query_reservations'],2);self.assertEqual(len(m['errors']),1)
            self.assertTrue((Path(name)/'SH510300.html').is_file())
            self.assertEqual(capture_sources(Path(name),sources,'synthetic',fetch=lambda *a:self.fail('free retry')),m)

    def test_main_rejects_claimed_body_or_extraction_bounds_before_capture(self):
        import hashlib
        import bs4
        from unittest.mock import patch
        import scripts.capture_etf_action_sources as module
        repo=Path(module.__file__).resolve().parents[1]
        base={'status':'FROZEN_EIGHT_ETF_ACTION_AND_RULE_SOURCES','sources':list(module.SOURCES),
            'maximum_http_queries':8,'max_attempts_per_identity':1,'minimum_interval_seconds':.3,
            'maximum_body_bytes':10485760,'extracted_action_window':['2022-12-01','2025-12-31'],
            'bs4_version':bs4.__version__,'method_code_sha256':{n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in module.METHOD_FILES},
            'local_source_sha256':{},'public_evidence_sha256':{}}
        for key,value in [('maximum_body_bytes',1),('extracted_action_window',['2022-12-01','2026-12-31'])]:
            with TemporaryDirectory() as name:
                root=Path(name);r={**base,key:value};path=root/'request.json';path.write_text(json.dumps(r))
                with patch.object(module,'capture_sources',side_effect=lambda *a,**k:self.fail('unchecked source scope reached capture')):
                    with self.assertRaises(ValueError):module.main(['--request',str(path),'--expected-request-sha256',hashlib.sha256(path.read_bytes()).hexdigest(),'--source-root',name,'--output-dir',str(root/'output')])
                self.assertFalse((root/'output').exists())

    def test_header_only_table_is_unknown_not_a_successful_zero_action_history(self):
        empty='<tr><td colspan="5">暂无分红信息!</td></tr>'
        for raw in (html(),html(empty,split='')):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError,'empty source action table'):extract_actions(raw,'SH510300')
