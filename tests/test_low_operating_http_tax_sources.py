from io import BytesIO
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
from urllib.parse import urlparse,parse_qs
from unittest.mock import patch
try:
    from stock_rsi.vendor_dividend_tax_text import parse_net_cash
    from scripts import capture_low_operating_http_pre2026 as source
    from scripts import audit_low_operating_http_pre2026 as audit
except ImportError:
    parse_net_cash=source=audit=None
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS

SESSIONS=['2024-01-02','2024-01-03']
def body(code,days=SESSIONS):
    return json.dumps({'data':{'code':code[2:],'market':int(code.startswith('SH')),
      'klines':[d+',10,10,11,9,2,2000,20,0,0,1' for d in days]}}).encode()
def packet():
    row=dict.fromkeys(DIVIDEND_FIELDS,'');row.update(code='sh.600118',dividOperateDate='2024-06-10',
       dividCashPsBeforeTax='.03',dividCashPsAfterTax='0.027或0.03',dividStocksPs='0',dividReserveToStockPs='0')
    return {'instrument':'SH600118','window':['2023-12-29','2025-12-31'],'bars':[
       dict(zip(BAR_FIELDS,[d,'sh.600118','10','11','9','10','10','200','2000','3','1','0'])) for d in SESSIONS],
       'distributions':[row],'adjustments':[],'quarantine':[]}
class Response(BytesIO):
    def __init__(self,data,url,*,status=200):super().__init__(data);self.url=url;self.status=status;self.headers={'Content-Length':str(len(data)),'Content-Type':'application/json'}
class Opener:
    def __init__(self,mode='ok'):self.calls=[];self.mode=mode
    def __call__(self,request,timeout):
        self.calls.append((request.full_url,timeout));q=parse_qs(urlparse(request.full_url).query);code=q['secid'][0].split('.')[1];code=('SH' if code.startswith('6') else 'SZ')+code
        if self.mode=='timeout':raise URLError('synthetic timeout')
        return Response(body(code),request.full_url if self.mode!='redirect' else 'https://example.com/',status=503 if self.mode=='http' else 200)


class LowOperatingHttpTaxTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(source,'new bounded HTTP source module missing');self.assertIsNotNone(audit);self.assertIsNotNone(parse_net_cash)
    def test_tax_literal_options_are_ordered_unselected_and_empty_is_unknown(self):
        r=parse_net_cash('0.027或0.03','.03');self.assertEqual(r['source_text'],'0.027或0.03');self.assertEqual(r['options'],['0.027','0.03'])
        self.assertIsNone(r['selected_net_cash']);self.assertFalse(r['tax_treatment_admitted'])
        self.assertEqual(parse_net_cash('','')['status'],'UNKNOWN_EMPTY_SOURCE_TEXT')
        self.assertEqual(parse_net_cash('0.01或0.01','.02')['options'],['0.01','0.01'])
    def test_invalid_or_above_gross_tax_options_are_rejected(self):
        for x in ('-0.1','NaN','Infinity','0.01或NaN','0.04或0.03','0.01 或0.03','0.01或者0.03'):
            with self.subTest(x=x),self.assertRaises(ValueError):parse_net_cash(x,'.03')
    def test_tax_view_preserves_original_and_other_source_failures(self):
        p=packet();before=copy.deepcopy(p);r=source.tax_risk(p,SESSIONS)
        self.assertEqual(p,before);self.assertEqual(len(r['after_tax_receipts']),1);self.assertFalse(r['physical_account_admitted'])
        p['bars'][0]['close']='NaN'
        with self.assertRaises(ValueError):source.tax_risk(p,SESSIONS)
    def test_exact_http_rows_and_independent_decoder_agree(self):
        a=source.parse_bars(body('SZ002326'),'SZ002326',SESSIONS)
        self.assertEqual(a,audit.decode_bars(body('SZ002326'),'SZ002326',SESSIONS));self.assertEqual(len(a),2)
        self.assertNotIn('isST',a[0]);self.assertNotIn('preclose',a[0])
    def test_future_duplicate_gapped_wrong_code_and_invalid_price_http_rejected(self):
        cases=[body('SZ002326',['2026-01-05']),body('SZ002326',[SESSIONS[0]]*2),body('SZ002326',SESSIONS[:1]),body('SH600118')]
        v=json.loads(body('SZ002326'));v['data']['klines'][0]=v['data']['klines'][0].replace(',10,10,',',NaN,10,');cases.append(json.dumps(v).encode())
        for raw in cases:
            for parser in (source.parse_bars,audit.decode_bars):
                with self.subTest(parser=parser.__name__),self.assertRaises(ValueError):parser(raw,'SZ002326',SESSIONS)
    def test_control_price_volume_and_amount_mismatches_are_not_hidden(self):
        bars=source.parse_bars(body('SH600118'),'SH600118',SESSIONS);p=packet()
        self.assertTrue(source.control_check(bars,p['bars'])['corroborated'])
        for field,val in (('open','9.9'),('volume','201'),('amount','2000.02')):
            changed=copy.deepcopy(p['bars']);changed[0][field]=val
            self.assertFalse(source.control_check(bars,changed)['corroborated'])
    def execute(self,root,opener):
        p=root/'input.json';p.write_text('{"immutable":true}')
        return source.execute({'resources':source.RESOURCES},
          {'known_hashes':{str(p):source.sha(p)},'sessions':SESSIONS,'packets':{'SH600118':packet()},'request_sha256':'a'*64},root/'capture',opener)
    def test_terminal_binds_its_frozen_request(self):
        with tempfile.TemporaryDirectory() as t:
            result=self.execute(Path(t),Opener());self.assertEqual(result['request_sha256'],'a'*64)
    def test_exact_two_requests_success_and_no_fake_account_admission(self):
        with tempfile.TemporaryDirectory() as t:
            op=Opener();r=self.execute(Path(t),op);self.assertTrue(r['complete']);self.assertEqual(len(op.calls),2)
            self.assertTrue(all(timeout==20 for _,timeout in op.calls));self.assertFalse(r['physical_account_admitted'])
            self.assertEqual(len(list((Path(t)/'capture').rglob('reservation.json'))),2)
    def test_error_timeout_redirect_and_body_cap_are_retained_without_retry(self):
        for mode in ('timeout','http','redirect','oversize'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                op=Opener(mode)
                if mode=='oversize':
                    base=op
                    def op(req,timeout):base.calls.append((req.full_url,timeout));return Response(b'x'*(source.MAX_BYTES+2),req.full_url)
                r=self.execute(Path(t),op);self.assertFalse(r['complete'])
                self.assertEqual(len(list((Path(t)/'capture').rglob('reservation.json'))),2)
                self.assertEqual(len(list((Path(t)/'capture').rglob('response.json'))),2)
    def test_late_input_or_capture_output_mutation_fails_and_retains_terminal(self):
        for mode in ('input','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);real=source.write_once
                def write(p,v):
                    real(p,v)
                    if p.name=='.terminal-pending.json':
                        target=root/'input.json' if mode=='input' else next((root/'capture').rglob('body.bin'))
                        target.write_bytes(b'changed')
                with patch.object(source,'write_once',side_effect=write),self.assertRaises(ValueError):self.execute(root,Opener())
                self.assertFalse(source.read(root/'capture/terminal.json')['complete'])
