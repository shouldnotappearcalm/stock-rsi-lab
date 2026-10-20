import base64
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
try:
    from scripts.capture_etf_rotation_pre2026 import parse_history,capture,history_url
except ImportError:
    parse_history=capture=history_url=None

CODES=('SH510300','SH510500','SZ159915')
DAYS=['2022-12-01','2022-12-02']


def response(code='510300',days=None):
    return {'rc':0,'data':{'code':code,'market':0 if code=='159915' else 1,'decimal':3,
        'klines':[d+',1.001,1.005,1.006,1.000,1000,100200,0.60,0.10,0.001,0.01' for d in (days or DAYS)]}}


class ETFCaptureTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(capture)

    def test_preserves_all_six_raw_responses_and_never_substitutes_an_adjustment_mode(self):
        with TemporaryDirectory() as name:
            out=Path(name);seen=[]
            def fetch(url,payload):
                self.assertIsNone(payload);seen.append(url)
                code=next(c for c in CODES if c[2:] in url)
                raw=json.dumps(response(code[2:])).encode()
                return ['http_response'],[{'status':200,'final_url':url,'body_base64':base64.b64encode(raw).decode(),
                    'body_truncated':False,'body_complete':True,'read_error_type':None}]
            manifest=capture(out,DAYS,'synthetic-request',fetch=fetch,minimum_interval=0)
            self.assertEqual(len(seen),6);self.assertEqual(manifest['captured_series'],6)
            self.assertEqual(manifest['HTTP_query_reservations'],6);self.assertFalse(manifest['source_admitted_for_account_replay'])
            self.assertEqual(json.loads((out/'SH510300-raw.json').read_text())['bars'][0]['close'],'1.005')
            again=capture(out,DAYS,'synthetic-request',fetch=lambda *a:self.fail('free restart network'))
            self.assertEqual(again,manifest)

    def test_wrong_security_future_duplicate_missing_session_or_bad_ohlc_rejects(self):
        cases=[response('510500'),response(days=DAYS+['2026-01-05']),response(days=DAYS+DAYS[:1]),response(days=DAYS[:1])]
        bad=response();bad['data']['klines'][0]=bad['data']['klines'][0].replace('1.006','0.990');cases.append(bad)
        for body in cases:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):parse_history(body,'SH510300','raw',DAYS)
        with self.assertRaises(ValueError):history_url('SH600580','raw')
        with self.assertRaises(ValueError):history_url('SH510300','qfq')

    def test_empty_provider_payload_is_preserved_as_failure_without_derived_bars(self):
        with TemporaryDirectory() as name:
            out=Path(name)
            def fetch(url,payload):
                data=b'{"rc":0,"data":null}'
                return ['http_response'],[{'status':200,'final_url':url,'body_base64':base64.b64encode(data).decode(),
                    'body_truncated':False,'body_complete':True,'read_error_type':None}]
            m=capture(out,DAYS,'synthetic-request',fetch=fetch,minimum_interval=0)
            self.assertEqual(m['captured_series'],0);self.assertEqual(len(m['errors']),6)
            self.assertEqual(len(list(out.rglob('response-1.json'))),6)
            self.assertEqual(list(out.glob('SH*.json')),[])
            self.assertFalse(m['portfolio_returns_computed'])

    def test_timeout_attempts_remain_consumed_across_terminal_restart(self):
        with TemporaryDirectory() as name:
            out=Path(name);calls=[]
            def fail(url,payload):calls.append(url);raise TimeoutError('synthetic timeout')
            m=capture(out,DAYS,'synthetic-request',fetch=fail,minimum_interval=0)
            self.assertEqual(len(calls),6);self.assertEqual(m['HTTP_query_reservations'],6)
            self.assertEqual(len(m['errors']),6)
            self.assertEqual(capture(out,DAYS,'synthetic-request',fetch=lambda *a:self.fail('retry')),m)
