import math
import statistics
from datetime import date
import unittest
try:
    from stock_rsi.market_residual_momentum import residual_score,build_targets
except ImportError:residual_score=build_targets=None


def prices(returns,initial=100.):
    out=[initial]
    for r in returns:out.append(out[-1]*(1+r))
    return out


class MarketResidualMomentumTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(residual_score)

    def test_beta_fitted_with_intercept_but_alpha_is_not_subtracted_from_ranking_return(self):
        market=[-.02,0.,.02]*12;noise=[.01,-.02,.01]*12
        stock=[.01+2*x+e for x,e in zip(market,noise)]
        value=residual_score(prices(stock),prices(market,1000.))
        adjusted=[.01+e for e in noise][-12:-1]
        self.assertAlmostEqual(value['beta'],2.);self.assertAlmostEqual(value['alpha'],.01)
        self.assertAlmostEqual(value['score'],statistics.mean(adjusted)/statistics.stdev(adjusted))
        self.assertAlmostEqual(value['score'],residual_score(prices(stock,777.),prices(market,3.))['score'])
        self.assertEqual(len(value['rank_adjusted_returns']),11)

    def test_incomplete_or_degenerate_histories_are_not_fake_neutral_scores(self):
        market=[-.02,0.,.02]*12;stock=[.01+2*x for x in market]
        self.assertIsNone(residual_score(prices(stock),prices(market)))
        self.assertIsNone(residual_score(prices(market),[100.]*37))
        for bad in (None,0.,-1.,math.nan,math.inf):
            self.assertIsNone(residual_score(prices(market)[:-1]+[bad],prices(market)))
        with self.assertRaises(ValueError):residual_score([100.]*36,[100.]*37)

    def test_monthly_clock_history_membership_and_future_records_have_explicit_roles(self):
        ends=[date(2020,12,28)]+[date(y,m,28) for y in (2021,2022,2023) for m in range(1,13)]
        mr=[-.02,0.,.02]*12;mp=prices(mr);noise=[.01,-.02,.01]*12
        class Source:
            calendar=tuple(ends+[date(2024,1,2),date(2024,1,31),date(2024,2,1),date(2026,1,5)])
            def __init__(self):self.reads=[]
            def value(self,code,field,day):
                assert day<='2023-12-28','future value read';self.reads.append((code,field,day))
                if field in ('factor','volume'):return 1.
                selftest=ends.index(date.fromisoformat(day))
                if code=='SH000905':return mp[selftest]
                alpha=.001+int(code[-3:])/100000
                return prices([alpha+2*x+e for x,e in zip(mr,noise)])[selftest]
        members={f'SH600{i:03d}':[('2010-01-01','2025-12-31')] for i in range(200)}
        members['SZ000999']=[('2024-01-02','2025-12-31')]
        source=Source();targets,receipts=build_targets(source,members,end='2024-01-31')
        r=receipts[0];self.assertEqual(r['regression_return_months'][0],'2021-01');self.assertEqual(r['regression_return_months'][-1],'2023-12')
        self.assertEqual(r['ranking_return_months'],[f'2023-{m:02d}' for m in range(1,12)])
        self.assertEqual(r['skipped_ranking_month'],'2023-12');self.assertEqual(r['latest_factor_price_read'],'2023-12-28')
        selected=targets['market_residual_mom36_12_2']['2024-01-02']['weights']
        self.assertEqual(tuple(selected),tuple(f'SH600{i:03d}' for i in range(199,179,-1)))
        self.assertAlmostEqual(sum(selected.values()),.95)
        self.assertNotIn('SZ000999',targets['eligible_equal_weight']['2024-01-02']['weights'])
        with self.assertRaises(ValueError):build_targets(source,members,end='2026-01-05')

    def test_missing_exchange_month_cannot_shorten_regression_window(self):
        class Source:
            calendar=tuple([date(2020,12,28)]+[date(y,m,28) for y in (2021,2022,2023) for m in range(1,13)
                if (y,m)!=(2022,6)]+[date(2024,1,2)])
            def value(self,*args):return 1.
        with self.assertRaises(ValueError):build_targets(Source(),{},end='2024-01-02')
