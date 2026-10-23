import copy
from datetime import date
import unittest
try:
    from stock_rsi import operating_monthly as signal
except ImportError:
    signal=None
from stock_rsi import annual_operating as op
from tests.test_operating_factor import source_case


def fixture():
    class Quotes:
        calendar=tuple(date.fromisoformat(d) for d in ('2023-12-29','2024-01-02','2024-01-31','2024-02-01','2025-12-31'))
        def __init__(self):self.missing=set();self.reads=[]
        def value(self,code,field,day):
            if day!='2023-12-29':raise AssertionError('future factor quote')
            self.reads.append((code,field,day));return None if code in self.missing else 1.
    docs={};cases={};old={};ids={};rows=[]
    for i in range(110):
        d,c,o,a=source_case(i,legacy=i%2==0);k=d['capture_key'];docs[k]=d;cases[k]=c;old[k]=o;ids.update(a)
        rows.append({'instrument':d['instrument'],'industry_status':'NONFINANCIAL_IN_SOURCE_VINTAGE','annual_status':'ORIGINAL_SOURCE_STATUS_RETAINED',
          'selected_capture_key':k,'selected_source_sha256':d['source_sha256'],'latest_fiscal_year':2022,'latest_publication_day':d['day'],
          'effective_source_status':c['effective_source_status'],'effective_record_id':c['effective_record_id']})
    cohort=[r['instrument'] for r in rows];members={c:[('2020-01-01','2025-12-31')] for c in cohort}
    views={'2024-01-02':{'as_of':'2023-12-29T07:05:00+00:00','visibility_mode':op.RECONSTRUCTED,'cohort_count':110,'classifications':rows}}
    return Quotes(),members,cohort,views,docs,cases,old,ids


class OperatingMonthlyTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(signal,'operating monthly targets missing')
    def build(self,f,**kw):return signal.build_targets(*f[:5],f[5].__getitem__,f[6].__getitem__,f[7],end='2024-01-31',**kw)

    def test_top_bottom_and_equal_use_exact_operating_ratio_prior_close_and_95percent(self):
        f=fixture();targets,receipts=self.build(f);codes=f[2]
        self.assertEqual(list(targets[signal.PRIMARY]['2024-01-02']['weights']),codes[::-1][:11])
        self.assertEqual(list(targets[signal.LOW_CONTROL]['2024-01-02']['weights']),codes[:11])
        self.assertEqual(list(targets['eligible_equal_weight']['2024-01-02']['weights']),codes)
        self.assertAlmostEqual(sum(targets[signal.PRIMARY]['2024-01-02']['weights'].values()),.95)
        self.assertEqual(receipts[0]['ranked_source'][codes[-1]]['score_fraction'],'36/25')
        self.assertEqual({d for _,_,d in f[0].reads},{'2023-12-29'});self.assertEqual(receipts[0]['eligible'],110)

    def test_latest_failures_ambiguity_stale_unknown_membership_and_missing_quote_remain_excluded(self):
        f=fixture();rows=f[3]['2024-01-02']['classifications'];rows[0].update(effective_source_status='STILL_UNSUPPORTED',effective_record_id=None)
        rows[1].pop('selected_capture_key');rows[1]['annual_status']='AMBIGUOUS_LATEST_SAME_DAY_EDITIONS'
        rows[2]['industry_status']='NOT_IN_SOURCE_VINTAGE';rows[3]['latest_fiscal_year']=2021
        f[1][f[2][4]]=[('2024-01-02','2025-12-31')];f[0].missing.add(f[2][5]);f[5]['older-unused']=object()
        _,receipt=self.build(f);counts=receipt[0]['admission_counts']
        self.assertEqual(receipt[0]['eligible'],104)
        for reason in ('LATEST_STILL_UNSUPPORTED','AMBIGUOUS_LATEST_SAME_DAY_EDITIONS','NOT_NONFINANCIAL_IN_2021_SOURCE','STALE_ANNUAL_SOURCE','NOT_IN_FORMATION_MEMBERSHIP','NO_POSITIVE_FORMATION_QUOTE'):self.assertEqual(counts[reason],1)

    def test_misaligned_view_future_selected_document_and_rehashed_bad_record_fail(self):
        for mode in ('clock','mode','duplicate','future','source','id'):
            f=fixture();v=f[3]['2024-01-02']
            if mode=='clock':v['as_of']='2024-01-31T07:05:00+00:00'
            elif mode=='mode':v['visibility_mode']=op.OBSERVED
            elif mode=='duplicate':v['classifications'].append(copy.deepcopy(v['classifications'][0]))
            elif mode=='future':f[4]['1']['day']='2025-04-29';f[5]['1']=object()
            elif mode=='source':v['classifications'][0]['selected_source_sha256']='f'*64
            else:v['classifications'][0]['effective_record_id']='f'*64
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.build(f)

    def test_unselected_future_payloads_ignored_and_insufficient_coverage_stops_version(self):
        f=fixture();f[3]['2026-01-05']=object();f[4]['future']=object();f[5]['future']=object();self.build(f)
        for row in f[3]['2024-01-02']['classifications'][:11]:row['effective_source_status']='STILL_UNSUPPORTED'
        with self.assertRaisesRegex(ValueError,'coverage'):self.build(f)
        with self.assertRaises(ValueError):signal.build_targets(*f[:5],f[5].__getitem__,f[6].__getitem__,f[7],end='2026-01-05')

    def test_completed_formation_is_persisted_before_later_metadata_failure(self):
        f=fixture();done=[]
        with self.assertRaises(KeyError):signal.build_targets(*f[:5],f[5].__getitem__,f[6].__getitem__,f[7],end='2024-02-01',on_formation=lambda d,t,r:done.append((d,r['eligible'])))
        self.assertEqual(done,[('2024-01-02',110)])
