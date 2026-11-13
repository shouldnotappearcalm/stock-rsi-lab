import unittest

from stock_rsi.blogger_batch5 import evaluate


class Batch5Tests(unittest.TestCase):
    def test_hill_exact_edges_and_neutral_state(self):
        above = [99.] * 5 + [100.] * 190 + [101.] * 5
        below = [101.] * 5 + [100.] * 190 + [99.] * 5
        self.assertTrue(evaluate('hill5200', above, [100.] * 3, False, False)['state_after'])
        self.assertFalse(evaluate('hill5200', below, [100.] * 3, True, True)['state_after'])
        self.assertTrue(evaluate('hill5200', [100.] * 200, [100.] * 3, False, True)['state_after'])
        self.assertFalse(evaluate('hill5200', [100.] * 200, [100.] * 3, True, False)['state_after'])

    def test_swanson_body_direction_not_interday_close(self):
        closes = [100.] * 197 + [101., 102., 103.]
        self.assertEqual(evaluate('swanson32', closes, [102., 103., 104.], False, False)['leader'], 'SH510050')
        self.assertIsNone(evaluate('swanson32', closes, [102., 102., 104.], False, False)['leader'])

    def test_swanson_exit_survives_unfilled_order_then_resets(self):
        closes = [100.] * 200
        exit_signal = evaluate('swanson32', closes, [101., 99., 99.], True, False)
        self.assertIsNone(exit_signal['leader'])
        self.assertTrue(exit_signal['state_after'])
        self.assertIsNone(evaluate('swanson32', closes, [101.] * 3, True, True)['leader'])
        self.assertEqual(evaluate('swanson32', closes, [101.] * 3, False, True)['leader'], 'SH510050')

    def test_incomplete_prices_rejected(self):
        with self.assertRaises(ValueError):
            evaluate('hill5200', [100.] * 199, [100.] * 3, False, False)
        with self.assertRaises(ValueError):
            evaluate('swanson32', [100.] * 200, [100., None, 100.], False, False)
