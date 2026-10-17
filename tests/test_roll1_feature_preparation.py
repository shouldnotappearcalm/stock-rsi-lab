import tempfile
import unittest

from scripts.prepare_qlib_roll1_features_pre2026 import END, NO_FORWARD_LABEL, main


class RollingFeaturePreparationTests(unittest.TestCase):
    def test_feature_only_preparation_cannot_overwrite_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "already exists"):
                main(["--provider-uri", "/not-needed", "--output-dir", directory])
        self.assertEqual(END, "2025-12-30")
        self.assertNotIn("Ref(", NO_FORWARD_LABEL)
