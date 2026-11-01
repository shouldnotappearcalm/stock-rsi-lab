from decimal import Decimal
import json,struct,tempfile
from pathlib import Path
import unittest
from scripts import prepare_blogger_2026_data as data
from scripts import run_blogger_2026 as run
from scripts.audit_blogger_2026 import reference_flags
from scripts.audit_published_strategies_2026 import independent_periods


class BloggerForwardTests(unittest.TestCase):
    def terminal(self):
        return {'passed_numerical_two_year_screen':list(run.base.NAMES),'average_exposure_is_hard_gate':False,
                'results':{'40/'+n:{'2024_return_pct':1.,'2025_return_pct':1.,'average_exposure_pct':1.,'unverified_held_marks':0} for n in run.base.NAMES}}

    def test_all_three_selected_by_positive2024_2025_not_future_outcomes(self):
        for value in (-100.,1000.):
            t=self.terminal()
            for m in t['results'].values():m['2026_return_pct']=value
            run.validate_selection(t)
        self.assertFalse(run.PROFILE['average_exposure_is_hard_gate'])

    def test_no_missing_candidate_invented_exposure_gate_or_failed_year(self):
        for change in ({'passed_numerical_two_year_screen':['fengji20']},{'average_exposure_is_hard_gate':True}):
            with self.assertRaises(ValueError):run.validate_selection({**self.terminal(),**change})
        t=self.terminal();t['results']['40/plus2047']['2025_return_pct']=0
        with self.assertRaises(ValueError):run.validate_selection(t)

    def test_parse_rejects_raw_in_place_of_hfq_and_future_quotes(self):
        body={'code':0,'data':{'sh518880':{'day':[['2026-10-30','10','10','10','10','100']]}}}
        self.assertEqual(len(data.parse(body,'SH518880','raw',['2026-10-30'])['bars']),1)
        with self.assertRaises(ValueError):data.parse(body,'SH518880','hfq',['2026-10-30'])
        body['data']['sh518880']['day'][0][0]='2026-11-02'
        with self.assertRaises(ValueError):data.parse(body,'SH518880','raw',['2026-11-02'])

    def test_source_overlap_cannot_be_scaled_overwritten_or_skipped(self):
        a={'instrument':'SH518880','mode':'raw','bars':[{'date':'2025-12-01','close':'10.000'}]}
        b={**a,'bars':[{'date':'2025-12-01','close':'10.0'},{'date':'2026-01-05','close':'11.000'}]}
        full,count=data.merge(a,b,['2025-12-01','2026-01-05'])
        self.assertEqual(count,1);self.assertEqual(full['bars'][0],a['bars'][0])
        with self.assertRaises(ValueError):data.merge(a,{**b,'bars':[{**b['bars'][0],'close':'10.001'},b['bars'][1]]},['2025-12-01','2026-01-05'])
        with self.assertRaises(ValueError):data.merge(a,{**b,'bars':b['bars'][1:]},['2025-12-01','2026-01-05'])

    def test_raw_reference_keeps_literal_limit_instead_of_widening_band(self):
        self.assertEqual(reference_flags(Decimal('9.908'),Decimal('11.009'),'SH518880'),(0,1))
        with self.assertRaises(ValueError):reference_flags(Decimal('9.907'),Decimal('11.009'),'SH518880')
        self.assertEqual(reference_flags(Decimal('8.000'),Decimal('10.000'),'SZ159915'),(0,1))

    def test_calendar_requires_real_complete_october_and_next_session(self):
        good={'fields':['calendar_date','is_trading_day'],'error_code':'0','rows':[['2023-07-03','1'],['2026-10-30','1'],['2026-10-31','0'],['2026-11-02','1']]}
        sessions,next_day=data.calendar(good);self.assertEqual(next_day,'2026-11-02');self.assertNotIn('2026-10-31',sessions)
        with self.assertRaises(ValueError):data.calendar({**good,'rows':good['rows'][:-1]})
        with self.assertRaises(ValueError):data.calendar({**good,'rows':good['rows'][::-1]})

    def test_forward_year_starts_from_actual2025_nav_without_account_reset(self):
        rows=[{'session':'2024-12-31','account_value':'1200000','stock_value':'600000','cost':'0','orders':'0'},
              {'session':'2025-12-31','account_value':'1500000','stock_value':'750000','cost':'0','orders':'0'},
              {'session':'2026-01-05','account_value':'1350000','stock_value':'675000','cost':'5','orders':'1'},
              {'session':'2026-10-30','account_value':'1650000','stock_value':'825000','cost':'5','orders':'1'}]
        result=run.per_year(rows)['2026'];independent=independent_periods(rows)['2026']
        self.assertEqual(result['baseline_CNY'],1500000);self.assertAlmostEqual(result['net_return_pct'],10.)
        self.assertAlmostEqual(result['max_drawdown_pct'],-10.)
        for k,v in independent.items():self.assertAlmostEqual(result[k],v)

    def test_append_preserves_every_original_feature_byte(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);old=root/'old';packets={};references={};sessions=['2025-12-31','2026-01-05']
            for c in data.FUNDS+data.INDEXES:
                folder=old/'features'/c.lower();folder.mkdir(parents=True)
                original={'open':1,'high':1,'low':1,'close':1,'factor':.1,'volume':1000,'change':0,'buyblock':0,'sellblock':0}
                for f,v in original.items():(folder/(f+'.day.bin')).write_bytes(struct.pack('<2f',0,v))
                for mode in (('raw','hfq') if c in data.FUNDS else ('raw',)):
                    packets[c+'-'+mode]={'bars':[dict(date=d,open=p,high=p,low=p,close=p,volume_provider_units='100') for d,p in zip(sessions,['10','9'])]}
                if c in data.FUNDS:references[c,'2026-01-05']='10'
            output=root/'new';prefix=data.build(output,packets,sessions,'2026-01-06',old,references)
            self.assertEqual(len(prefix),72)
            for f in old.rglob('*.bin'):
                self.assertEqual((output/f.relative_to(old)).read_bytes()[:8],f.read_bytes())
            self.assertEqual(struct.unpack('<3f',(output/'features/sh518880/sellblock.day.bin').read_bytes())[-1],1)
            (old/'features/sh518880/close.day.bin').write_bytes(struct.pack('<2f',0,999))
            with self.assertRaisesRegex(ValueError,'prefix changed'):data.build(root/'bad',packets,sessions,'2026-01-06',old,references)


if __name__=='__main__':unittest.main()
