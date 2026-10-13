import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import pandas as pd
from core import watchlist
from strategy_core import StrategyRegistry
import strategy_core.preset
class WatchlistTests(unittest.TestCase):
 def setUp(self):watchlist._cache.clear()
 def test_quote_cache_mode_and_original_timestamp(self):
  with patch('core.watchlist.data_fetcher.get_current_price',return_value=dict(price=185.25,change_rate=.25)) as fetch:
   first=watchlist.quote('NASDAQ:AAPL','vps')
   second=watchlist.quote('NASDAQ:AAPL','vps')
   self.assertEqual(first,second);self.assertEqual(fetch.call_count,1)
   watchlist.quote('NASDAQ:AAPL','prod');self.assertEqual(fetch.call_count,2)
   self.assertIsNone(first['provider_time']);self.assertEqual(first['market_status'],'unknown')
 def test_failure_does_not_refresh_success_timestamp(self):
  with patch('core.watchlist.data_fetcher.get_current_price',side_effect=RuntimeError('offline')):
   with self.assertRaises(RuntimeError):watchlist.quote('NASDAQ:AAPL','vps')
  self.assertFalse(watchlist._cache)
 def test_us_dst_and_korean_cutoff(self):
  # During standard time 04:30 UTC is previous NY date; after spring DST it is current NY date.
  self.assertEqual(watchlist.cutoff('NASDAQ:AAPL',datetime(2025,1,2,4,30,tzinfo=timezone.utc)),'20250101')
  self.assertEqual(watchlist.cutoff('NASDAQ:AAPL',datetime(2025,7,2,4,30,tzinfo=timezone.utc)),'20250702')
  self.assertEqual(watchlist.cutoff('KOSPI:005930',datetime(2025,1,2,4,30,tzinfo=timezone.utc)),'20250102')
 def test_closed_daily_evidence_cache_and_dedup(self):
  schema=StrategyRegistry.get_list()[0]
  state=schema['builder_state']
  frame=pd.DataFrame([dict(date=d.strftime('%Y%m%d'),open=float(i+100),close=float(i+100),high=float(i+101),low=float(i+99),volume=100) for i,d in enumerate(pd.date_range('2024-01-01',periods=500))])
  today=frame.date.iloc[-1]
  with patch('core.watchlist.cutoff',return_value=today),patch('core.watchlist.data_fetcher.get_daily_prices',return_value=frame) as fetch:
   result=watchlist.signal('NASDAQ:AAPL','vps',state,schema['id'])
   self.assertEqual(result['basis_date'],frame.date.iloc[-2])
   self.assertEqual(result['basis'],'closed_daily')
   old=result['signal_id'];frame.loc[499,'close']=99999
   second=watchlist.signal('NASDAQ:AAPL','vps',state,schema['id'])
   self.assertEqual(old,second['signal_id']);self.assertEqual(result['fetched_at'],second['fetched_at']);self.assertEqual(fetch.call_count,1)
   watchlist._cache.clear();third=watchlist.signal('NASDAQ:AAPL','vps',state,schema['id'])
   self.assertEqual(result['action'],third['action']);self.assertEqual(result['indicators'],third['indicators'])
 def test_empty_and_insufficient_not_hold(self):
  schema=StrategyRegistry.get_list()[0]
  for frame in [pd.DataFrame(),pd.DataFrame([dict(date='20240101',close=10,open=10,high=10,low=10,volume=10)])]:
   with patch('core.watchlist.data_fetcher.get_daily_prices',return_value=frame),self.assertRaises(ValueError):watchlist.signal('NASDAQ:AAPL','vps',schema['builder_state'],schema['id'])
 def test_endpoint_readonly_auth_no_order_calls(self):
  from fastapi.testclient import TestClient
  from backend.main import app
  client=TestClient(app)
  with patch('backend.routers.watchlist.is_authenticated',return_value=False):self.assertEqual(client.get('/api/watchlist/quote/NASDAQ:AAPL').status_code,401)
  with patch('backend.routers.watchlist.is_authenticated',return_value=True),patch('core.watchlist.data_fetcher.get_current_price',return_value=dict(price=10.25,change_rate=1)),patch('core.us_paper.submit') as order:
   self.assertEqual(client.get('/api/watchlist/quote/NASDAQ:AAPL').status_code,200);order.assert_not_called()
 def test_quote_invalid_prices_are_errors(self):
  for data in [dict(price=0,change_rate=0),dict(price=float('nan'),change_rate=1),dict(price=10,change_rate=float('inf'))]:
   with patch('core.watchlist.data_fetcher.get_current_price',return_value=data),self.assertRaises(ValueError):watchlist.quote('NASDAQ:AAPL','vps')
