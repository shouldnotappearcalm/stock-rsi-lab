"""Exercise a real binary snapshot and the frozen formation-only CLI."""
import copy
import hashlib
import json
import struct
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.low_beta60 import build_targets as original_targets
from scripts.run_qlib_low_risk_pre2026 import input_hashes

try:
    from scripts.prepare_low_beta60_extension import METHOD_FILES, extension_input_hashes, main
except ImportError:
    METHOD_FILES = extension_input_hashes = main = None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


class PrepareLowBeta60ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(main, 'frozen formation-only consumer missing')

    def fixture(self, base):
        provider = base / 'provider'
        ends = [date(2018, 12, 28)] + [date(y, m, 28) for y in range(2019, 2027)
                for m in range(1, 13) if (y, m) <= (2026, 9)]
        firsts = [date(y, m, 2) for y in (2024, 2025, 2026) for m in range(1, 13)
                  if (y, m) <= (2026, 10)]
        days = sorted(ends + firsts + [date(2026, 10, 13)])
        (provider / 'calendars').mkdir(parents=True)
        (provider / 'instruments').mkdir()
        (provider / 'calendars/day.txt').write_text(''.join(d.isoformat() + '\n' for d in days))
        codes = [f'SH600{i:03d}' for i in range(200)]
        membership = ''.join(c + '\t2010-01-01\t2026-12-31\n' for c in codes)
        for name in ('all.txt', 'csi500.txt'):
            (provider / 'instruments' / name).write_text(membership)
        for code in codes + ['SH000905']:
            path = provider / 'features' / code.lower()
            path.mkdir(parents=True)
            slope = 1. if code == 'SH000905' else (int(code[-3:]) + 1) / 100
            monthly = [100.]
            for i in range(94):
                monthly.append(monthly[-1] * (1 + .001 + slope * (-.02, 0., .02)[i % 3]))
            values = [monthly[(d.year - 2018) * 12 + d.month - 12] for d in days]
            for field in ('open', 'high', 'low', 'close', 'volume', 'factor', 'amount', 'adjclose'):
                data = [1.] * len(days) if field in ('factor', 'volume') else values
                (path / (field + '.day.bin')).write_bytes(struct.pack('<' + 'f' * (len(days) + 1), 0., *data))
        members = {c: [('2010-01-01', '2026-12-31')] for c in codes}
        return provider, members

    def test_extension_hash_covers_names_only_entering_in2026(self):
        with tempfile.TemporaryDirectory() as directory:
            provider, members = self.fixture(Path(directory))
            members['SH600199'] = [('2026-01-01', '2026-12-31')]
            before = extension_input_hashes(provider, members, '2026-10-13')
            path = provider / 'features/sh600199/close.day.bin'
            path.write_bytes(path.read_bytes() + b'\x00\x00\x80\x3f')
            self.assertNotEqual(extension_input_hashes(provider, members, '2026-10-13')['price_files'],
                                before['price_files'])

    def test_cli_authenticates_emits34formations_and_refuses_changed_source(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            provider, members = self.fixture(base)
            old_targets, old_receipts = original_targets(QlibSnapshot(provider), members)
            for name, value in [('targets.json', old_targets), ('formation_receipts.json', old_receipts)]:
                write_json(base / 'original' / name, value)
            bindings = {'original/targets.json': digest(base / 'original/targets.json'),
                        'original/formation_receipts.json': digest(base / 'original/formation_receipts.json')}
            request = {'status': 'FROZEN_LOW_BETA60_CALENDAR_EXTENSION_FORMATIONS_ONLY',
                       'window': ['2024-01-02', '2026-10-13'], 'candidate_budget': 1,
                       'selected_family': 'low_beta60', 'expected_formations': 34,
                       'portfolio_returns_allowed': False, 'sealed_evidence': False,
                       'method_code_sha256': {n: digest(repo / n) for n in METHOD_FILES},
                       'pre2026_input_sha256': input_hashes(provider, members),
                       'extension_input_sha256': extension_input_hashes(provider, members, '2026-10-13'),
                       'local_source_sha256': bindings,
                       'public_evidence_sha256': {'experiments/qlib/low-beta60-intraday-development-verification.json':
                            digest(repo / 'experiments/qlib/low-beta60-intraday-development-verification.json')},
                       'reference_targets_file': 'original/targets.json',
                       'reference_receipts_file': 'original/formation_receipts.json'}
            request_path = base / 'request.json'
            write_json(request_path, request)
            out = base / 'out'
            args = ['--request', str(request_path), '--sha256', digest(request_path),
                    '--source-root', str(base), '--provider-uri', str(provider), '--output-dir', str(out)]
            self.assertEqual(main(args), 0)
            result = json.loads((out / 'summary.json').read_text())
            self.assertEqual(result['formations'], 34)
            self.assertEqual(result['extension_formations'], 10)
            self.assertFalse(result['portfolio_returns_computed'])
            self.assertFalse(result['objective_achieved'])
            receipts = json.loads((out / 'formation_receipts.json').read_text())
            self.assertEqual(receipts[-1]['latest_factor_price_read'], '2026-09-28')
            self.assertEqual((out / 'pre2026_targets.json').read_bytes(), (base / 'original/targets.json').read_bytes())
            self.assertEqual((out / 'pre2026_formation_receipts.json').read_bytes(),
                             (base / 'original/formation_receipts.json').read_bytes())
            with self.assertRaisesRegex(ValueError, 'preserve'):
                main(args)
            # All seven authentication failures must precede provider parsing.
            # A nonexistent provider would otherwise produce FileNotFoundError.
            for kind in ('external_sha', 'missing_method', 'missing_confirmation', 'missing_reference',
                         'changed_method_binding', 'changed_public_binding', 'changed_local_binding'):
                with self.subTest(authentication_failure=kind):
                    bad = copy.deepcopy(request)
                    message = 'frozen'
                    if kind == 'missing_method':
                        bad['method_code_sha256'].pop(next(iter(bad['method_code_sha256'])))
                        message = 'protocol'
                    elif kind == 'missing_confirmation':
                        bad['public_evidence_sha256'].clear()
                        message = 'confirmation binding'
                    elif kind == 'missing_reference':
                        bad['local_source_sha256'].pop('original/targets.json')
                        message = 'reference target'
                    elif kind == 'changed_method_binding':
                        bad['method_code_sha256'][next(iter(bad['method_code_sha256']))] = '0' * 64
                    elif kind == 'changed_public_binding':
                        bad['public_evidence_sha256'][next(iter(bad['public_evidence_sha256']))] = '0' * 64
                    elif kind == 'changed_local_binding':
                        bad['local_source_sha256']['original/targets.json'] = '0' * 64
                    bad_path = base / (kind + '.json')
                    write_json(bad_path, bad)
                    bad_args = ['--request', str(bad_path), '--sha256',
                                '0' * 64 if kind == 'external_sha' else digest(bad_path),
                                '--source-root', str(base), '--provider-uri', str(base / 'no-provider'),
                                '--output-dir', str(base / ('bad-' + kind))]
                    with self.assertRaisesRegex(ValueError, message):
                        main(bad_args)
                    self.assertFalse((base / ('bad-' + kind)).exists())
            (provider / 'features/sh600199/close.day.bin').write_bytes(b'changed source')
            args[-1] = str(base / 'changed-attempt')
            with self.assertRaisesRegex(ValueError, 'snapshot changed'):
                main(args)
            self.assertFalse((base / 'changed-attempt').exists())
