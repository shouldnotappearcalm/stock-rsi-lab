import copy
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
import struct
import unittest

from stock_rsi.archive_cent_clock import inverse_binary32_cent, archive_scenario_windows
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.time import parse_time


def f32(value):return struct.unpack('>f',struct.pack('>f',value))[0]


class ArchiveCentClockTests(unittest.TestCase):
    def fixture(self):
        day=date(2024,1,2)
        labels=['09:30']+[f'{h:02d}:{m:02d}' for h in (9,10,11,13,14,15) for m in range(60)
            if '09:31'<=f'{h:02d}:{m:02d}'<='11:30' or '13:01'<=f'{h:02d}:{m:02d}'<='15:00']
        rows=[dict(symbol='603056',exchange='SH',timestamp=datetime.fromisoformat(str(day)+'T'+t),
                   open=f32(10.01),high=f32(10.03),low=f32(9.99),close=f32(10.02),
                   volume=1000,turnover=10000.) for t in labels]
        daily=dict(date=str(day),tradestatus='1',open='10.01',high='10.03',low='9.99',close='10.02',volume='241000')
        return day,rows,daily

    def test_unique_exact_inverse_and_bitwise_roundtrip(self):
        for cents in [0,1,2,3,99,100,137,1443,12345,999999,10000001]:
            raw=f32(cents/100)
            with self.subTest(cents=cents):
                result=inverse_binary32_cent(raw)
                self.assertEqual(result,Decimal(cents).scaleb(-2))
                self.assertEqual(struct.pack('>f',float(result)),struct.pack('>f',raw))

    def test_nonpromoted_noncent_nonunique_and_unsupported_prices_rejected(self):
        for value in [True,1,10.01,-0.,-1.,float('inf'),float('nan'),f32(.001),f32(500000.)]:
            with self.subTest(value=value),self.assertRaises(ValueError):inverse_binary32_cent(value)

    def test_exact_midpoints_use_binary32_even_ties(self):
        # At high prices a single promoted float can encode multiple cents;
        # a nearest-cent fallback must never silently choose one.
        with self.assertRaises(ValueError):inverse_binary32_cent(f32(262144.))
        self.assertEqual(inverse_binary32_cent(f32(131072.)),Decimal('131072.00'))

    def test_all241_rows_retained_and192_interior_minutes_have_disjoint_clock_envelopes(self):
        day,rows,daily=self.fixture();before=copy.deepcopy(rows)
        result=archive_scenario_windows('SH603056',day,rows,daily)
        self.assertEqual(before,rows)
        self.assertEqual(len(result['decoded_price_audit']),241)
        self.assertEqual(len(result['unused_for_execution']),49)
        self.assertEqual(len(result['windows']),48)
        self.assertEqual(result['safe_window_volume_shares'],192000)
        self.assertEqual(result['whole_day_volume_shares'],241000)
        self.assertFalse(result['admitted_for_original_reconstructed_execution'])
        for w in result['windows']:
            self.assertEqual(w['volume_lower_shares'],4000)
            self.assertEqual(w['buy_price'],'10.03');self.assertEqual(w['sell_price'],'9.99')
            self.assertEqual(parse_time(w['available_at']),parse_time(w['end']))
            start,end=parse_time(w['start']),parse_time(w['end'])
            for i in (1,2,3,4):
                label=start+timedelta(minutes=i)
                self.assertLessEqual(start,label-timedelta(minutes=1))
                self.assertLessEqual(label+timedelta(minutes=1),end)

    def test_generated_windows_meet_unchanged_broker_contract_and_prior_only_child_sizing(self):
        day,rows,daily=self.fixture();result=archive_scenario_windows('SH603056',day,rows,daily)
        broker=IntradayBroker(TradingCalendar([str(day)]),'1000000',tape_provider=None)
        for w in result['windows']:broker._bar(w,'SH603056')
        for w in result['windows'][1:23]:broker._window_clock(w['start'],w['end'])

    def test_future_interior_bar_change_does_not_change_earlier_window_or_evidence(self):
        day,rows,daily=self.fixture();first=archive_scenario_windows('SH603056',day,rows,daily)
        rows[101]['close']=f32(10.01)
        second=archive_scenario_windows('SH603056',day,rows,daily)
        self.assertEqual(first['windows'][:19],second['windows'][:19])
        self.assertNotEqual(first['windows'],second['windows'])

    def test_boundary_volume_is_retained_in_audit_and_never_used_to_size_windows(self):
        day,rows,daily=self.fixture();first=archive_scenario_windows('SH603056',day,rows,daily)
        rows[0]['volume']+=1000000;daily['volume']='1241000'
        second=archive_scenario_windows('SH603056',day,rows,daily)
        self.assertEqual(first['windows'],second['windows'])
        self.assertEqual(second['whole_day_volume_shares'],1241000)
        self.assertEqual(second['safe_window_volume_shares'],192000)

    def test_missing_label_wrong_daily_or_bad_encoding_cannot_be_repaired(self):
        for mutation in ['missing','daily','encoding']:
            day,rows,daily=self.fixture()
            if mutation=='missing':del rows[0]
            if mutation=='daily':daily['high']='10.04'
            if mutation=='encoding':rows[1]['open']=10.01
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):archive_scenario_windows('SH603056',day,rows,daily)


if __name__=='__main__':unittest.main()
