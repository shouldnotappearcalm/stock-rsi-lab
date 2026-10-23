from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from tests.test_low_operating_tencent_decode import DAYS,row,body,raw
from stock_rsi.tencent_history import JsonSlices,decode
try:
    from stock_rsi import tencent_window as window
    from scripts import run_low_operating_tencent_window_pre2026 as source
except ImportError:window=source=None

def padded(code='SH600118'):
    earlier=['2023-12-28',{'opaque':'EARLIER_POISON'}]
    return body([earlier]+[row(d) for d in DAYS],code=code)


class TencentWindowTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(window,'date window adapter missing');self.assertIsNotNone(source)
    def test_earlier_values_stay_opaque_and_kept_row_bytes_are_unchanged(self):
        original=padded();loads=json.loads
        def scalar(b,*a,**kw):
            self.assertNotIn(b'POISON',b if isinstance(b,bytes) else b.encode());return loads(b,*a,**kw)
        with patch.object(window.json,'loads',side_effect=scalar):prepared,receipt=window.prepare(original,'SH600118',DAYS)
        self.assertEqual(receipt['earlier_count'],1);self.assertEqual(receipt['kept_count'],2)
        before=JsonSlices.items(JsonSlices(original).path(('data','sh600118','day')))
        after=JsonSlices.items(JsonSlices(prepared).path(('data','sh600118','day')))
        self.assertEqual(after,before[1:]);self.assertEqual(receipt['records'][1]['row_sha256'],hashlib.sha256(before[1]).hexdigest())
        self.assertEqual([r['date'] for r in decode(prepared,'SH600118',DAYS)],DAYS)
    def test_future_offcalendar_duplicate_or_reversed_dates_fail_before_numeric_decode(self):
        for rows in ([row(),row('2026-01-02')],[row('2024-01-06')],[row(),row()],[row(),row('2023-12-28')]):
            with self.subTest(count=len(rows)),self.assertRaises(ValueError):window.prepare(body(rows),'SH600118',DAYS)
    def test_invalid_kept_price_is_not_filtered_or_repaired(self):
        r=row();r[1]='NaN';prepared,receipt=window.prepare(body([r]),'SH600118',DAYS)
        self.assertEqual(receipt['kept_count'],1)
        with self.assertRaises(ValueError):decode(prepared,'SH600118',DAYS)
    def test_partial_date_receipt_does_not_scan_or_decode_unfinished_row(self):
        original=body([row('2023-12-28'),row(),row('2026-01-02')])
        try:window.prepare(original,'SH600118',DAYS)
        except ValueError as exc:records=exc.window_records
        else:self.fail('future row admitted')
        self.assertEqual(len(records),2)
        window.verify_records(original,'SH600118',DAYS,records,complete=False)
    def test_control_failure_prevents_even_target_preparation(self):
        r=raw();r[0]['close']='10.01';called=[]
        result=source.experiment(padded(),lambda:called.append(True),DAYS,r)
        self.assertFalse(result['control']['price_volume_gate_passed']);self.assertEqual(called,[])
    def fixture(self,base):
        known={}
        for code in ('SH600118','SZ002326'):
            p=base/source.OPAQUE/code/'body.bin';p.parent.mkdir(parents=True);p.write_bytes(padded(code));known[str(p.resolve())]=source.sha(p)
        return known
    def test_source_and_separate_projector_verify_full_window_artifacts(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);known=self.fixture(base)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):result=source.run(base,base,base/'unused','sha')
            self.assertTrue(result['complete']);self.assertEqual(result['target_rows_completed'],2)
            facts=source.verify_artifacts(base/source.OUTPUT,DAYS,raw(),result,lambda c:(base/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertTrue(facts['complete']);self.assertEqual(facts['window_counts']['SZ002326'],{'earlier':1,'kept':2})
    def test_mutation_during_target_preparation_blocks_numeric_target_decode(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);known=self.fixture(base);real=source.persist;calls=[];evaluate=source.legacy.evaluate
            def persist(out,name,value,outputs):
                real(out,name,value,outputs)
                if name=='window-SZ002326.json':(base/source.OPAQUE/'SH600118/body.bin').write_bytes(b'changed')
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=persist),self.assertRaises(ValueError):
                source.run(base,base,base/'unused','sha')
            self.assertFalse(source.read(base/source.OUTPUT/'terminal.json')['target_decoder_invoked'])
    def test_target_preparation_failure_retains_partial_dates_without_numeric_reads(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);known=self.fixture(base);target=base/source.OPAQUE/'SZ002326/body.bin'
            target.write_bytes(body([row('2023-12-28'),row('2026-01-02')],code='SZ002326'));known[str(target.resolve())]=source.sha(target)
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),self.assertRaises(ValueError):source.run(base,base,base/'unused','sha')
            out=base/source.OUTPUT;terminal=source.read(out/'terminal.json');self.assertFalse(terminal['target_decoder_invoked'])
            facts=source.verify_artifacts(out,DAYS,raw(),terminal,lambda c:(base/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertFalse(facts['complete']);self.assertEqual(facts['partial_window_records']['SZ002326'],1)
    def test_native_row_interruption_preserves_and_audits_durable_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);known=self.fixture(base);real=source.persist
            def persist(out,name,value,outputs):
                real(out,name,value,outputs)
                if name=='rows/SH600118/'+DAYS[0]+'.json':raise KeyboardInterrupt('after durable row')
            with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)),patch.object(source,'persist',side_effect=persist),self.assertRaises(KeyboardInterrupt):source.run(base,base,base/'unused','sha')
            out=base/source.OUTPUT;terminal=source.read(out/'terminal.json');self.assertEqual(terminal['control_rows_completed'],1)
            facts=source.verify_artifacts(out,DAYS,raw(),terminal,lambda c:(base/source.OPAQUE/c/'body.bin').read_bytes())
            self.assertFalse(facts['complete']);self.assertEqual(len(facts['control_rows']),1)
    def test_audit_rejects_control_corruption_before_any_target_read(self):
        for corruption in ('row','agreement','aggregate'):
            with self.subTest(corruption=corruption),tempfile.TemporaryDirectory() as t:
                base=Path(t);known=self.fixture(base)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(base,base,base/'unused','sha')
                out=base/source.OUTPUT;original=raw()
                if corruption=='row':(out/'rows/SH600118'/ (DAYS[0]+'.json')).write_text('{}')
                elif corruption=='aggregate':(out/'control-rows.json').write_text('[]')
                else:original[0]['close']='10.01'
                reads=[]
                def load(c):reads.append(c);return (base/source.OPAQUE/c/'body.bin').read_bytes()
                with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,original,terminal,load)
                self.assertNotIn('SZ002326',reads)
    def test_audit_rejects_impossible_target_lifecycle_before_target_read(self):
        for missing in ('preparation','marker'):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as t:
                base=Path(t);known=self.fixture(base)
                with patch.object(source,'authenticate',return_value=({},DAYS,raw(),known)):terminal=source.run(base,base,base/'unused','sha')
                out=base/source.OUTPUT
                terminal.update(error_type='ValueError',error='synthetic',status='SELECTIVE_DECODE_FAILURE_PREFIX_RETAINED',
                    complete=False,failed_stage='TARGET',failed_row_index=0,target_rows_completed=0)
                for p in (out/'rows/SZ002326').glob('*.json'):p.unlink()
                (out/'target-rows.json').unlink()
                if missing=='preparation':
                    for n in ('window-SZ002326.json','prepared-SZ002326.bin'):(out/n).unlink()
                else:
                    (out/'target-started.json').unlink();terminal['target_decoder_invoked']=False
                reads=[]
                def load(c):reads.append(c);return (base/source.OPAQUE/c/'body.bin').read_bytes()
                with self.assertRaises(ValueError):source.verify_artifacts(out,DAYS,raw(),terminal,load)
                self.assertNotIn('SZ002326',reads)
