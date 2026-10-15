import unittest

from scripts.run_qlib_master_pre2026 import DailySequences, train_label_subset


class QlibMasterResearchTests(unittest.TestCase):
    def test_daily_sequences_use_each_stocks_past_observed_sessions(self):
        try:
            import numpy as np
            import pandas as pd
        except ImportError:
            self.skipTest("optional research dependencies unavailable")
        dates = pd.bdate_range("2024-01-02", periods=10)
        pairs = [("SH600001", day) for day in dates] + [("SH600002", day) for day in dates[5:]]
        index = pd.MultiIndex.from_tuples(pairs, names=["instrument", "datetime"])
        columns = pd.MultiIndex.from_tuples(
            [("feature", str(i)) for i in range(158)] + [("label", "LABEL0")]
        )
        panel = pd.DataFrame(0.0, index=index, columns=columns)
        for instrument, day in pairs:
            panel.loc[(instrument, day), ("feature", "0")] = dates.get_loc(day)
        market = pd.DataFrame(
            np.repeat((np.arange(10) * 10)[:, None], 63, axis=1),
            index=pd.Index(dates, name="datetime"),
        )
        rows, features, _ = DailySequences(panel, market).batch(dates[-1])
        self.assertEqual(len(rows), 2)
        self.assertEqual(features.shape, (2, 8, 221))
        self.assertEqual(features[0, :, 0].tolist(), list(range(2, 10)))
        self.assertEqual(features[0, :, 158].tolist(), [i * 10 for i in range(2, 10)])
        self.assertEqual(features[1, :3, 0].tolist(), [0.0] * 3)
        self.assertEqual(features[1, 3:, 0].tolist(), list(range(5, 10)))

    def test_training_label_filter_trims_tails_without_looking_ahead(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("optional numpy research dependency unavailable")
        features = np.zeros((100, 8, 221), dtype="float32")
        labels = np.arange(100, dtype="float32")
        _, standardized = train_label_subset(features, labels)
        self.assertEqual(len(standardized), 96)
        self.assertAlmostEqual(float(standardized.mean()), 0.0, places=6)
        self.assertAlmostEqual(float(standardized.std(ddof=1)), 1.0, places=6)
