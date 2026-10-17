import unittest
from datetime import date

from scripts.verify_cninfo_csi500_event_prices import check_pair


class EventPriceAdmissionTests(unittest.TestCase):
    def test_next_session_pair_and_corporate_action_are_distinct(self):
        class Snapshot:
            calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))

            def raw_bar(self, code, day):
                return {"status": "observed_bar", "normalization_factor":
                        2.0 if day == "2024-01-04" else 1.0}

        membership = {"SH600001": [("2024-01-01", "2024-12-31")]}
        self.assertEqual(check_pair(Snapshot(), "SH600001", "2024-01-02", membership),
                         "price_pair_admitted")
        self.assertEqual(check_pair(Snapshot(), "SH600001", "2024-01-03", membership),
                         "corporate_action_factor_jump")

    def test_last_pre2026_date_cannot_query_2026_price(self):
        class Snapshot:
            calendar = (date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 5))

            def raw_bar(self, code, day):
                raise AssertionError("must not read 2026 prices")

        self.assertEqual(check_pair(Snapshot(), "SH600001", "2025-12-31", {}),
                         "no_pre2026_next_session")


if __name__ == "__main__":
    unittest.main()
