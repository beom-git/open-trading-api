"""Exchange-rate polling and stale-data tests. All network requests are mocked."""
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {}, clear=True), patch('pathlib.Path.home', return_value=Path(directory)), patch('os.path.expanduser', return_value=directory), patch('core.kis_config.dotenv_values', return_value={}):
        from core import exchange_rates as fx
        from backend.main import app

from fastapi.testclient import TestClient


def response(rate='1375.25', rows=None):
    return SimpleNamespace(isOK=lambda: True, getBody=lambda: SimpleNamespace(
        output1={'ovrs_nmix_prpr': rate},
        output2=rows if rows is not None else [
            {'stck_bsop_date': '20261014', 'stck_cntg_hour': '012345'},
            {'stck_bsop_date': '20261014', 'stck_cntg_hour': '012200'},
        ],
    ))


class ExchangeRateTests(unittest.TestCase):
    def setUp(self):
        for patcher in (patch.object(fx, '_snapshots', {}), patch.object(fx, '_attempts', {}), patch.object(fx, '_errors', {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_provider_request_and_distinct_timestamps(self):
        with patch.object(fx.ka, '_url_fetch', return_value=response()) as fetch:
            result = fx.get_usd_krw('vps')
        data = result['data']
        self.assertEqual(result['status'], 'success')
        self.assertEqual((data['base'], data['quote'], data['rate']), ('USD', 'KRW', 1375.25))
        self.assertEqual(data['source_quote_time'], '2026-10-14T01:23:45')
        self.assertIsNotNone(datetime.fromisoformat(data['fetched_at']).tzinfo)
        self.assertEqual(fetch.call_args.args[1], 'FHKST03030200')
        self.assertEqual(fetch.call_args.args[3]['FID_INPUT_ISCD'], 'FX@KRW')
        self.assertEqual(fetch.call_args.args[3]['FID_COND_MRKT_DIV_CODE'], 'X')

    def test_cache_coalesces_polls_and_retains_timestamp(self):
        with patch.object(fx.time, 'monotonic', return_value=100), patch.object(fx.ka, '_url_fetch', return_value=response()) as fetch:
            first = fx.get_usd_krw('vps')
            second = fx.get_usd_krw('vps')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first['data']['fetched_at'], second['data']['fetched_at'])

    def test_failed_refresh_keeps_last_valid_data_and_original_time(self):
        with patch.object(fx.time, 'monotonic', return_value=100), patch.object(fx.ka, '_url_fetch', return_value=response()):
            first = fx.get_usd_krw('vps')
        with patch.object(fx.time, 'monotonic', return_value=131), patch.object(fx.ka, '_url_fetch', side_effect=TimeoutError('not exposed')) as fetch:
            failed = fx.get_usd_krw('vps')
            retry = fx.get_usd_krw('vps')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(failed['status'], 'error')
        self.assertTrue(failed['stale'])
        self.assertEqual(failed['data'], first['data'])
        self.assertNotIn('not exposed', failed['message'])
        self.assertEqual(retry['data']['fetched_at'], first['data']['fetched_at'])
        with patch.object(fx.time, 'monotonic', return_value=162), patch.object(fx.ka, '_url_fetch', return_value=response('1400.5')):
            recovered = fx.get_usd_krw('vps')
        self.assertFalse(recovered['stale'])
        self.assertEqual(recovered['data']['rate'], 1400.5)

    def test_bad_rates_never_enable_conversion(self):
        for rate in ('0', '-1', 'NaN', 'inf', '', 'unavailable'):
            with self.subTest(rate=rate), patch.object(fx, '_attempts', {}), patch.object(fx.ka, '_url_fetch', return_value=response(rate)):
                result = fx.get_usd_krw('vps')
                self.assertEqual(result['status'], 'error')
                self.assertIsNone(result['data'])

    def test_source_time_is_not_invented(self):
        rows = [{'stck_bsop_date': 'invalid', 'stck_cntg_hour': 'xxxxxx'}]
        with patch.object(fx.ka, '_url_fetch', return_value=response(rows=rows)):
            result = fx.get_usd_krw('vps')
        self.assertIsNone(result['data']['source_quote_time'])
        self.assertIsNotNone(result['data']['fetched_at'])

    def test_modes_have_separate_caches(self):
        with patch.object(fx.ka, '_url_fetch', side_effect=[response(), response('1400')]) as fetch:
            paper = fx.get_usd_krw('vps')
            live = fx.get_usd_krw('prod')
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(paper['data']['rate'], 1375.25)
        self.assertEqual(live['data']['rate'], 1400)

    def test_endpoint_requires_existing_auth_and_does_not_log_in(self):
        with TestClient(app) as client, patch('backend.routers.market.is_authenticated', return_value=False), patch('backend.routers.market.authenticate') as login, patch.object(fx.ka, '_url_fetch') as fetch:
            result = client.get('/api/market/exchange-rate').json()
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['data'])
        login.assert_not_called()
        fetch.assert_not_called()

    def test_endpoint_uses_current_mode(self):
        with TestClient(app) as client, patch('backend.routers.market.is_authenticated', return_value=True), patch('backend.routers.market.get_current_mode', return_value='vps'), patch.object(fx.ka, '_url_fetch', return_value=response()):
            result = client.get('/api/market/exchange-rate').json()
        self.assertEqual(result['refresh_interval_seconds'], 30)
        self.assertEqual(result['data']['rate'], 1375.25)


if __name__ == '__main__':
    unittest.main()
