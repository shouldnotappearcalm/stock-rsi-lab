import unittest
from scripts.tdx_history_checks import minute_labels, inspect_minutes, inspect_opening, bounded_opening_match


class TdxHistoryChecksTests(unittest.TestCase):
    def daily(self):return {"tradestatus":"1","open":"10","high":"11","low":"9","close":"10","volume":"24035"}

    def test_sdk_page_limit_exception_gets_one_bounded_supplement_not_a_silent_empty(self):
        calls=[]
        def fetch(code,day,**kwargs):
            pages=kwargs['max_pages'];calls.append(pages)
            if pages==4:raise RuntimeError('trade pagination reached max_pages before an empty page')
            return {'matched':True}
        self.assertEqual(bounded_opening_match(fetch,'sh600008','2024-01-02'),({'matched':True},16))
        self.assertEqual(calls,[4,16])
        def broken(*args,**kwargs):raise RuntimeError('unrelated protocol failure')
        with self.assertRaisesRegex(RuntimeError,'unrelated'):bounded_opening_match(broken,'sh600008','2024-01-02')
        def limited(*args,**kwargs):raise RuntimeError('trade pagination reached max_pages before an empty page')
        with self.assertRaisesRegex(RuntimeError,'max_pages'):bounded_opening_match(limited,'sh600008','2024-01-02')

    def test_explicit_minutes_keep_hand_precision_distinct_from_exact_shares(self):
        self.assertEqual(len(minute_labels()),240)
        points=[{"index":i,"time_label":label,"time":"2024-01-02T"+label+":00+08:00",
                 "price_milli":10000,"price":10,"volume":1} for i,label in enumerate(minute_labels())]
        payload={"exchange":"sh","market_id":1,"code":"600008","trading_date":"2024-01-02","points":points}
        facts=inspect_minutes("SH600008","2024-01-02",payload,self.daily())
        self.assertEqual(facts["minute_volume_shares_at_documented_multiplier"],24000)
        self.assertTrue(facts["nearest_hand_daily_total_match_diagnostic_only"])
        self.assertFalse(facts["exact_total_shares_match"])
        payload["points"][0]["time"]="2024-01-02T09:31:00"
        with self.assertRaises(ValueError):inspect_minutes("SH600008","2024-01-02",payload,self.daily())

    def test_virtual_auction_wrong_date_and_fractional_hand_volume_cannot_pass(self):
        record={"event_kind":"opening_match","time_minutes":565,"time_label":"09:25","status_raw":2,
                "trade_datetime":"2024-01-02T09:25:00","price_milli":10000,"price":10,"volume":300}
        facts=inspect_opening("2024-01-02",record,self.daily())
        self.assertEqual(facts["matched_volume_shares_at_documented_multiplier"],30000)
        self.assertTrue(facts["usable_matched_volume"])
        self.assertFalse(facts["counterfactual_queue_and_impact_verified"])
        for changed in (record|{"status_raw":8},record|{"volume":True},record|{"volume":.5},
                        record|{"trade_datetime":"2024-01-03T09:25:00"},
                        record|{"trade_datetime":"2024-01-02T09:25:00+00:00"},record|{"price":True}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):inspect_opening("2024-01-02",changed,self.daily())
        self.assertFalse(inspect_opening("2024-01-02",None,self.daily())["usable_matched_volume"])
