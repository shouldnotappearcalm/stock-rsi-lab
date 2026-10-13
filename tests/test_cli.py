import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/"data/fixtures/synthetic_cn_v1.json"


class CLITests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "stock_rsi", *args], cwd=ROOT,
                              env=os.environ | {"PYTHONPATH": str(ROOT/"src")}, capture_output=True, text=True)

    def test_snapshot_cli_cutoff_excludes_future_and_returns_digest(self):
        result = self.command("snapshot", "--dataset", str(DATA), "--as-of", "2024-09-27T16:04:59+08:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["snapshot_hash"]), 64)
        self.assertNotIn("filing-v1", [row["record_id"] for row in data["snapshot"]["records"]])

    def test_run_and_replay_cli_persist_auditable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory)/"run")
            result = self.command("run", "--dataset", str(DATA), "--start", "2024-09-02T00:00:00+08:00", "--end", "2024-10-18T23:00:00+08:00", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(output)/"report.json").is_file())
            again = self.command("replay", "--run-dir", output, "--output", str(Path(directory)/"replay"))
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(json.loads(again.stdout)["account"], json.loads(result.stdout)["account"])

    def test_compare_cli_emits_equal_budget_report_and_denies_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            args=['compare','--dataset',str(DATA),'--splits',str(DATA.parent/'synthetic_cn_splits.json'),'--budget','1']
            result=self.command(*args,'--output',str(Path(directory)/'ok'))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['arms']),5)
            denied=self.command(*args,'--split','sealed','--output',str(Path(directory)/'denied'))
            self.assertEqual(denied.returncode,2)
            self.assertFalse((Path(directory)/'denied').exists())

    def test_cli_rejects_naive_time_before_running(self):
        result = self.command("snapshot", "--dataset", str(DATA), "--as-of", "2024-09-27T16:05:00")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timezone-aware", result.stderr)

    def test_public_package_declares_license_and_private_inputs_stay_ignored(self):
        license_text = (ROOT / "LICENSE").read_text()
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        package = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(package["project"]["license"], {"file": "LICENSE"})
        ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines() if line.strip()}
        self.assertTrue({"data/local/", "artifacts/", ".env"} <= ignored)


if __name__ == '__main__':
    unittest.main()
