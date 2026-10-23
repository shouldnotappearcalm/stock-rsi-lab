import copy
from fractions import Fraction
from pathlib import Path
import struct
import tempfile
import unittest
try:
    from stock_rsi import float32_quote_bounds as bounds
    from scripts import recover_low_operating_quotes_pre2026 as source
    from scripts import audit_low_operating_quote_recovery_pre2026 as audit
except ImportError:
    bounds=source=audit=None

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
DAYS=['2024-01-02','2024-01-03']
def packets(volume='200'):
    return {'SH600118':{'instrument':'SH600118','window':['2023-12-29','2025-12-31'],
      'bars':[{'date':d,'open':'10','high':'10','low':'10','close':'10','volume':volume,'tradestatus':'1','isST':'1'} for d in DAYS]}}
def getter(code,field,day):return f32(.1) if field=='factor' else f32(2000) if field=='volume' else f32(1)


class QuoteRecoveryTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(bounds,'exact source bounds missing');self.assertIsNotNone(source);self.assertIsNotNone(audit)
    def test_exact_cent_uses_whole_quantization_cell_including_subnormal(self):
        x=bounds.cent_price(f32(1),f32(.1));self.assertEqual(x['status'],'UNIQUE_POSITIVE_CENT');self.assertEqual(x['value'],'10.00')
        lo,hi=bounds.cell(f32(2**-149));self.assertEqual(lo,Fraction(1,2**150));self.assertEqual(hi,Fraction(3,2**150))
        self.assertEqual(bounds.cell(0.,allow_zero=True)[0],0)
    def test_no_cent_ambiguous_invalid_and_unrepresentable_inputs_never_round(self):
        self.assertEqual(bounds.cent_price(f32(1.234),f32(1))['status'],'NO_CENT_PRICE')
        self.assertEqual(bounds.cent_price(f32(100000000),f32(1))['status'],'AMBIGUOUS_CENT_PRICE')
        for value in (float('nan'),float('inf'),-1.,0.,1.0000000001):
            with self.subTest(v=value),self.assertRaises(ValueError):bounds.cell(value)
    def test_volume_interval_lower_bound_is_conservative_and_unit_hypotheses_explicit(self):
        lo,hi=bounds.volume_interval(f32(2000),f32(.1),1);self.assertLessEqual(lo,200);self.assertGreaterEqual(hi,200)
        r=source.controls(packets(),DAYS,getter);self.assertEqual(r['identified_volume_scale'],1)
        self.assertEqual(source.controls(packets('20000'),DAYS,getter)['identified_volume_scale'],100)
        self.assertIsNone(source.controls(packets('300'),DAYS,getter)['identified_volume_scale'])
    def test_one_control_failure_prevents_any_missing_code_read(self):
        p=packets();p['SH600118']['bars'][1]['close']='10.01';calls=[]
        def get(code,field,day):calls.append(code);return getter(code,field,day)
        r=source.recover(p,DAYS,get)
        self.assertFalse(r['controls']['price_gate_passed']);self.assertFalse(r['target_quote_values_decoded']);self.assertNotIn('SZ002326',calls)
    def test_all_trading_fields_including_ST_count_and_nontrading_is_not_invented(self):
        p=packets();p['SH600118']['bars'][1]['tradestatus']='0';before=copy.deepcopy(p)
        r=source.controls(p,DAYS,getter);self.assertTrue(r['price_gate_passed']);self.assertEqual(r['price_cells_checked'],4)
        self.assertEqual(r['nontrading_rows_excluded'],1);self.assertEqual(p,before)
        p['SH600118']['bars'][0]['tradestatus']='0';self.assertFalse(source.controls(p,DAYS,getter)['price_gate_passed'])
    def test_projection_preserves_unknown_state_and_unproved_volume_separately(self):
        r=source.recover(packets('300'),DAYS,getter)
        self.assertTrue(r['target_quote_values_decoded']);self.assertFalse(r['source_projection_complete'])
        for row in r['projection']:
            self.assertEqual(row['prices']['open']['value'],'10.00');self.assertIsNone(row['volume_lower_shares'])
            self.assertNotIn('isST',row);self.assertNotIn('preclose',row);self.assertNotIn('amount',row)
    def test_future_feature_cells_cannot_change_earlier_read_and_bad_extent_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.bin';p.write_bytes(struct.pack('<3f',0,1,2));self.assertEqual(source.read32(p,0,2),1)
            p.write_bytes(struct.pack('<3f',0,1,float('inf')));self.assertEqual(source.read32(p,0,2),1)
            with self.assertRaises(ValueError):source.read32(p,0,1)
            p.write_bytes(struct.pack('<2f',.5,1))
            with self.assertRaises(ValueError):source.read32(p,0,2)
    def test_independent_bit_arithmetic_reconstructs_the_same_unique_ticks(self):
        for value,factor in ((1.,f32(.1)),(f32(1.234),1.),(f32(1e8),1.)):
            bits=lambda x:struct.unpack('<I',struct.pack('<f',x))[0]
            self.assertEqual(bounds.cent_price(value,factor),audit.cent_from_bits(bits(value),bits(factor)))
    def test_late_input_or_output_mutation_rejects_completion_and_keeps_failure(self):
        from unittest.mock import patch
        for mode in ('input','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                root=Path(t);original=root/'source';original.write_text('immutable');out=root/'out';out.mkdir();source.write_once(out/'facts.json',{'kept':True})
                real=source.write_once
                def write(p,v):
                    real(p,v)
                    if p.name=='.terminal-pending.json':(original if mode=='input' else out/'facts.json').write_text('changed')
                with patch.object(source,'write_once',side_effect=write),self.assertRaises(ValueError):
                    source.finish(out,{'complete':True},{str(original):source.sha(original)})
                self.assertFalse(source.read(out/'terminal.json')['complete'])
