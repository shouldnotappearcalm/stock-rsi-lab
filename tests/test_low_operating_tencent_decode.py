from pathlib import Path
from decimal import Decimal
import json
import tempfile
import unittest
from unittest.mock import patch
try:
    from stock_rsi import tencent_history as history
    from scripts import decode_low_operating_tencent_pre2026 as source
    from scripts import audit_low_operating_tencent_pre2026 as checker
except ImportError:history=source=checker=None

DAYS=['2024-01-02','2024-01-03']
def row(day=DAYS[0]):return [day,'10.00','10.00','10.00','10.00','2',{'poison':'FUTURE_POISON'},'1','0.2']
def body(rows=None,code='SH600118',field='day'):
    return ('kline_day2023='+json.dumps({'code':0,'data':{code.lower():{field:rows if rows is not None else [row(d) for d in DAYS],
        'qt':{'future':'FUTURE_POISON'}}}})+';').encode()
def raw():return [{'date':d,'open':'10','close':'10','high':'10','low':'10','volume':'200','amount':'2000','tradestatus':'1','isST':'1'} for d in DAYS]


class TencentDecodeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(history,'selective decoder missing');self.assertIsNotNone(source);self.assertIsNotNone(checker)
    def test_ignored_current_and_extra_values_never_reach_json_decoder(self):
        loads=json.loads;seen=[]
        def scalar(x,*a,**kw):
            seen.append(x);self.assertNotIn('FUTURE_POISON',x.decode() if isinstance(x,bytes) else x);return loads(x,*a,**kw)
        with patch.object(history.json,'loads',side_effect=scalar):rows=history.decode(body(),'SH600118',DAYS)
        self.assertEqual(rows[0]['volume_shares'],'200');self.assertEqual(Decimal(rows[0]['amount_cny']),2000)
        self.assertLess(max(len(x) for x in seen),40)
    def test_future_date_rejected_before_price_value_and_completed_prefix_retained(self):
        later=row('2026-01-02');later[1]='FUTURE_POISON';completed=[];loads=json.loads
        def scalar(x,*a,**kw):
            self.assertNotIn(b'FUTURE_POISON',x if isinstance(x,bytes) else x.encode());return loads(x,*a,**kw)
        with patch.object(history.json,'loads',side_effect=scalar),self.assertRaises(ValueError):
            history.decode(body([row(),later]),'SH600118',DAYS,completed.append)
        self.assertEqual([r['date'] for r in completed],[DAYS[0]])
    def test_wrong_issuer_adjusted_only_duplicates_and_bad_framing_fail(self):
        cases=[body(code='SZ002326'),body(field='qfqday'),b'kline_day2023={"code":0,"data":{},"data":{}}',body()+b'x',b'other='+body(),b'{"x":[1,]}']
        for b in cases:
            with self.subTest(size=len(b)),self.assertRaises(ValueError):history.decode(b,'SH600118',DAYS)
        with self.assertRaises(ValueError):history.JsonSlices(b'{"x":'+b'['*65+b'0'+b']'*65+b'}')
    def test_noncent_nonfinite_fractional_share_bad_range_duplicate_dates_fail(self):
        bad=[]
        for index,value in ((1,'10.001'),(1,'NaN'),(5,'0.0001'),(3,'9')):
            r=row();r[index]=value;bad.append([r])
        bad.extend(([row(),row()],[row(DAYS[1]),row()]))
        for rows in bad:
            with self.subTest(rows=len(rows)),self.assertRaises(ValueError):history.decode(body(rows),'SH600118',DAYS)
    def test_optional_fields_unknown_and_amount_mismatch_never_changes_price_volume_gate(self):
        rows=history.decode(body([row(d)[:6] for d in DAYS]),'SH600118',DAYS)
        self.assertIsNone(rows[0]['amount_cny']);report=history.compare(rows,raw());self.assertTrue(report['price_volume_gate_passed'])
        self.assertFalse(report['all_components_exactly_corroborated'])
        r=raw();r[0]['amount']='1999.99';report=history.compare(history.decode(body(),'SH600118',DAYS),r)
        self.assertTrue(report['price_volume_gate_passed']);self.assertEqual(report['amount_exact_matches'],1)
    def test_one_control_failure_prevents_any_target_loader_or_row(self):
        r=raw();r[0]['close']='10.01';calls=[]
        result=source.evaluate(body(),lambda:calls.append(True),DAYS,r)
        self.assertFalse(result['control']['price_volume_gate_passed']);self.assertEqual(calls,[]);self.assertEqual(result['target_rows'],[])
    def test_all_trading_ST_rows_and_missing_dates_contribute_to_gate(self):
        rows=history.decode(body(),'SH600118',DAYS);report=history.compare(rows,raw())
        self.assertEqual(report['price_cells_checked'],8);self.assertTrue(report['price_volume_gate_passed'])
        self.assertFalse(history.compare(rows[:1],raw())['price_volume_gate_passed'])
        r=raw();r[1]['tradestatus']='0';self.assertTrue(history.compare(rows[:1],r)['price_volume_gate_passed'])
    def test_actual_buffer_authentication_and_boundary_input_change_prevent_target(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(body());h=source.sha(p);p.write_bytes(body(code='SZ002326'))
            with self.assertRaises(ValueError):source.bound_body(p,h)
        calls=[]
        def boundary():raise ValueError('bound source changed')
        with self.assertRaises(ValueError):source.evaluate(body(),lambda:calls.append(True),DAYS,raw(),before_target=boundary)
        self.assertEqual(calls,[])
    def test_separate_projector_agrees_and_failure_prefix_never_continues(self):
        expected=history.decode(body(),'SH600118',DAYS);self.assertEqual(checker.project(body(),'SH600118',DAYS),expected)
        later=row('2026-01-02');later[1]='FUTURE_POISON';completed=[]
        with self.assertRaises(ValueError):history.decode(body([row(),later]),'SH600118',DAYS,completed.append)
        self.assertEqual(checker.project(body([row(),later]),'SH600118',DAYS,prefix_rows=1),completed)
    def test_large_literal_volume_is_scaled_without_decimal_context_rounding(self):
        r=row();r[5]='12345678901234567890123456789'
        result=history.decode(body([r]),'SH600118',DAYS)
        self.assertEqual(result[0]['volume_shares'],str(int(r[5])*100))
    def test_subcent_tail_cannot_disappear_under_default_decimal_precision(self):
        r=row();r[1:5]=['10.00000000000000000000000000001']*4
        with self.assertRaises(ValueError):history.decode(body([r]),'SH600118',DAYS)
