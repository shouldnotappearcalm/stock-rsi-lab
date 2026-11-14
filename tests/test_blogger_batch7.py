import unittest

from stock_rsi.blogger_batch7 import SYMBOLS, allocation, orders_for


class MultiETFTests(unittest.TestCase):
    def test_inverse_vol_doubles_weight_when_daily_vol_halves(self):
        paths={}
        for c,amp in zip(SYMBOLS,(.01,.02,.02,.02)):
            p=[1.]
            for i in range(60):
                p.append(p[-1]*(1+amp*(-1)**i))
            paths[c]=p
        weights,_=allocation('invvol60',paths)
        self.assertAlmostEqual(sum(weights.values()),.95)
        self.assertAlmostEqual(weights[SYMBOLS[0]],2*weights[SYMBOLS[1]])
        self.assertEqual(allocation('equal4',{})[0],dict.fromkeys(SYMBOLS,.2375))

    def test_missing_or_zero_volatility_fails_closed(self):
        with self.assertRaises(ValueError):
            allocation('invvol60',dict.fromkeys(SYMBOLS,[1.]*61))
        with self.assertRaises(ValueError):
            allocation('invvol60',dict.fromkeys(SYMBOLS,[1.]*60))

    def test_sell_only_before_purchase_with_observed_cash(self):
        c=SYMBOLS[0]
        prices=dict.fromkeys(SYMBOLS,10.)
        factors=dict.fromkeys(SYMBOLS,1.)
        target=dict.fromkeys(SYMBOLS,200.)
        sell=orders_for(target,{c:400.},prices,factors,6000.,10000.,40)
        self.assertEqual(sell,[{'instrument':c,'side':'SELL','normalized_units':200.}])
        buys=orders_for(target,{c:200.},prices,factors,6000.,10000.,40)
        self.assertGreater(len(buys),1)
        spent=sum(o['normalized_units']*10+max(5,o['normalized_units']*.045) for o in buys)
        self.assertLessEqual(spent,5500.)
        self.assertTrue(all(o['side']=='BUY' and o['normalized_units']%100==0 for o in buys))
