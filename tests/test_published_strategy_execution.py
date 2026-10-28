import unittest
from scripts.audit_published_strategy_execution import validate_order


class PublishedExecutionEvidenceTests(unittest.TestCase):
    def test_partial_fill_is_permitted_at_source_open_and_known_request(self):
        intent = {'orders': [{'instrument': 'A', 'side': 'BUY', 'normalized_units': 100}]}
        order = {'instrument': 'A', 'side': 'BUY', 'requested_normalized_units': '100', 'filled_normalized_units': '90', 'normalized_price': '10'}
        self.assertEqual(validate_order(order, intent, 10, 1000), .09)

    def test_signed_sell_and_unfilled_have_explicit_semantics(self):
        intent = {'orders': [{'instrument': 'A', 'side': 'SELL', 'normalized_units': 100}]}
        order = {'instrument': 'A', 'side': 'SELL', 'requested_normalized_units': '-100', 'filled_normalized_units': '-100', 'normalized_price': '10'}
        self.assertEqual(validate_order(order, intent, 10, 1000), .1)
        order.update(filled_normalized_units='0', normalized_price='')
        self.assertEqual(validate_order(order, intent, None, None), 0)

    def test_future_intent_price_size_and_capacity_forgeries_are_rejected(self):
        intent = {'orders': [{'instrument': 'A', 'side': 'BUY', 'normalized_units': 100}]}
        good = {'instrument': 'A', 'side': 'BUY', 'requested_normalized_units': '100', 'filled_normalized_units': '90', 'normalized_price': '10'}
        for changed, book, price, volume in [({'side': 'SELL'}, intent, 10, 1000), ({'normalized_price': '11'}, intent, 10, 1000), ({'requested_normalized_units': '101'}, intent, 10, 1000), ({'filled_normalized_units': '101'}, intent, 10, 1000), ({}, intent, 10, 80)]:
            with self.subTest(changed=changed, volume=volume), self.assertRaises(ValueError): validate_order({**good, **changed}, book, price, volume)
