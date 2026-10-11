import json
import tempfile
import unittest
from pathlib import Path

try:
    from stock_rsi.time import parse_time
    from stock_rsi.calendar import TradingCalendar
    from stock_rsi.data import Dataset
except ImportError:
    parse_time = TradingCalendar = Dataset = None


def fixture():
    return {
        "dataset_id": "synthetic_cn_v1",
        "evidence_level": "SYNTHETIC_REGRESSION",
        "provenance": {"source": "hand-authored", "real_market_prices": False},
        "sessions": ["2024-09-27", "2024-09-30", "2024-10-08", "2024-10-09"],
        "records": [
            {"record_id": "report-v1", "fact_key": "SYN_A:earnings:q2", "security_id": "SYN_A", "kind": "filing", "event_at": "2024-09-27T16:00:00+08:00", "public_at": "2024-09-27T16:00:00+08:00", "available_at": "2024-09-27T16:05:00+08:00", "payload": {"period_end": "2024-06-30", "profit": 100}},
            {"record_id": "report-v2", "fact_key": "SYN_A:earnings:q2", "security_id": "SYN_A", "kind": "filing", "event_at": "2024-09-27T16:00:00+08:00", "public_at": "2024-10-08T16:00:00+08:00", "available_at": "2024-10-08T16:05:00+08:00", "payload": {"period_end": "2024-06-30", "profit": 90}},
            {"record_id": "late-news", "fact_key": "SYN_A:news:1", "security_id": "SYN_A", "kind": "announcement", "event_at": "2024-09-30T11:45:00+08:00", "public_at": "2024-09-30T11:45:00+08:00", "available_at": "2024-09-30T13:05:00+08:00", "payload": {"text": "synthetic arrival lag"}},
        ],
    }


class TimeDataTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Dataset, "time/calendar/data implementation is missing")

    def load(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text(json.dumps(payload))
            return Dataset.load(path)

    def test_naive_time_is_rejected_and_offsets_normalize(self):
        with self.assertRaises(ValueError):
            parse_time("2024-09-27T16:05:00")
        self.assertEqual(parse_time("2024-09-27T16:05:00+08:00").isoformat(), "2024-09-27T08:05:00+00:00")

    def test_lunch_and_holiday_do_not_create_trading_sessions(self):
        calendar = TradingCalendar(fixture()["sessions"])
        self.assertFalse(calendar.is_trading(parse_time("2024-09-30T12:00:00+08:00")))
        self.assertFalse(calendar.is_trading(parse_time("2024-10-01T10:00:00+08:00")))
        self.assertEqual(calendar.next_open(parse_time("2024-09-30T12:00:00+08:00")).isoformat(), "2024-09-30T05:00:00+00:00")
        self.assertEqual(calendar.next_open(parse_time("2024-09-30T15:01:00+08:00")).isoformat(), "2024-10-08T01:30:00+00:00")

    def test_public_report_is_hidden_until_arrival_inclusive(self):
        data = self.load(fixture())
        self.assertEqual(data.snapshot(parse_time("2024-09-27T16:04:59+08:00")).to_dict()["records"], [])
        records = data.snapshot(parse_time("2024-09-27T16:05:00+08:00")).to_dict()["records"]
        self.assertEqual([r["record_id"] for r in records], ["report-v1"])

    def test_revision_does_not_rewrite_prior_snapshot(self):
        data = self.load(fixture())
        before = data.snapshot(parse_time("2024-09-30T17:00:00+08:00"))
        after = data.snapshot(parse_time("2024-10-08T17:00:00+08:00"))
        self.assertEqual(before.to_dict()["records"][0]["payload"]["profit"], 100)
        self.assertEqual([r for r in after.to_dict()["records"] if r["kind"] == "filing"][0]["payload"]["profit"], 90)
        view = before.to_dict()
        view["records"][0]["payload"]["profit"] = 999
        self.assertEqual(before.to_dict()["records"][0]["payload"]["profit"], 100)

    def test_future_perturbation_preserves_snapshot_hash(self):
        original = fixture()
        changed = fixture()
        changed["records"][1]["payload"]["profit"] = -999999
        at = parse_time("2024-09-30T17:00:00+08:00")
        self.assertEqual(self.load(original).snapshot(at).sha256, self.load(changed).snapshot(at).sha256)

    def test_daily_bar_cannot_publish_future_close_or_use_non_session(self):
        base=fixture()
        row={"record_id":"bar", "security_id":"SYN_A", "kind":"bar", "event_at":"2024-09-27T15:00:00+08:00", "public_at":"2024-09-27T15:00:00+08:00", "available_at":"2024-09-27T17:00:00+08:00", "payload":{"trade_date":"2024-09-30","open":10,"close":11}}
        for day,event in (("2024-09-30","2024-09-27T15:00:00+08:00"),("2024-09-27","2024-09-27T10:00:00+08:00"),("2024-10-01","2024-10-01T15:00:00+08:00")):
            bad=json.loads(json.dumps(base)); changed=json.loads(json.dumps(row))
            changed['payload']['trade_date']=day
            changed['event_at']=changed['public_at']=changed['available_at']=event
            bad['records'].append(changed)
            with self.subTest(day=day,event=event),self.assertRaises(ValueError):self.load(bad)

    def test_invalid_arrival_and_duplicate_ids_fail_loading(self):
        bad = fixture()
        bad["records"][0]["available_at"] = "2024-09-27T15:00:00+08:00"
        with self.assertRaises(ValueError):
            self.load(bad)
        bad = fixture()
        bad["records"].append(bad["records"][0])
        with self.assertRaises(ValueError):
            self.load(bad)


if __name__ == "__main__":
    unittest.main()
