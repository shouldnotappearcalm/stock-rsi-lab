"""Source freeze must reject tampering before interpreting archive values."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_illiquidity_archive_scenario_sources as builder


class FrozenScenarioRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method = self.root / 'method.py'
        self.method.write_text('frozen method\n')
        self.source = self.root / 'raw.json'
        self.source.write_text('original raw bytes\n')
        self.paths = {'source/raw.json': self.source, 'repo/method.py': self.method}
        self.request = {
            'status': builder.STATUS, 'contract': builder.CONTRACT,
            'portfolio_returns_permitted': False, 'end': '2025-12-31',
            'method_code_sha256': {'method.py': builder.file_sha(self.method)},
            'input_sha256': {n: builder.file_sha(p) for n, p in self.paths.items()},
        }
        self.file = self.root / 'request.json'

    def verify(self, request=None, expected=None):
        self.file.write_text(json.dumps(self.request if request is None else request))
        expected = builder.file_sha(self.file) if expected is None else expected
        with patch.object(builder, 'METHOD_FILES', ('method.py',)), patch.object(
                builder, 'required_input_paths', return_value=self.paths):
            return builder.verify_request(self.root, self.root, self.file, expected)

    def test_complete_original_bindings_are_accepted(self):
        _, paths = self.verify()
        self.assertEqual(paths, self.paths)

    def test_omitted_raw_source_is_rejected_even_when_remaining_hashes_match(self):
        changed = copy.deepcopy(self.request)
        del changed['input_sha256']['source/raw.json']
        with self.assertRaisesRegex(ValueError, 'complete input key set'):
            self.verify(changed)

    def test_changed_source_and_method_are_rejected_before_interpretation(self):
        self.source.write_text('changed raw bytes\n')
        with self.assertRaisesRegex(ValueError, 'frozen source bytes'):
            self.verify()
        self.method.write_text('changed method\n')
        with self.assertRaisesRegex(ValueError, 'frozen method bytes'):
            self.verify()

    def test_rewritten_request_or_permission_to_score_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'frozen source request'):
            self.verify(expected='0' * 64)
        for key, value in [('portfolio_returns_permitted', True), ('end', '2026-10-20')]:
            changed = {**self.request, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'source-only contract'):
                self.verify(changed)

    def test_postcheck_rejects_source_mutation(self):
        expected = self.request['input_sha256']
        builder.check_hashes(self.paths, expected)
        self.source.write_text('mutated during processing\n')
        with self.assertRaisesRegex(ValueError, 'frozen source bytes'):
            builder.check_hashes(self.paths, expected)

    def test_existing_output_is_not_overwritten_or_resumed(self):
        out = self.root / 'existing-output'
        out.mkdir()
        sentinel = out / 'failure.json'
        sentinel.write_text('original failed run\n')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            builder.build(self.root, self.root, self.file, 'unused', out)
        self.assertEqual(sentinel.read_text(), 'original failed run\n')

    def run_synthetic_build(self, interpreter):
        self.file.write_text(json.dumps(self.request))
        expected = builder.file_sha(self.file)
        out = self.root / 'new-output'
        with patch.object(builder, 'METHOD_FILES', ('method.py',)), patch.object(
                builder, 'required_input_paths', return_value=self.paths), patch.object(
                builder, '_interpret', side_effect=interpreter):
            return builder.build(self.root, self.root, self.file, expected, out)

    def test_interrupt_retains_partial_records_and_checks_every_input(self):
        def stop(*args):
            args[-1]['sessions'].append({'synthetic': 'already_processed'})
            self.source.write_text('changed during interrupted parse')
            raise KeyboardInterrupt('synthetic interrupt')
        with self.assertRaisesRegex(KeyboardInterrupt, 'synthetic interrupt'):
            self.run_synthetic_build(stop)
        out = self.root / 'new-output'
        terminal = builder.read(out / 'terminal.json')
        self.assertEqual(terminal['original_error']['type'], 'KeyboardInterrupt')
        self.assertEqual(terminal['partial_sessions'], 1)
        self.assertFalse(terminal['postcheck']['all_inputs_unchanged'])
        self.assertTrue(terminal['postcheck']['request_rehashed_after_processing'])
        self.assertEqual(builder.read(out / 'details.json')['sessions'],
                         [{'synthetic': 'already_processed'}])
        self.assertFalse((out / 'summary.json').exists())

    def test_request_changed_mid_run_cannot_produce_success_summary(self):
        def change_request(*args):
            self.file.write_text('{}')
            return {'status': 'SYNTHETIC_COMPLETION'}
        with self.assertRaisesRegex(ValueError, 'changed during source interpretation'):
            self.run_synthetic_build(change_request)
        out = self.root / 'new-output'
        self.assertEqual(builder.read(out / 'input-postcheck.json')['mismatches'],
                         [{'input': 'frozen_request', 'reason': 'SHA256_CHANGED'}])
        self.assertFalse((out / 'summary.json').exists())

    def test_io_parse_error_is_preserved_and_missing_input_is_reported(self):
        def io_error(*args):
            self.source.unlink()
            raise OSError('synthetic parse error')
        with self.assertRaisesRegex(OSError, 'synthetic parse error'):
            self.run_synthetic_build(io_error)
        terminal = builder.read(self.root / 'new-output' / 'terminal.json')
        self.assertEqual(terminal['original_error']['message'], 'synthetic parse error')
        self.assertEqual(terminal['postcheck']['mismatches'],
                         [{'input': 'source/raw.json', 'reason': 'FileNotFoundError'}])

    def test_terminal_persistence_failure_does_not_hide_original_interrupt(self):
        original = KeyboardInterrupt('original interrupted parse')
        real_write = builder.write
        def interrupted(*args):
            raise original
        def broken_details(path, value):
            if Path(path).name == 'details.json':
                raise OSError('synthetic disk write failure')
            return real_write(path, value)
        with patch.object(builder, 'write', side_effect=broken_details):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_synthetic_build(interrupted)
        self.assertIs(caught.exception, original)
        terminal = builder.read(self.root / 'new-output' / 'terminal.json')
        self.assertEqual(terminal['persistence_errors'], ['details.json:OSError'])
        self.assertIn('details.json:OSError', original.__notes__[0])


if __name__ == '__main__':
    unittest.main()
