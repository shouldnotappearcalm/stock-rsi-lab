import unittest
from datetime import date

from scripts.verify_cninfo_csi500_event_prices import check_pair, classify_original_events


class EventPriceAdmissionTests(unittest.TestCase):
    def test_next_session_pair_and_listed_adjustment_are_distinct(self):
        class Snapshot:
            calendar = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))

            def raw_bar(self, code, day):
                return {"status": "observed_bar", "normalization_factor":
                        2.0 if day == "2024-01-04" else 1.0}

        membership = {"SH600001": [("2024-01-01", "2024-12-31")]}
        self.assertEqual(check_pair(Snapshot(), "SH600001", "2024-01-02", membership),
                         "price_pair_observed_no_listed_adjustment")
        self.assertEqual(check_pair(Snapshot(), "SH600001", "2024-01-03", membership,
                                    {"2024-01-04"}), "listed_adjustment_on_open")

    def test_last_pre2026_date_cannot_query_2026_price(self):
        class Snapshot:
            calendar = (date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 5))

            def raw_bar(self, code, day):
                raise AssertionError("must not read 2026 prices")

        self.assertEqual(check_pair(Snapshot(), "SH600001", "2025-12-31", {}),
                         "no_pre2026_next_session")

    def test_duplicate_versions_and_generic_yearless_title_are_quarantined(self):
        reports = {"annual": [
            {"title": "2023年年度报告", "announcement_id": "a"},
            {"title": "2023年年度报告全文", "announcement_id": "b"},
            {"title": "锦江酒店年报", "announcement_id": "c"},
            {"title": "2024年年度报告", "announcement_id": "d"},
        ], "q1": []}
        accepted, ambiguous, generic = classify_original_events(reports)
        self.assertEqual([row["announcement_id"] for _, row in accepted], ["d"])
        self.assertEqual(ambiguous[0]["announcement_ids"], ["a", "b"])
        self.assertEqual([row["announcement_id"] for row in generic], ["c"])


if __name__ == "__main__":
    unittest.main()
