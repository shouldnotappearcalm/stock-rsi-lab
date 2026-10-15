import unittest
import tempfile
import json
from pathlib import Path

from scripts.run_qlib_rolling_ridge20_pre2026 import main


class QlibRollingRidgeResearchTests(unittest.TestCase):
    def test_existing_output_cannot_be_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, "already exists"):
                main(["--provider-uri", "/nonexistent", "--output-dir", str(output)])
            self.assertEqual(list(output.iterdir()), [])

    def test_recorded_ridge_run_is_complete_and_not_promoted(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / "experiments/qlib/rolling-ridge20-pre2026-results.json").read_text())
        self.assertEqual(result["fit_count"], len(result["windows"]))
        self.assertEqual(result["fit_count"], 24)
        self.assertFalse(result["2026_market_data_accessed"])
        self.assertEqual(result["target_status"], "FAIL")
        self.assertGreater(result["comparison_to_rolling_lightgbm"]["2024_return_pct_points"], 0)
