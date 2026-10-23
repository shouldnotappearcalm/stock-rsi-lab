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
        self.assertEqual(checker.project(b'malformed unopened body','SH600118',DAYS,prefix_rows=0),[])
    def test_large_literal_volume_is_scaled_without_decimal_context_rounding(self):
        r=row();r[5]='12345678901234567890123456789'
        result=history.decode(body([r]),'SH600118',DAYS)
        self.assertEqual(result[0]['volume_shares'],str(int(r[5])*100))
    def test_subcent_tail_cannot_disappear_under_default_decimal_precision(self):
        r=row();r[1:5]=['10.00000000000000000000000000001']*4
        with self.assertRaises(ValueError):history.decode(body([r]),'SH600118',DAYS)
    def test_tiny_positive_prices_or_volume_cannot_underflow_into_legal_zero(self):
        for field in ('prices','volume','amount'):
            with self.subTest(field=field):
                r=row()
                if field=='prices':r[1:5]=['1e-1000100']*4
                elif field=='volume':r[5]='1e-1000100'
                else:r[8]='1e-1000100'
                with self.assertRaises(ValueError):history.decode(body([r]),'SH600118',DAYS)
    def test_target_marker_persistence_mutation_prevents_any_target_decoder_call(self):
        for mode in ('input','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                base=Path(t);known={}
                for code in ('SH600118','SZ002326'):
                    p=base/source.OPAQUE/code/'body.bin';p.parent.mkdir(parents=True);p.write_bytes(body(code=code));known[str(p.resolve())]=source.sha(p)
                real=source.persist;calls=[];real_decode=source.decode
                def persist(out,name,value,outputs):
                    real(out,name,value,outputs)
                    if name=='target-started.json':
                        p=base/source.OPAQUE/'SH600118/body.bin' if mode=='input' else out/'rows/SH600118'/f'{DAYS[0]}.json'
                        p.write_bytes(b'changed')
                def decode(b,code,*args,**kwargs):calls.append(code);return real_decode(b,code,*args,**kwargs)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=persist),patch.object(source,'decode',side_effect=decode),self.assertRaises(ValueError):
                    source.run(base,base,base/'unused','sha')
                self.assertNotIn('SZ002326',calls)
    def fixture(self,base):
        known={}
        for code in ('SH600118','SZ002326'):
            p=base/source.OPAQUE/code/'body.bin';p.parent.mkdir(parents=True);p.write_bytes(body(code=code));known[str(p.resolve())]=source.sha(p)
        return known
    def test_mutation_during_target_buffer_loading_prevents_target_decoder(self):
        for mode in ('input','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                base=Path(t);known=self.fixture(base);real=source.bound_body;real_decode=source.decode;calls=[]
                def bound(p,h):
                    data=real(p,h)
                    if p.parent.name=='SZ002326':
                        changed=base/source.OPAQUE/'SH600118/body.bin' if mode=='input' else base/source.OUTPUT/'rows/SH600118'/f'{DAYS[0]}.json'
                        changed.write_bytes(b'changed')
                    return data
                def decode(b,code,*args,**kw):calls.append(code);return real_decode(b,code,*args,**kw)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'bound_body',side_effect=bound),patch.object(source,'decode',side_effect=decode),self.assertRaises(ValueError):
                    source.run(base,base,base/'unused','sha')
                self.assertNotIn('SZ002326',calls)
    def test_durable_native_failures_reconcile_and_audit_the_actual_prefix(self):
        for mode in ('control_row','target_row','target_load','aggregate'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                base=Path(t);known=self.fixture(base);real=source.persist;bound=source.bound_body
                def persist(out,name,value,outputs):
                    real(out,name,value,outputs)
                    fail=mode=='control_row' and name=='rows/SH600118/'+DAYS[0]+'.json' or mode=='target_row' and name=='rows/SZ002326/'+DAYS[0]+'.json' or mode=='aggregate' and name=='control-rows.json'
                    if fail:raise KeyboardInterrupt('synthetic durable interruption')
                def load(p,h):
                    if mode=='target_load' and p.parent.name=='SZ002326':raise OSError('synthetic buffer failure')
                    return bound(p,h)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=persist),patch.object(source,'bound_body',side_effect=load),self.assertRaises(OSError if mode=='target_load' else KeyboardInterrupt):
                    source.run(base,base,base/'unused','sha')
                out=base/source.OUTPUT;terminal=source.read(out/'terminal.json')
                if mode=='control_row':self.assertEqual(terminal['control_rows_completed'],1)
                if mode=='target_row':self.assertEqual(terminal['target_rows_completed'],1)
                called=[]
                def body_loader(code):called.append(code);return (base/source.OPAQUE/code/'body.bin').read_bytes()
                facts=checker.verify_projection_artifacts(out,DAYS,raw(),terminal,body_loader)
                self.assertFalse(facts['complete'])
                if mode in ('target_load','control_row'):self.assertNotIn('SZ002326',called)
    def test_post_publication_input_row_or_terminal_mutation_never_returns_success(self):
        from scripts import recover_low_operating_quotes_pre2026 as inherited
        for mode in ('input','row','terminal'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                base=Path(t);known=self.fixture(base);real=inherited.os.replace;mutated=[]
                def replace(a,b):
                    real(a,b)
                    if Path(b).name=='terminal.json' and not mutated:
                        mutated.append(True)
                        p=base/source.OPAQUE/'SH600118/body.bin' if mode=='input' else Path(b) if mode=='terminal' else base/source.OUTPUT/'rows/SH600118'/f'{DAYS[0]}.json'
                        p.write_bytes(b'changed')
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(inherited.os,'replace',side_effect=replace),self.assertRaises(ValueError):
                    source.run(base,base,base/'unused','sha')
                self.assertFalse(source.read(base/source.OUTPUT/'terminal.json')['complete'])
