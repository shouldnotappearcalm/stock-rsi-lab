import unittest

from scripts.audit_cninfo_report_admission import fixed_sample, original_report, publication_date, query


class CninfoReportAdmissionTests(unittest.TestCase):
    def test_fixed_sample_uses_active_main_board_members_only(self):
        lines = []
        for prefix, start in (("SH60", 1000), ("SZ00", 2000)):
            for i in range(8):
                lines.append(f"{prefix}{start+i} 2023-01-01 2025-01-01")
        lines.extend(("SH688001 2023-01-01 2025-01-01", "SH600999 2025-01-01 2026-01-01"))
        result = fixed_sample("\n".join(lines))
        self.assertEqual(len(result), 12)
        self.assertTrue(all(code.startswith(("SH60", "SZ00")) for code in result))
        self.assertNotIn("SH600999", result)

    def test_report_titles_and_date_only_timestamp(self):
        self.assertTrue(original_report("annual", "2024年年度报告"))
        self.assertTrue(original_report("annual", "2023年度报告"))
        self.assertTrue(original_report("annual", "江苏金租：2024年年度报告"))
        self.assertTrue(original_report("annual", "绝味食品2024年年度报告全文"))
        self.assertFalse(original_report("annual", "2024年年度报告摘要"))
        self.assertFalse(original_report("annual", "2023年年度报告补充公告"))
        self.assertTrue(original_report("q1", "2025年第一季度报告"))
        self.assertTrue(original_report("q1", "2024年一季度报告"))
        self.assertTrue(original_report("h1", "2024年半年度报告"))
        self.assertTrue(original_report("q3", "2025年三季度报告"))
        self.assertEqual(publication_date(1710432000000), "2024-03-15")

    def test_query_rejects_2026_before_network_access(self):
        with self.assertRaisesRegex(ValueError, "pre-2026"):
            query("org", "000001", "", "2025-12-01", "2026-01-05")
