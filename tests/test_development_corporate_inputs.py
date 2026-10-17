import copy
import unittest
from decimal import Decimal

try:
    from scripts.return_family_development_inputs import prepare_events
except ImportError:prepare_events=None

from stock_rsi.calendar import TradingCalendar
from stock_rsi.raw_share_account import RawShareAccount


class DevelopmentCorporateTests(unittest.TestCase):
    def event(self,**changes):
        row={'code':'sh.600763','dividPlanDate':'2024-07-01','dividRegistDate':'2024-07-04',
             'dividOperateDate':'2024-07-05','dividPayDate':'2024-07-05','dividStockMarketDate':'2024-07-05',
             'dividCashPsBeforeTax':'0.43565','dividStocksPs':'0.400595','dividReserveToStockPs':'',
             'dividCashStock':'10-stock-dividend-no-capital-transfer'}
        return row|changes

    def test_unheld_stock_dividend_retains_zero_event_and_cannot_be_applied_to_inventory(self):
        self.assertIsNotNone(prepare_events,'development corporate adapter missing')
        packets={'SH600763':{'instrument':'SH600763','distributions':[self.event()]}}
        targets={'2025-02-05':{'as_of':'2025-01-27','weights':{'SH600763':.95}}}
        original=copy.deepcopy(packets);merged,events,proofs=prepare_events(packets,targets,{'supplementary_distributions':[]})
        self.assertEqual(packets,original);self.assertEqual(len(events),1);self.assertEqual(len(proofs),1)
        self.assertFalse(events[0].capital_tax_exempt_verified)
        calendar=TradingCalendar(['2024-07-03','2024-07-04','2024-07-05','2024-07-08'])
        account=RawShareAccount(calendar,'10000',events)
        for day in calendar.days:account.start_day(day);account.end_day(day)
        self.assertEqual(account.broker.cash,Decimal('10000'));self.assertEqual(account.owned_quantities(),{})
        bad=RawShareAccount(calendar,'10000',events)
        bad.broker.positions={'SH600763':[{'quantity':100,'bought_on':calendar.days[0],'price':Decimal(10)}]}
        bad.start_day(calendar.days[1]);bad.end_day(calendar.days[1])
        with self.assertRaises(ValueError):bad.start_day(calendar.days[2])
        with self.assertRaises(ValueError):prepare_events(packets,{'2024-07-01':{'as_of':'2024-06-28','weights':{'SH600763':.95}}},{'supplementary_distributions':[]})

    def test_primary_cash_supplement_preserves_provider_packet_and_rejects_duplicate(self):
        self.assertIsNotNone(prepare_events,'development corporate adapter missing')
        packets={'SH600763':{'instrument':'SH600763','distributions':[]}}
        targets={'2025-02-05':{'as_of':'2025-01-27','weights':{'SH600763':.95}}}
        record=self.event(dividStocksPs='0',dividReserveToStockPs='0',dividStockMarketDate='')
        proof={'supplementary_distributions':[{'instrument':'SH600763','record':record,'source_file':'notice.pdf','source_sha256':'source'}]}
        merged,events,receipts=prepare_events(packets,targets,proof)
        self.assertEqual(packets['SH600763']['distributions'],[])
        self.assertEqual(len(merged['SH600763']['distributions']),1);self.assertEqual(events[0].cash_per_share,Decimal('.43565'))
        with self.assertRaises(ValueError):prepare_events(merged,targets,proof)
        future=copy.deepcopy(proof);future['supplementary_distributions'][0]['record']['dividOperateDate']='2026-01-05'
        with self.assertRaises(ValueError):prepare_events(packets,targets,future)
