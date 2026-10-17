import unittest
from datetime import datetime, timedelta, timezone

from scripts.capture_cninfo_csi500_reports_pre2026 import (
    capture_one, historical_names, member_on,
)


class CninfoFullCaptureTests(unittest.TestCase):
    def test_historical_universe_uses_membership_intervals(self):
        text = "\n".join((
            "SH600001 2023-01-01 2024-06-30",
            "SH600001 2025-01-01 2025-12-31",
            "SZ000002 2025-05-01 2025-12-31",
            "SH688001 2024-01-01 2025-12-31",
            "SH600003 2020-01-01 2023-12-31",
        ))
        intervals = historical_names(text)
        self.assertEqual(list(intervals), ["SH600001", "SZ000002"])
        self.assertTrue(member_on("SH600001", "2024-06-30", intervals))
        self.assertFalse(member_on("SH600001", "2024-12-31", intervals))
        self.assertTrue(member_on("SZ000002", "2025-05-01", intervals))

    def test_missing_category_report_is_recovered_from_fulltext(self):
        def record(kind, year):
            title = {"annual": "年度报告", "q1": "第一季度报告",
                     "h1": "半年度报告", "q3": "第三季度报告"}[kind]
            when = datetime(year, 4, 30, tzinfo=timezone(timedelta(hours=8)))
            return {"secCode": "600001", "announcementTitle": f"{year}年{title}",
                    "announcementTime": int(when.timestamp() * 1000),
                    "announcementId": kind + str(year), "adjunctUrl": "example.pdf"}

        categories = {
            "category_ndbg_szsh": "annual", "category_yjdbg_szsh": "q1",
            "category_bndbg_szsh": "h1", "category_sjdbg_szsh": "q3",
        }

        class Client:
            def fetch(self, url, payload):
                kind = categories.get(payload["category"])
                if kind == "q1":
                    rows = [record("q1", 2025)]
                elif kind:
                    rows = [record(kind, 2024), record(kind, 2025)]
                else:
                    rows = [record("q1", 2024)]
                return {"totalAnnouncement": len(rows), "announcements": rows}

        result = capture_one("SH600001", "org", Client())
        self.assertEqual(result["category_counts"]["q1"], 1)
        self.assertEqual(len(result["reports"]["q1"]), 2)
        self.assertEqual(result["fallback_recoveries"], [
            {"kind": "q1", "year": "2024", "announcement_id": "q12024"}
        ])
        self.assertEqual(result["missing_original_reports"], [])


if __name__ == "__main__":
    unittest.main()
