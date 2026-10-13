"""Fixture-based integration tests. Never issue credentials or broker orders."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.instruments import parse_instrument
from core.symbol_master import make_symbol, parse_kis_domestic, parse_kis_us, load_master, save_master

with tempfile.TemporaryDirectory() as directory:
    with patch.dict(os.environ, {}, clear=True), patch('pathlib.Path.home', return_value=Path(directory)), patch('os.path.expanduser', return_value=directory), patch('core.kis_config.dotenv_values', return_value={}):
        import kis_auth as ka
        from core import data_fetcher
        from core.signal import Signal, Action
        from core.order_executor import OrderExecutor
        from backend.main import app
        from backend.routers import symbols
        from strategy_core.executor import execute_custom_file
        from strategy_core.dsl.parser import parse_strategy
        from strategy_core.dsl.codegen import StrategyCodeGenerator

from fastapi.testclient import TestClient


def broker_response(**outputs):
    return SimpleNamespace(isOK=lambda: True, getBody=lambda: SimpleNamespace(**outputs))


def daily_rows(count=100, end='2026-10-13'):
    import pandas as pd
    dates = pd.bdate_range(end=end, periods=count)
    return [dict(xymd=date.strftime('%Y%m%d'), open='10.1250', high='11.25', low='9.75', clos='10.8750', tvol='1200') for date in reversed(dates)]


def us_line(ticker='AAPL', exchange='NAS', kind='2'):
    return '\t'.join(['US', '22', exchange, '나스닥', ticker, exchange+ticker, '애플', 'APPLE INC', kind, 'USD']).encode('cp949')


class MasterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for patcher in (patch.object(symbols, 'MASTER_DIR', self.root), patch.object(symbols, '_symbol_cache', {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_sources_normalize_to_same_schema(self):
        domestic = b'005930   ' + b'KR7005930003' + '삼성전자'.encode('euc-kr').ljust(40, b' ')
        kr, us = parse_kis_domestic(domestic, 'kospi')[0], parse_kis_us(us_line(), 'nasdaq')[0]
        self.assertEqual(set(kr), set(us))
        self.assertEqual((kr['id'], kr['ticker'], kr['currency']), ('KOSPI:005930', '005930', 'KRW'))
        self.assertEqual((us['id'], us['market'], us['currency']), ('NASDAQ:AAPL', 'US', 'USD'))
        self.assertEqual(parse_kis_us(us_line(kind='1'), 'nasdaq'), [])
        self.assertEqual(parse_kis_us(us_line(exchange='NYS'), 'nasdaq'), [])
        self.assertEqual(parse_kis_us(us_line(kind='3'), 'nasdaq')[0]['ticker'], 'AAPL')
        self.assertEqual(parse_kis_domestic(domestic.replace(b'005930', b'0000D0'), 'kospi')[0]['id'], 'KOSPI:0000D0')

    def test_json_roundtrip_and_legacy_csv(self):
        stock = make_symbol('BRK.B', 'nyse', '버크셔, B', 'BERKSHIRE "B", INC')
        save_master(self.root, 'nyse', [stock])
        self.assertEqual(load_master(self.root, 'nyse'), [stock])
        self.assertEqual(json.loads((self.root/'nyse.json').read_text())['schema_version'], 1)
        (self.root/'kospi.csv').write_text('code,name,exchange\n005930,삼성전자,kospi\n', encoding='utf-8-sig')
        self.assertEqual(load_master(self.root, 'kospi')[0]['id'], 'KOSPI:005930')
        self.assertFalse((self.root/'kospi.json').exists())
        with self.assertRaises(ValueError):
            save_master(self.root, 'nyse', [stock | {'currency': 'KRW'}])
        self.assertEqual(load_master(self.root, 'nyse'), [stock])

    def test_search_and_legacy_detail_and_status(self):
        save_master(self.root, 'kospi', [make_symbol('005930', 'kospi', '삼성전자')])
        save_master(self.root, 'nasdaq', [make_symbol('AAPL', 'nasdaq', '애플', 'APPLE INC')])
        save_master(self.root, 'nyse', [make_symbol('A', 'nyse', '애질런트', 'AGILENT'), make_symbol('BRK/B', 'nyse', '버크셔 B')])
        with TestClient(app) as client:
            for query in ('aapl', '애플', 'APPLE'):
                self.assertEqual(client.get('/api/symbols/search', params={'q': query}).json()['items'][0]['id'], 'NASDAQ:AAPL')
            self.assertEqual(client.get('/api/symbols/search?q=A&limit=1').json()['items'][0]['id'], 'NYSE:A')
            self.assertEqual(client.get('/api/symbols/search?q=AAPL&exchange=kospi').json()['total'], 0)
            self.assertEqual(client.get('/api/symbols/search?q=AAPL&exchange=nasdaq').json()['total'], 1)
            for code in ('005930', 'KOSPI:005930'):
                self.assertEqual(client.get(f'/api/symbols/{code}').json()['data']['id'], 'KOSPI:005930')
            status = client.get('/api/symbols/status').json()
            self.assertEqual(status['total_count'], 4)
            self.assertEqual(client.get('/api/symbols/NYSE%3ABRK%2FB').json()['data']['ticker'], 'BRK/B')
            self.assertEqual(len(status['exchanges']), 5)
            self.assertTrue(status['needs_update'])

    def test_failed_collection_keeps_previous_master(self):
        previous = make_symbol('AAPL', 'nasdaq', '애플')
        save_master(self.root, 'nasdaq', [previous])
        fake_client = AsyncMock()
        fake_client.__aenter__.return_value.get.return_value = Mock(content=b'<html>Error</html>')
        with patch.object(symbols.httpx, 'AsyncClient', return_value=fake_client):
            items, error = asyncio.run(symbols._download_and_parse('nasdaq'))
        self.assertEqual(items, [])
        self.assertIsNotNone(error)
        self.assertEqual(load_master(self.root, 'nasdaq'), [previous])


class MarketAndExecutionTests(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.object(ka, '_url_fetch', side_effect=AssertionError('Unexpected broker request')),
            patch.object(data_fetcher, '_assert_trenv_ready', return_value=True),
            patch('backend.routers.strategy.is_authenticated', return_value=True),
            patch('backend.routers.strategy.get_current_mode', return_value='vps'),
            patch('backend.routers.strategy._api_sleep'),
            patch('backend.routers.strategy.get_stock_name', side_effect=lambda code: code),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_ids_and_decimal_signals(self):
        self.assertEqual(parse_instrument('nasdaq:aapl').id, 'NASDAQ:AAPL')
        self.assertEqual(parse_instrument('005930').ticker, '005930')
        self.assertEqual(parse_instrument('0000D0').ticker, '0000D0')
        for invalid in ('AAPL', 'LSE:ABC', 'NASDAQ:', 'NASDAQ:../../etc'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_instrument(invalid)
        self.assertEqual(Signal('NASDAQ:AAPL', '애플', Action.BUY, 0.7, 'test', target_price=123.4567).target_price, 123.4567)

    def test_history_pagination_and_precision(self):
        first, second = daily_rows(), daily_rows(end='2026-05-26')
        with patch.object(ka, '_url_fetch', side_effect=[broker_response(output2=first), broker_response(output2=second)]) as fetch:
            frame = data_fetcher.get_daily_prices('NASDAQ:AAPL', 150)
        self.assertEqual(len(frame), 150)
        self.assertTrue(frame['date'].is_monotonic_increasing)
        self.assertTrue(frame['date'].is_unique)
        self.assertEqual(frame['close'].iloc[-1], 10.875)
        params = fetch.call_args_list[0].args[3]
        self.assertEqual((params['EXCD'], params['SYMB'], params['MODP']), ('NAS', 'AAPL', '1'))
        self.assertLess(fetch.call_args_list[1].args[3]['BYMD'], first[-1]['xymd'])

    def test_repeated_page_and_invalid_data(self):
        with patch.object(ka, '_url_fetch', return_value=broker_response(output2=daily_rows(2))) as fetch:
            self.assertEqual(len(data_fetcher.get_daily_prices('NYSE:IBM', 100)), 2)
            self.assertEqual(fetch.call_count, 2)
        bad = daily_rows(1)
        bad[0]['clos'] = 'NaN'
        with patch.object(ka, '_url_fetch', return_value=broker_response(output2=bad)), self.assertRaises(ValueError):
            data_fetcher.get_daily_prices('NYSE:IBM', 1)

    def test_quote_precision_currency_and_routing(self):
        fixture = dict(last='123.4567', base='124.0000', high='125.5', low='122.25', tvol='500', h52p='150.75', l52p='70.25')
        with patch('backend.routers.market.ensure_authenticated', return_value=True), patch.object(ka, '_url_fetch', return_value=broker_response(output=fixture)) as fetch:
            response = self.client.get('/api/market/price/NYSE%3ABRK%2FB').json()
        self.assertEqual(response['status'], 'success')
        self.assertEqual(response['data']['price'], 123.4567)
        self.assertEqual(response['data']['change'], -0.5433)
        self.assertEqual(response['data']['currency'], 'USD')
        self.assertEqual(fetch.call_args.args[3]['EXCD'], 'NYS')
        self.assertEqual(fetch.call_args.args[3]['SYMB'], 'BRK/B')

    def test_domestic_id_routes_to_domestic_api(self):
        with patch.object(ka, '_url_fetch', return_value=broker_response(output={'stck_prpr': '72000'})) as fetch:
            self.assertEqual(data_fetcher.get_current_price('KOSPI:005930')['price'], 72000)
        self.assertIn('/domestic-stock/', fetch.call_args.args[0])
        self.assertEqual(fetch.call_args.args[3]['FID_INPUT_ISCD'], '005930')

    def test_preset_and_builder_execute_us_ids(self):
        from strategy_core import StrategyRegistry
        builder = StrategyRegistry.get('golden_cross')['builder_state']
        for request in [dict(strategy_id='golden_cross'), dict(strategy_id='local_test', builder_state=builder)]:
            with self.subTest(request=request['strategy_id']), patch.object(ka, '_url_fetch', return_value=broker_response(output2=daily_rows())):
                response = self.client.post('/api/strategies/execute', json=request | {'stocks': ['NASDAQ:AAPL'], 'params': {}})
            self.assertEqual(response.status_code, 200)
            result = response.json()['results'][0]
            self.assertNotEqual(result['action'], 'ERROR', result['reason'])
            self.assertEqual(result['currency'], 'USD')
            self.assertTrue(result['order_supported'])

    def test_custom_file_execution(self):
        code = StrategyCodeGenerator().generate(parse_strategy(name='test_global', name_ko='Global', buy_condition='close > open', sell_condition='close < open'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'strategy_test_global.py'
            path.write_text(code)
            with patch('strategy_core.executor.get_generated_strategy_file', return_value=path), patch.object(ka, '_url_fetch', return_value=broker_response(output2=daily_rows())):
                results = execute_custom_file('test_global', ['AMEX:SPY'], lambda *args: None, lambda code: code, lambda: None)
            self.assertEqual(results[0]['action'], 'BUY')
            self.assertEqual(results[0]['currency'], 'USD')

    def test_price_indicators_keep_sub_dollar_values(self):
        import pandas as pd
        from core import indicators
        frame = pd.DataFrame({'close': [0.1234, 0.2345], 'high': [0.3456, 0.4567], 'low': [0.0123, 0.1234]})
        self.assertEqual(indicators.get_latest_close(frame), 0.2345)
        self.assertEqual(indicators.get_prev_close(frame), 0.1234)
        self.assertEqual(indicators.calc_high_since(frame, 2), 0.4567)
        self.assertEqual(indicators.calc_low_since(frame, 2), 0.0123)

    def test_all_presets_run_mixed_market_inputs(self):
        from strategy_core import StrategyRegistry
        def fetch(path, tr_id, continuation, params):
            if 'dailyprice' in path:
                return broker_response(output2=daily_rows())
            if 'inquire-daily-itemchartprice' in path:
                rows = [dict(stck_bsop_date=r['xymd'], stck_oprc='10000', stck_hgpr='12000', stck_lwpr='9000', stck_clpr='11000', acml_vol='100') for r in daily_rows()]
                return broker_response(output2=rows)
            if 'price-detail' in path:
                return broker_response(output=dict(last='10.125', base='10.25', h52p='12.5', l52p='5'))
            return broker_response(output=dict(stck_prpr='11000', w52_hgpr='12000'))
        for strategy in StrategyRegistry.get_list():
            with self.subTest(strategy=strategy['id']), patch.object(ka, '_url_fetch', side_effect=fetch):
                response = self.client.post('/api/strategies/execute', json={'strategy_id': strategy['id'], 'stocks': ['KOSPI:005930', 'NASDAQ:AAPL']}).json()
                self.assertEqual(response['status'], 'success', response)
                self.assertEqual(len(response['results']), 2)
                for result in response['results']:
                    self.assertNotEqual(result['action'], 'ERROR', result['reason'])
                self.assertTrue(response['results'][0]['order_supported'])
                self.assertTrue(response['results'][1]['order_supported'])

    def test_broker_failure_is_error_signal(self):
        failure = SimpleNamespace(isOK=lambda: False, getErrorCode=lambda: 'TEST_DENIED')
        with patch.object(ka, '_url_fetch', return_value=failure):
            result = self.client.post('/api/strategies/execute', json={'strategy_id': 'golden_cross', 'stocks': ['NASDAQ:AAPL']}).json()['results'][0]
        self.assertEqual(result['action'], 'ERROR')
        self.assertIn('TEST_DENIED', result['reason'])

    def test_us_domestic_only_operations_never_call_broker(self):
        response = self.client.post('/api/orders/execute', json=dict(stock_code='NASDAQ:AAPL', stock_name='애플', action='BUY', order_type='limit', price=123, quantity=1, signal_reason='test'))
        self.assertEqual(response.json()['status'], 'error')
        self.assertIn('해외 주문', response.json()['message'])
        calls = [lambda: OrderExecutor().execute_signal(Signal('NASDAQ:AAPL', '애플', Action.BUY, 1, 'test')), lambda: data_fetcher.get_buyable_amount('NASDAQ:AAPL', 100), lambda: data_fetcher.get_orderbook('NASDAQ:AAPL'), lambda: data_fetcher.cancel_order('test', 'NASDAQ:AAPL', 1)]
        for call in calls:
            with self.assertRaises(ValueError):
                call()
        ka._url_fetch.assert_not_called()

    def test_domestic_order_normalizes_id_before_execution(self):
        signal = Signal('KOSPI:005930', '삼성전자', Action.BUY, 0.7, 'test', target_price=72000, quantity=1)
        executor = OrderExecutor()
        with patch.object(executor, '_execute_order') as order:
            executor.execute_signal(signal)
        self.assertEqual(order.call_args.kwargs['signal'].stock_code, '005930')
        ka._url_fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
