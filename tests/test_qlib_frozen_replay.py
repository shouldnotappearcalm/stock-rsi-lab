import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.run_qlib_frozen_2026 import verify_frozen_inputs
from scripts.run_qlib_enhanced_frozen_2026 import verify_frozen_inputs as verify_enhanced_inputs


class QlibFrozenReplayTests(unittest.TestCase):
    def test_model_identity_and_exact_interval_are_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.pkl"
            model.write_bytes(b"frozen-model")
            identity = hashlib.sha256(model.read_bytes()).hexdigest()
            self.assertEqual(verify_frozen_inputs(model, identity), identity)
            with self.assertRaises(ValueError):
                verify_frozen_inputs(model, "0" * 64)
            with self.assertRaises(ValueError):
                verify_frozen_inputs(model, identity, start="2026-01-06")

    def test_enhanced_diagnostic_requires_exact_prediction_and_risk_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction = root / "pred.pkl"
            prediction.write_bytes(b"fixed-prediction")
            identity = hashlib.sha256(prediction.read_bytes()).hexdigest()
            risk = root / "risk"
            (risk / "20251231").mkdir(parents=True)
            (risk / "20261012").mkdir()
            self.assertEqual(
                verify_enhanced_inputs(prediction, risk, identity),
                (identity, "20251231", "20261012"),
            )
            with self.assertRaises(ValueError):
                verify_enhanced_inputs(prediction, risk, "0" * 64)
            (risk / "20261013").mkdir()
            with self.assertRaises(ValueError):
                verify_enhanced_inputs(prediction, risk, identity)


if __name__ == "__main__":
    unittest.main()
