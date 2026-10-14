"""All account and external order calls are replaced by fixtures."""
import os, tempfile, threading, unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from core import auto_trading as auto, us_calendar

class AutoTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.current=datetime(2026,10,14,15,tzinfo=timezone.utc)
  self.decision=dict(action='BUY',basis_date='20261013',indicators={},buy=None,sell=None)
  self.patches=[patch.dict(os.environ,{'KIS_ORDER_JOURNAL':self.tmp.name+'/journal.db'})]
  self.mocks={}
  replacements={
   'core.auto_trading.now':self.current,'core.auto_trading.is_authenticated':True,'core.auto_trading.get_current_mode':'vps',
   'core.auto_trading.ka.isPaperTrading':True,'core.auto_trading.ka.getTREnv':SimpleNamespace(my_acct='fake',my_prod='01'),
   'backend.routers.us_paper.is_authenticated':True,'backend.routers.us_paper.get_current_mode':'vps',
   'core.auto_trading.us_stock.holdings':[dict(instrument_id=auto.CODE,quantity=7,orderable_quantity=7)],'core.auto_trading.us_stock.pending':[],
   'core.auto_trading.us_stock.buyable':dict(amount=10000,quantity=100),
   'core.auto_trading.overseas_data.latest_minute':dict(price='100',provider_at=self.current.isoformat()),
   'core.auto_trading.us_stock.submit':dict(status='accepted',order_no='42'),
   'core.auto_trading.us_stock.cancel':dict(status='accepted'),'core.auto_trading.us_stock.order_history':[]}
  for target,value in replacements.items():
   p=patch(target,return_value=value);self.patches.append(p);self.mocks[target.split('.')[-1]]=p
  for p in self.patches:
   mock=p.start()
   for name,original in list(self.mocks.items()):
    if original is p:self.mocks[name]=mock
  p=patch.object(auto.watchlist,'signal',side_effect=lambda *a:self.decision.copy());p.start();self.patches.append(p)
  self.engine=auto.Engine(self.tmp.name+'/auto.db');self.assertTrue(self.engine.acquire());self.engine.start('vps')
  with self.engine.locked() as (_,s):s['basis']='20261012'
 def tearDown(self):
  self.engine.release()
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def order(self):return self.engine.snapshot()['orders'][0]
 def row(self,filled=0,remaining=9):
  return dict(order_no='42',instrument_id=auto.CODE,action='BUY',quantity=9,filled=filled,remaining=remaining,cancelled=False,rejected=False)
 def reset_signal(self):
  with self.engine.locked() as (db,s):s['basis']='20261012';s['next_run']=None;db.execute('DELETE FROM signals')
 def test_decimal_price_budget_and_sell_ratio(self):
  cfg=auto.Settings().model_dump(mode='json');r=auto.calculation('10000','100','100',cfg)
  self.assertEqual((r['quantity'],r['limit_price_usd']),(9,'100.10'));self.assertLessEqual(float(r['total_usd'])*1.01,1000)
  self.assertEqual(auto.calculation(10000,2,100,cfg)['quantity'],2)
  self.assertEqual(auto.calculation(10,100,'.1234',cfg)['limit_price_usd'],'0.1236')
  cfg['sell_percent']='50';self.assertEqual(auto.calculation(0,0,100,cfg,'SELL',9)['quantity'],4)
  self.assertEqual(auto.calculation(0,0,100,cfg,'SELL',9)['limit_price_usd'],'99.90')
 def test_read_preview_no_orders(self):
  self.engine.snapshot();r=self.engine.preview();self.assertEqual(r['preview']['available_usd'],'10000');self.assertEqual(r['manual'],7)
  self.mocks['submit'].assert_not_called()
 def test_baseline_duplicate_and_concurrent_ticks(self):
  self.engine.start('vps');self.engine.tick();self.assertFalse(self.engine.snapshot()['orders'])
  self.reset_signal();self.mocks['order_history'].return_value=[self.row()]
  other=auto.Engine(self.engine.path);self.assertFalse(other.acquire())
  threads=[threading.Thread(target=self.engine.tick) for _ in range(2)]
  for t in threads:t.start()
  for t in threads:t.join(5);self.assertFalse(t.is_alive())
  self.engine.tick(self.current+timedelta(seconds=60));self.assertEqual(self.mocks['submit'].call_count,1)
 def test_partial_fill_cancel_after_stop(self):
  self.engine.tick();self.engine.stop();self.mocks['order_history'].return_value=[self.row(3,6)]
  self.engine.tick();self.assertEqual(self.engine.snapshot()['owned'],3);self.assertEqual(self.order()['status'],'partial')
  self.engine.tick(self.current+timedelta(seconds=301));self.assertEqual(self.order()['status'],'cancel_pending')
  self.engine.tick(self.current+timedelta(seconds=331));self.assertEqual(self.mocks['cancel'].call_count,1)
  self.mocks['order_history'].return_value=[self.row(4,0),dict(order_no='43',instrument_id=auto.CODE,cancelled=True,original_order_no='42')]
  self.engine.tick();self.assertEqual(self.order()['status'],'cancelled');self.assertEqual(self.engine.snapshot()['owned'],4)
 def test_full_fill_sell_manual_protection(self):
  self.engine.tick();self.mocks['order_history'].return_value=[self.row(9,0)];self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=16,orderable_quantity=16)];self.engine.tick();self.assertEqual(self.engine.snapshot()['owned'],9)
  self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=16,orderable_quantity=16)]
  self.decision['action']='SELL';self.reset_signal()
  with self.engine.locked() as (_,s):s['config']['sell_percent']='50'
  self.engine.tick();self.assertEqual(self.order()['quantity'],4);self.assertEqual(self.order()['action'],'SELL');self.assertEqual(self.engine.snapshot()['manual'],7)
 def test_no_additional_buy(self):
  with self.engine.locked() as (_,s):s['owned']=2
  self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=9,orderable_quantity=9)]
  self.engine.tick();self.mocks['submit'].assert_not_called()
 def test_stale_missing_future_quote(self):
  for seconds in (-121,10):
   self.mocks['latest_minute'].return_value=dict(price=100,provider_at=(self.current+timedelta(seconds=seconds)).isoformat())
   self.reset_signal();self.engine.tick();self.mocks['submit'].assert_not_called()
  self.mocks['latest_minute'].side_effect=KeyError('provider_at');self.reset_signal();self.engine.tick();self.mocks['submit'].assert_not_called()
 def test_mode_account_auth_change(self):
  for target,value in [('get_current_mode','prod'),('is_authenticated',False),('scope','different')]:
   with self.engine.locked() as (_,s):s['running']=True
   with patch.object(auto,target,return_value=value):self.engine.tick()
   self.assertFalse(self.engine.snapshot()['running'])
  self.mocks['submit'].assert_not_called()
 def test_account_errors_and_pending(self):
  self.mocks['holdings'].side_effect=RuntimeError('balance unavailable');self.engine.tick();self.mocks['submit'].assert_not_called()
  self.assertIn('balance unavailable',self.engine.snapshot()['reason'])
  with self.engine.locked() as (_,s):s['running']=True
  self.mocks['holdings'].side_effect=None;self.mocks['pending'].return_value=[dict(instrument_id=auto.CODE)];self.reset_signal();self.engine.tick();self.mocks['submit'].assert_not_called()
 def test_timeout_restart_no_retry(self):
  self.mocks['submit'].side_effect=TimeoutError();self.engine.tick();self.assertEqual(self.order()['status'],'unknown')
  self.engine.tick();self.engine.release();self.engine=auto.Engine(self.engine.path);self.engine.acquire();self.engine.tick()
  self.assertFalse(self.engine.snapshot()['running']);self.assertEqual(self.mocks['submit'].call_count,1)
  with self.assertRaises(ValueError):self.engine.start('vps')
 def test_restart_fill_recovery(self):
  self.engine.tick();self.engine.release();self.engine=auto.Engine(self.engine.path);self.engine.acquire()
  self.mocks['order_history'].return_value=[self.row(5,4)];self.engine.tick();self.engine.tick()
  self.assertEqual(self.engine.snapshot()['owned'],5);self.assertFalse(self.engine.snapshot()['running'])
 def test_recover_known_acceptance_from_journal_without_resend(self):
  self.engine.tick()
  with self.engine.locked() as (db,_):
   order=self.engine.orders(db)[0]
   order['status']='unknown';order.pop('order_no');self.engine.save_order(db,order)
  self.engine.release();self.engine=auto.Engine(self.engine.path);self.engine.acquire()
  self.mocks['order_history'].return_value=[self.row(2,7)];self.engine.tick()
  self.assertEqual(self.order()['status'],'partial');self.assertEqual(self.engine.snapshot()['owned'],2)
  self.assertEqual(self.mocks['submit'].call_count,1)
 def test_provider_sell_limit_and_rejection(self):
  with self.engine.locked() as (_,s):s['owned']=4;s['manual']=7
  self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=11,orderable_quantity=2)]
  self.decision['action']='SELL';self.mocks['submit'].return_value=dict(status='rejected')
  self.engine.tick();self.assertEqual(self.order()['quantity'],2);self.assertEqual(self.order()['status'],'rejected')
  self.assertEqual(self.engine.snapshot()['owned'],4)
 def test_missing_sellable_quantity_and_balance_mismatch(self):
  with self.engine.locked() as (_,s):s['owned']=4;s['manual']=7
  self.decision['action']='SELL';self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=11)]
  self.engine.tick();self.mocks['submit'].assert_not_called()
  self.mocks['holdings'].return_value=[dict(instrument_id=auto.CODE,quantity=3)]
  self.reset_signal();self.engine.tick();self.assertFalse(self.engine.snapshot()['running'])
  self.mocks['submit'].assert_not_called()
 def test_api_settings_mode_and_read(self):
  client=TestClient(app)
  with patch('backend.routers.auto_trading.service',return_value=self.engine):
   self.assertEqual(client.put('/api/auto-trading/settings',json={'buy_percent':0}).status_code,422)
   self.assertEqual(client.put('/api/auto-trading/settings',json={'sell_percent':30}).status_code,409)
   client.post('/api/auto-trading/stop');r=client.put('/api/auto-trading/settings',json={'sell_percent':30}).json();self.assertEqual(r['config']['sell_percent'],'30')
   self.assertEqual(client.post('/api/auto-trading/start',json={'mode':'prod'}).status_code,409)
   client.get('/api/auto-trading');client.get('/api/auto-trading/history');self.mocks['submit'].assert_not_called()
 def test_regular_hours_old_signal(self):
  self.engine.tick(self.current.replace(hour=12));self.mocks['submit'].assert_not_called()
  self.decision['basis_date']='20261012'
  with self.engine.locked() as (_,s):s['basis']='20261011';s['next_run']=None
  self.engine.tick();self.mocks['submit'].assert_not_called()

class CalendarTests(unittest.TestCase):
 def test_dst_holidays_early_close_range(self):
  for date,hour,opened in [('2026-03-09',13,False),('2026-03-09',14,True),('2026-11-02',14,False),('2026-11-02',15,True),('2026-11-26',15,False),('2026-11-27',17,True),('2026-11-27',18,False),('2026-12-24',18,False)]:
   self.assertEqual(us_calendar.session(datetime.fromisoformat(date).replace(hour=hour,tzinfo=timezone.utc))['is_open'],opened)
  with self.assertRaises(ValueError):us_calendar.session(datetime(2029,1,2,tzinfo=timezone.utc))
  self.assertEqual(us_calendar.session(datetime(2026,10,12,15,tzinfo=timezone.utc))['previous'],'20261009')
