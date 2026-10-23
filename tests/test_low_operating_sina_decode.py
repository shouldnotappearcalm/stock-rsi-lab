from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from tests.test_low_operating_tencent_decode import DAYS,raw
try:
    from stock_rsi import sina_history as history
    from scripts import decode_low_operating_sina_pre2026 as source
except ImportError:history=source=None

def fixture(code='SH600118',change=None):
    rows=[{'day':'2023-12-28','open':{'poison':'EARLIER_POISON'}}]
    rows += [{'day':d,'open':'10.000','close':'10','high':'10.00','low':'10.00','volume':'200','ignored':'EXTRA_POISON'} for d in DAYS]
    rows += [{'day':'2026-01-02','volume':{'poison':'FUTURE_POISON'}}]
    if change:change(rows)
    return json.dumps(rows).encode()

class SinaDecodeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(history,'native selective Sina decoder missing');self.assertIsNotNone(source)
    def test_both_outside_quote_tails_and_extras_remain_opaque(self):
        loads=json.loads
        def checked(v,*a,**kw):self.assertNotIn(b'POISON',v if isinstance(v,bytes) else v.encode());return loads(v,*a,**kw)
        with patch.object(history.json,'loads',side_effect=checked):rows=history.decode(fixture(),'SH600118',DAYS)
        self.assertEqual([r['date'] for r in rows],DAYS);self.assertEqual([r['source_index'] for r in rows],[1,2])
        self.assertEqual(rows[0]['open'],'10.00');self.assertEqual(rows[0]['volume_shares'],'200');self.assertEqual(rows[0]['source_tokens']['open'],'"10.000"')
    def test_all_dates_checked_before_any_quote_with_duplicate_or_offcalendar(self):
        for day in (DAYS[0],'2024-01-06','2024-1-3'):
            seen=[]
            with self.subTest(day=day),patch.object(history,'price',side_effect=lambda v:seen.append(v)),self.assertRaises(ValueError):
                history.decode(fixture(change=lambda rows:rows[2].update(day=day)),'SH600118',DAYS)
            self.assertEqual(seen,[])
    def test_bad_scalar_values_do_not_become_valid_via_rounding_or_fill(self):
        for field,value in [('open','10.001'),('open','10.00000000000000000000000001'),('open','1e-1000100'),('open',None),('volume','200.1'),('volume','NaN'),('volume','1e1000000'),('high','9')]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):history.decode(fixture(change=lambda rows:rows[1].update({field:value})),'SH600118',DAYS)
    def test_exact_control_failure_prevents_any_target_loader(self):
        original=raw();original[0]['volume']='201';seen=[]
        result=source.evaluate(fixture(),lambda:seen.append(True),DAYS,original)
        self.assertFalse(result['control']['price_volume_gate_passed']);self.assertEqual(seen,[])
    def setup_run(self,base):
        known={}
        for code in ('SH600118','SZ002326'):
            p=base/source.OPAQUE/code/'body.bin';p.parent.mkdir(parents=True);p.write_bytes(fixture(code));known[str(p.resolve())]=source.sha(p)
        return known
    def test_full_run_shared_audit_and_date_only_aggregate_counts(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(b,b,b/'unused','sha')
            facts=source.verify_artifacts(b/source.OUTPUT,DAYS,raw(),terminal,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertTrue(facts['complete']);self.assertEqual(len(facts['target_rows']),2)
    def test_mutation_at_marker_or_load_prevents_target_decoder(self):
        for at in ('marker','load'):
            with self.subTest(at=at),tempfile.TemporaryDirectory() as t:
                b=Path(t);known=self.setup_run(b);persist=source.persist;bound=source.bound_body;decode=history.decode;seen=[]
                def corrupt():(b/source.OPAQUE/'SH600118/body.bin').write_bytes(b'changed')
                def save(out,n,v,outputs):
                    persist(out,n,v,outputs)
                    if at=='marker' and n=='target-started.json':corrupt()
                def load(p,h):
                    v=bound(p,h)
                    if at=='load' and p.parent.name=='SZ002326':corrupt()
                    return v
                def tracked(data,code,*a,**kw):seen.append(code);return decode(data,code,*a,**kw)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=save),patch.object(source,'bound_body',side_effect=load),patch.object(source,'decode',side_effect=tracked),self.assertRaises(ValueError):source.run(b,b,b/'unused','sha')
                self.assertNotIn('SZ002326',seen)
    def test_native_durable_prefix_is_audited_without_finishing_failed_quote(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b);p=b/source.OPAQUE/'SZ002326/body.bin'
            p.write_bytes(fixture(change=lambda rows:rows[2].update(open='UNFINISHED_POISON')));known[str(p.resolve())]=source.sha(p)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),self.assertRaises(ValueError):source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT;terminal=source.read(out/'terminal.json');self.assertEqual(terminal['target_rows_completed'],1)
            real=history.price;seen=[]
            def checked(v):seen.append(v);return real(v)
            with patch.object(history,'price',side_effect=checked):facts=source.verify_artifacts(out,DAYS,raw(),terminal,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertFalse(facts['complete']);self.assertNotIn(b'"UNFINISHED_POISON"',seen)
    def test_corrupt_control_or_impossible_stage_blocks_audit_target_reads(self):
        for mode in ('row','aggregate','missing','stage'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                b=Path(t);known=self.setup_run(b)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(b,b,b/'unused','sha')
                out=b/source.OUTPUT
                if mode=='row':(out/'rows/SH600118'/ (DAYS[0]+'.json')).write_text('{}')
                elif mode=='aggregate':(out/'control-rows.json').write_text('[]')
                elif mode=='missing':(out/'control-rows.json').unlink()
                else:terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',complete=False,error_type='ValueError',error='synthetic',failed_stage='CONTROL',failed_row_index=2)
                seen=[]
                def load(c):seen.append(c);return (b/source.OPAQUE/c/'body.bin').read_bytes()
                with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,raw(),terminal,load)
                self.assertNotIn('SZ002326',seen)
    def test_control_aggregate_persistence_failure_precedes_any_target_decode(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b);real=source.persist
            def interrupted(out,n,v,outputs):
                real(out,n,v,outputs)
                if n=='control-rows.json':raise KeyboardInterrupt('durable aggregate interruption')
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT;terminal=source.read(out/'terminal.json')
            self.assertFalse(terminal['target_decoder_invoked']);self.assertEqual(terminal['target_rows_completed'],0)
            facts=source.verify_artifacts(out,DAYS,raw(),terminal,lambda c:(b/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertFalse(facts['complete']);self.assertEqual(len(facts['control_rows']),2)
    def test_error_trace_with_target_evidence_requires_control_aggregate(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT;(out/'control-rows.json').unlink()
            terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',complete=False,error_type='ValueError',error='synthetic',failed_stage='TARGET',failed_row_index=2)
            seen=[]
            def load(c):seen.append(c);return (b/source.OPAQUE/c/'body.bin').read_bytes()
            with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,raw(),terminal,load)
            self.assertNotIn('SZ002326',seen)
    def test_invalid_rejected_publication_receipt_blocks_target_reads(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);known=self.setup_run(b)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(b,b,b/'unused','sha')
            out=b/source.OUTPUT
            terminal.update(status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',complete=False,error_type='ValueError',error='synthetic',failed_stage='TARGET',failed_row_index=2,
                rejected_terminal_sha256={'unexpected.txt':'bad'})
            seen=[]
            def load(c):seen.append(c);return (b/source.OPAQUE/c/'body.bin').read_bytes()
            with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,raw(),terminal,load)
            self.assertNotIn('SZ002326',seen)
