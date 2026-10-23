from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json,tempfile,unittest,struct
from unittest.mock import patch
from tests.test_low_operating_tencent_decode import DAYS,raw
try:
    from stock_rsi import yahoo_history as history
    from scripts import decode_low_operating_yahoo_pre2026 as source
except ImportError:history=source=None

def fixture(code='SH600118',days=DAYS,change=None):
    q={k:[10.,10.] for k in ('open','close','high','low')};q['volume']=[200,200]
    result={'meta':{'symbol':'600118.SS' if code=='SH600118' else '002326.SZ','exchangeTimezoneName':'Asia/Shanghai','regularMarketPrice':'FUTURE_POISON'},
        'timestamp':[int(datetime.fromisoformat(d+'T09:30:00').replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()) for d in days],
        'indicators':{'quote':[q],'adjclose':[{'adjclose':['FUTURE_POISON']}]},'events':{'poison':'FUTURE_POISON'}}
    if change:change(result)
    return json.dumps({'chart':{'error':None,'result':[result]}}).encode()

class YahooDecodeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(history,'selective Yahoo decoder missing');self.assertIsNotNone(source)
    def test_ignored_metadata_and_adjusted_values_remain_opaque(self):
        loads=json.loads
        def checked(v,*a,**kw):self.assertNotIn(b'FUTURE_POISON',v if isinstance(v,bytes) else v.encode());return loads(v,*a,**kw)
        with patch.object(history.json,'loads',side_effect=checked):rows=history.decode(fixture(),'SH600118',DAYS)
        self.assertEqual([r['date'] for r in rows],DAYS);self.assertEqual(rows[0]['volume_shares'],'200')
        self.assertEqual(rows[0]['source_tokens']['open'],'10.0')
    def test_all_dates_are_checked_before_any_quote_scalar(self):
        b=fixture(days=[DAYS[0],'2026-01-02'],change=lambda r:r['indicators']['quote'][0]['open'].__setitem__(0,'PRICE_POISON'))
        seen=[]
        with patch.object(history,'price',side_effect=lambda v:seen.append(v)),self.assertRaises(ValueError):history.decode(b,'SH600118',DAYS)
        self.assertEqual(seen,[])
    def test_exact_cents_and_unique_native_f32_cell_without_factor_or_tolerance(self):
        self.assertEqual(history.price(b'25.57'),'25.57')
        f=struct.unpack('<f',struct.pack('<f',25.57))[0]
        self.assertEqual(history.price(repr(f).encode()),'25.57')
        for token in (b'10.000000000000000000000000001',b'10.001',b'10.00390625',b'NaN',b'null',b'-10',b'1e1000000'):
            with self.subTest(token=token),self.assertRaises(ValueError):history.price(token)
    def test_identity_dates_and_quote_array_lengths_are_strict(self):
        mutations=[lambda r:r['meta'].__setitem__('symbol','OTHER'),lambda r:r['meta'].__setitem__('exchangeTimezoneName','UTC'),
            lambda r:r['timestamp'].__setitem__(1,r['timestamp'][0]),lambda r:r['timestamp'].__setitem__(0,True),
            lambda r:r['timestamp'].__setitem__(0,r['timestamp'][0]+1),lambda r:r['indicators']['quote'][0]['open'].pop(),
            lambda r:r['indicators']['quote'][0]['volume'].__setitem__(0,1.5),lambda r:r['indicators']['quote'][0]['open'].__setitem__(0,None)]
        for change in mutations:
            with self.subTest(change=change),self.assertRaises(ValueError):history.decode(fixture(change=change),'SH600118',DAYS)
    def test_complete_control_failure_prevents_any_target_load(self):
        original=raw();original[0]['volume']='201';seen=[]
        result=source.evaluate(fixture(),lambda:seen.append(True),DAYS,original)
        self.assertFalse(result['control']['price_volume_gate_passed']);self.assertEqual(seen,[])
    def setup_run(self,base):
        known={}
        for code in ('SH600118','SZ002326'):
            p=base/source.OPAQUE/code/'body.bin';p.parent.mkdir(parents=True);p.write_bytes(fixture(code));known[str(p.resolve())]=source.sha(p)
        return known
    def test_run_and_shared_projector_audit_preserve_exact_selected_components(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):result=source.run(b,b,b/'unused','sha')
            self.assertTrue(result['complete'])
            facts=source.verify_artifacts(b/source.OUTPUT,DAYS,raw(),result,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertEqual(len(facts['target_rows']),2)
    def test_native_durable_row_failure_audits_only_completed_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b);real=source.persist
            def save(out,n,v,outputs):
                real(out,n,v,outputs)
                if n=='rows/SH600118/'+DAYS[0]+'.json':raise KeyboardInterrupt('durable interruption')
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=save),self.assertRaises(KeyboardInterrupt):source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT;result=source.read(out/'terminal.json');self.assertEqual(result['control_rows_completed'],1)
            facts=source.verify_artifacts(out,DAYS,raw(),result,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertEqual(len(facts['control_rows']),1);self.assertFalse(facts['complete'])
    def test_mutation_at_marker_or_target_load_prevents_target_decode(self):
        for at in ('marker','load'):
            with self.subTest(at=at),tempfile.TemporaryDirectory() as t:
                b=Path(t);known=self.setup_run(b);real=source.persist;bound=source.bound_body;decode=history.decode;seen=[]
                def corrupt():(b/source.OPAQUE/'SH600118/body.bin').write_bytes(b'changed')
                def save(out,n,v,outputs):
                    real(out,n,v,outputs)
                    if at=='marker' and n=='target-started.json':corrupt()
                def load(p,h):
                    v=bound(p,h)
                    if at=='load' and p.parent.name=='SZ002326':corrupt()
                    return v
                def tracked(data,code,*a,**kw):seen.append(code);return decode(data,code,*a,**kw)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=save),patch.object(source,'bound_body',side_effect=load),patch.object(source,'decode',side_effect=tracked),self.assertRaises(ValueError):source.run(b,b,b/'unused','sha')
                self.assertNotIn('SZ002326',seen)
    def test_corrupt_control_aggregate_or_prefix_is_rejected_before_target_read(self):
        for name in ('control-rows.json','rows/SH600118/'+DAYS[0]+'.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
                b=Path(t);known=self.setup_run(b)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):result=source.run(b,b,b/'unused','sha')
                out=b/source.OUTPUT;(out/name).write_text('{}');seen=[]
                def load(c):seen.append(c);return (b/source.OPAQUE/c/'body.bin').read_bytes()
                with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,raw(),result,load)
                self.assertNotIn('SZ002326',seen)
    def test_prior_acquisition_proof_cannot_be_rebased_before_freeze(self):
        with patch.object(source,'sha',return_value='changed'),patch.object(source,'read',side_effect=AssertionError('untrusted proof read')):
            with self.assertRaises(ValueError):source.context(Path('/unused'),Path('/unused'))
    def test_error_aggregate_cannot_force_read_beyond_durable_target_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b);p=b/source.OPAQUE/'SZ002326/body.bin'
            p.write_bytes(fixture('SZ002326',change=lambda r:r['indicators']['quote'][0]['open'].__setitem__(1,'UNFINISHED_POISON')));known[str(p.resolve())]=source.sha(p)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),self.assertRaises(ValueError):source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT;terminal=source.read(out/'terminal.json');self.assertEqual(terminal['target_rows_completed'],1)
            (out/'target-rows.json').write_text(json.dumps([source.read(out/'rows/SZ002326'/ (DAYS[0]+'.json'))]))
            real=history.price;seen=[]
            def checked(v):seen.append(v);return real(v)
            with patch.object(history,'price',side_effect=checked),self.assertRaises(ValueError):
                source.verify_artifacts(out,DAYS,raw(),terminal,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertNotIn(b'"UNFINISHED_POISON"',seen)
