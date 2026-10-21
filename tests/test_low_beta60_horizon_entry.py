import importlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.fundamental_query_journal import file_sha


class HorizonEntryTests(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module('scripts.capture_low_beta60_horizon_sources')
        except ModuleNotFoundError:
            self.fail('authenticated horizon source entry is absent')

    # A bad external request checksum must fail before output creation or SDK access.
    def test_changed_request_rejects_before_source_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); request = root / 'request.json'; request.write_text('{}')
            out = root / 'out'
            with self.assertRaises(ValueError):
                api.main(['--request', str(request), '--expected-request-sha256', '0' * 64,
                          '--source-root', str(root), '--output-dir', str(out)])
            self.assertFalse(out.exists())

    # Calendar-first capture must retain provider login denial and never retry it.
    def test_calendar_login_failure_keeps_provider_code_and_single_reservation(self):
        api = self.api()
        class SDK:
            def login(self):
                return type('Response', (), {'error_code': '10001001', 'error_msg': 'synthetic denial'})()
            def query_trade_dates(self, **kwargs):
                raise AssertionError('denied login must not query calendar')
            def logout(self):
                return type('Response', (), {'error_code': '0', 'error_msg': 'success'})()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            session = api.HorizonSession(out, '1' * 64, SDK())
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    session('CN_STOCK_CALENDAR', 'calendar', {'start_date': '2026-10-14', 'end_date': '2026-10-20'})
            session.close()
            response = json.loads((out / 'login-response-1.json').read_text())
            self.assertEqual('10001001', response['error_code'])
            self.assertEqual('synthetic denial', response['error_msg'])
            self.assertEqual(1, len(list(out.glob('login-reserved-*.json'))))
            self.assertTrue((out / 'logout-response.json').exists())

    # The first calendar query and subsequent stock query share one real SDK login.
    def test_calendar_then_stock_share_one_admin_login_and_keep_decoded_envelopes(self):
        api = self.api(); calls = []
        class Result:
            error_code = '0'; error_msg = 'success'; fields = ['calendar_date', 'is_trading_day']
            def next(self): return False
        class SDK:
            def login(self): calls.append('login'); return Result()
            def query_trade_dates(self, **kwargs): calls.append(('calendar', kwargs)); return Result()
            def query_adjust_factor(self, symbol, **kwargs): calls.append(('adjustment', symbol, kwargs)); return Result()
            def logout(self): calls.append('logout'); return Result()
        with tempfile.TemporaryDirectory() as d:
            session = api.HorizonSession(Path(d), '1' * 64, SDK())
            a = session('CN_STOCK_CALENDAR', 'calendar', {'start_date': '2026-10-14', 'end_date': '2026-10-20'})
            b = session('SH600000', 'adjustments', {'start_date': '2026-10-14', 'end_date': '2026-10-20'})
            session.close()
            self.assertEqual(['provider_response'], a[0]); self.assertEqual(['provider_response'], b[0])
            self.assertEqual(['login', ('calendar', {'start_date': '2026-10-14', 'end_date': '2026-10-20'}),
                              ('adjustment', 'sh.600000', {'start_date': '2026-10-14', 'end_date': '2026-10-20'}), 'logout'], calls)


if __name__ == '__main__':
    unittest.main()
