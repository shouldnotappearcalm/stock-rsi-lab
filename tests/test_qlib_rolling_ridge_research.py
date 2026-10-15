import unittest
import tempfile
from pathlib import Path

from scripts.run_qlib_rolling_ridge20_pre2026 import main


class QlibRollingRidgeResearchTests(unittest.TestCase):
    def test_existing_output_cannot_be_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(ValueError, "already exists"):
                main(["--provider-uri", "/nonexistent", "--output-dir", str(output)])
            self.assertEqual(list(output.iterdir()), [])
