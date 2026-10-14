import math
import struct
import tempfile
import unittest
from pathlib import Path

from stock_rsi.qlib_snapshot import QlibSnapshot, equity_exchange


def write_feature(root, symbol, name, start, values):
    path = root / "features" / symbol.lower() / f"{name}.day.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack(f"<{len(values) + 1}f", float(start), *values))


class QlibSnapshotTests(unittest.TestCase):
    def fixture(self, root):
        (root / "calendars").mkdir(parents=True)
        (root / "instruments").mkdir(parents=True)
        (root / "calendars" / "day.txt").write_text(
            "2026-10-09\n2026-10-12\n2026-10-13\n"
        )
        (root / "instruments" / "all.txt").write_text(
            "SH600519\t2026-10-09\t2026-10-13\n"
            "SZ000001\t2026-10-09\t2026-10-13\n"
            "BJ920000\t2026-10-12\t2026-10-13\n"
            "SH000300\t2026-10-09\t2026-10-13\n"
            "SZ399300\t2026-10-09\t2026-10-13\n"
            "SH900901\t2026-10-09\t2026-10-13\n"
            "SZ200002\t2026-10-09\t2026-10-13\n"
        )
        factor = [0.25, 0.25, 0.25]
        fields = {
            "open": [300.0, 310.0, math.nan],
            "high": [305.0, 315.0, math.nan],
            "low": [295.0, 305.0, math.nan],
            "close": [302.5, 312.5, math.nan],
            "volume": [4000.0, 8000.0, math.nan],
            "factor": factor,
            "amount": [1_200_000.0, 2_500_000.0, math.nan],
        }
        for name, values in fields.items():
            write_feature(root, "SH600519", name, 0, values)

    def test_filters_indices_and_b_shares_from_point_in_time_universe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            snapshot = QlibSnapshot(root)
            self.assertEqual(snapshot.equities_on("2026-10-09"), ("SH600519", "SZ000001"))
            self.assertEqual(
                snapshot.equities_on("2026-10-12"),
                ("BJ920000", "SH600519", "SZ000001"),
            )
            self.assertEqual(snapshot.mainboard_sh_sz_on("2026-10-12"), ("SH600519", "SZ000001"))
            self.assertIsNone(equity_exchange("SH000300"))
            self.assertIsNone(equity_exchange("SH900901"))

    def test_recovers_raw_ohlcv_and_refuses_to_infer_missing_tradability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            snapshot = QlibSnapshot(root)
            bar = snapshot.raw_bar("SH600519", "2026-10-12")
            self.assertEqual(bar["status"], "observed_bar")
            self.assertEqual(bar["open"], 1240.0)
            self.assertEqual(bar["close"], 1250.0)
            self.assertEqual(bar["volume_source_units"], 2000.0)
            self.assertEqual(bar["amount_source_units"], 2_500_000.0)
            self.assertIsNone(bar["tradable"])
            missing = snapshot.raw_bar("SH600519", "2026-10-13")
            self.assertEqual(missing["status"], "missing_or_suspended")
            self.assertIsNone(missing["tradable"])

    def test_rejects_dates_outside_explicit_calendar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with self.assertRaises(ValueError):
                QlibSnapshot(root).audit("2026-10-10")


if __name__ == "__main__":
    unittest.main()
