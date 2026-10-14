import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.run_qlib_frozen_2026 import verify_frozen_inputs


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


if __name__ == "__main__":
    unittest.main()
