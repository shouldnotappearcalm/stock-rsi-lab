import copy,json,tempfile,unittest
from pathlib import Path
from scripts.fundamental_query_journal import QueryJournal,digest
from scripts.illiquidity_minute_sources import query_minute_packet
from scripts.tdx_history_checks import minute_labels
try:
    from scripts.admit_low_beta60_minutes_pre2026 import inspect_packet,verify_query_receipt
except ImportError:
    inspect_packet=verify_query_receipt=None


class LowBeta60MinuteAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(inspect_packet);self.assertIsNotNone(verify_query_receipt)
        self.day='2024-01-02';self.code='SH600008'
        self.daily={'date':self.day,'tradestatus':'1','isST':'0','open':'10','high':'11','low':'9','close':'10','volume':'24035'}
        self.payload={'exchange':'sh','market_id':1,'code':'600008','trading_date':self.day,
            'points':[{'index':i,'time_label':s,'time':self.day+'T'+s+':00+08:00',
                'price_milli':10000,'price':10,'volume':1} for i,s in enumerate(minute_labels())]}
        self.packet={'instrument':self.code,'requested_day':self.day,'status':'RESPONSE_CAPTURED','response':self.payload}
    def test_full_reconstruction_keeps_hand_rounding_distinct_from_exact_share_certification(self):
        v=inspect_packet(self.code,self.day,self.packet,self.daily)
        self.assertEqual(v['status'],'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE');self.assertEqual(v['windows'],48)
        self.assertEqual(v['stressed_volume_lower_shares'],0)
        self.assertFalse(v['facts']['exact_total_shares_match']);self.assertFalse(v['facts']['historical_date_echo_authenticated'])
    def test_wrong_price_signature_volume_or_missing_minutes_are_rejected(self):
        for kind in ('last','range','volume','partial','clock'):
            packet=copy.deepcopy(self.packet);points=packet['response']['points']
            if kind in ('last','range'):
                point=points[-1] if kind=='last' else points[0];point.update(price_milli=12000,price=12)
            elif kind=='volume':
                for point in points:point['volume']=1000000
            elif kind=='partial':points.pop()
            else:points[120]['time']=self.day+'T12:01:00+08:00'
            with self.subTest(kind=kind),self.assertRaises(ValueError):inspect_packet(self.code,self.day,packet,self.daily)
    def test_failed_future_wrong_security_or_daily_identity_are_rejected(self):
        cases=[(self.code,'2026-01-05',self.packet,self.daily),('SZ000001',self.day,self.packet,self.daily),
            (self.code,self.day,{**self.packet,'status':'REQUEST_FAILED'},self.daily),
            (self.code,self.day,self.packet,{**self.daily,'date':'2024-01-03'})]
        for c,d,p,b in cases:
            with self.subTest(c=c,d=d),self.assertRaises(ValueError):inspect_packet(c,d,p,b)
    def test_success_and_error_receipts_authenticate_and_modified_response_or_packet_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);j=QueryJournal(root,max_queries=2,max_attempts=1)
            packet=query_minute_packet(j,self.code,self.day,'fixture',lambda:self.payload)
            verify_query_receipt(root,self.code,self.day,packet,'fixture')
            bad=copy.deepcopy(packet);bad['response']['code']='600009'
            with self.assertRaises(ValueError):verify_query_receipt(root,self.code,self.day,bad,'fixture')
            def fail():raise RuntimeError('fixture source error')
            err=query_minute_packet(j,'SH600009',self.day,'fixture',fail)
            verify_query_receipt(root,'SH600009',self.day,err,'fixture')
            identity={'method':'minutes.history','instrument':self.code,'requested_day':self.day,'host':'fixture','include_raw':True}
            path=root/'queries'/digest(identity)/'response-1.json';old=path.read_text();path.write_text(old+' ')
            with self.assertRaises(ValueError):verify_query_receipt(root,self.code,self.day,packet,'fixture')
