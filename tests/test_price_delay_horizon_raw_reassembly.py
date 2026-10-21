import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import reassemble_price_delay_horizon_raw as api
from scripts.fundamental_query_journal import QueryJournal
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS, DIVIDEND_FIELDS, ADJUST_FIELDS
from tests.test_value_momentum_raw_extension_sources import prefix, envelope, DAYS
from tests.test_value_momentum_raw_reassembly_v2 import fixtures


class PriceDelayHorizonRawReassemblyTests(unittest.TestCase):
    def test_coherently_rebound_tree_cannot_replace_audited_packet_calendar_or_query(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            files = {'codes/SH603233.json': '{}', 'errors/SH603233.json': '{}',
                'calendar.json': '{"sessions":["2023-12-29"]}', 'cleanup.json': '{}',
                'source-postcheck.json': '{}', 'coordinate-reference-proofs.json': '{}'}
            files.update({f'queries/{i}/{kind}.json': '{}' for i in range(345)
                          for kind in ('request', 'reserved-1', 'response-1')})
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            tree = api.tree_hashes(root)
            m = {'per_code_sha256': {'SH603233': tree['codes/SH603233.json']},
                 'errors_sha256': {'SH603233': tree['errors/SH603233.json']},
                 'calendar_sha256': tree['calendar.json']}
            scope = {field: tree[name] for name, field in [('cleanup.json', 'cleanup_sha256'),
                ('source-postcheck.json', 'postcheck_sha256'),
                ('coordinate-reference-proofs.json', 'coordinate_reference_proofs_sha256')]}
            audit = {'query_artifact_sha256': {n: h for n, h in tree.items() if n.startswith('queries/')}}
            api.verify_source_capture_bindings(root, m, scope, audit, ['2023-12-29'])
            for name in ('codes/SH603233.json', 'errors/SH603233.json', 'calendar.json',
                         'cleanup.json', 'queries/0/response-1.json'):
                path = root / name
                path.write_text('{"changed_but_coherent_new_tree":true}')
                rebound = api.tree_hashes(root)
                self.assertNotEqual(rebound[name], tree[name])
                with self.subTest(name=name), self.assertRaises(ValueError):
                    api.verify_source_capture_bindings(root, m, scope, audit, ['2023-12-29'])
                path.write_text(files[name])
            with self.assertRaises(ValueError):
                api.verify_source_capture_bindings(root, m, scope, audit, ['2023-12-29', '2024-01-02'])

    def test_local_reassembly_preserves_all_inputs_and_never_falls_back_to_fetch(self):
        old, fresh, review = fixtures()
        for packet in (old, fresh):
            packet['instrument'] = 'SH603233'
            for field in ('bars', 'distributions', 'adjustments'):
                for row in packet[field]:
                    row['code'] = 'sh.603233'
        review.update(instrument='SH603233', file='SH603233.pdf')
        baseline = prefix('SH603233')
        def seed(code, component, parameters):
            fields, rows = {'daily': (BAR_FIELDS, fresh['bars']),
                'dividend2026': (DIVIDEND_FIELDS, fresh['distributions']),
                'adjustments': (ADJUST_FIELDS, fresh['adjustments'])}[component]
            return envelope(fields, [[r[k] for k in fields] for r in rows])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            api.fetch_packet(QueryJournal(root, max_queries=3, max_attempts=1), 'SH603233', 'frozen', seed, baseline)
            inputs = copy.deepcopy((baseline, old, fresh, review))
            files = api.tree_hashes(root)
            result, proof = api.make_conflict_packet(api.ReadOnlyJournal(root), 'frozen', baseline, DAYS, old, review)
            self.assertEqual(result['bars'], baseline['bars'] + fresh['bars'])
            self.assertEqual(result['adjustments'], fresh['adjustments'])
            self.assertEqual(result['distributions'], [])
            self.assertEqual(proof['ratio_exact'], '10/11')
            self.assertEqual(api.tree_hashes(root), files)
            self.assertEqual((baseline, old, fresh, review), inputs)
            with self.assertRaises(ValueError):
                api.make_conflict_packet(api.ReadOnlyJournal(root), 'missing-query', baseline, DAYS, old, review)
            with self.assertRaises(ValueError):
                api.make_conflict_packet(api.ReadOnlyJournal(root), 'frozen', baseline, DAYS, old,
                                        {**review, 'cash_per_original_share_CNY': '0'})
            self.assertEqual(api.tree_hashes(root), files)

    def test_invalid_request_and_existing_output_cannot_write_or_fetch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(api, 'forbidden_fetch') as fetch:
            base = Path(d)
            request = base / 'request.json'
            request.write_text('{}')
            out = base / api.OUTPUT
            args = ['--source-root', d, '--request', str(request),
                '--expected-request-sha256', '0' * 64, '--output-dir', str(out)]
            with self.assertRaises(ValueError):
                api.main(args)
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaisesRegex(ValueError, 'preserve'):
                api.main(args)
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
