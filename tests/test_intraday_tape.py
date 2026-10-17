import copy
import unittest
from datetime import date
from stock_rsi.intraday_tape import aggregate_minutes
from scripts.tdx_history_checks import minute_labels


class IntradayTapeTests(unittest.TestCase):
    def test_local_evidence_does_not_hash_future_points_and_lunch_is_explicit(self):
        day=date(2024,1,3)
        points=[{'time':'2024-01-03T'+label+':00+08:00','volume':100,'price_milli':10000} for label in minute_labels()]
        first=aggregate_minutes('A',day,points)
        self.assertEqual(len(first),48)
        self.assertEqual(first[0]['volume_lower_shares'],49500)
        self.assertEqual(first[23]['end'],'2024-01-03T03:30:00+00:00')
        self.assertEqual(first[24]['start'],'2024-01-03T05:00:00+00:00')
        changed=copy.deepcopy(points);changed[-1]['price_milli']=20000
        second=aggregate_minutes('A',day,changed)
        self.assertEqual(first[:47],second[:47])
        self.assertNotEqual(first[-1]['evidence_id'],second[-1]['evidence_id'])
        changed[0]['volume']=True
        with self.assertRaises(ValueError):aggregate_minutes('A',day,changed)
