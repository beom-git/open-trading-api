"""Sanitized real 90070000 error; external broker calls are mocked."""
import os, tempfile, unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from backend.state import TradingState
from core import auto_verification as verify, us_stock
import kis_auth as ka
ERROR='90070000: 모의투자 처리계좌의 ID와 사용자정보가 상이하여 처리 불가능 합니다.'

class VerificationTests(unittest.TestCase):
 def setUp(self):
  self.patches=[];self.mocks={}
  replacements={
   'core.auto_verification.is_authenticated':True,'core.auto_verification.get_current_mode':'vps',
   'core.auto_verification.ka.isPaperTrading':True,
   'core.auto_verification.us_stock._account':{'CANO':'DO_NOT_EXPOSE','ACNT_PRDT_CD':'01'},
   'core.auto_verification.us_calendar.session':dict(is_open=True,previous='20261013'),
   'core.auto_verification.watchlist.signal':dict(action='HOLD',basis_date='20261013'),
   'core.auto_verification.overseas_data.latest_minute':dict(price='100',provider_at=datetime.now(timezone.utc).isoformat()),
   'core.auto_verification.us_stock.holdings':[],'core.auto_verification.us_stock.order_history':[],
   'core.auto_verification.us_stock.buyable':dict(amount=10000,quantity=100),
   'core.auto_verification.service':SimpleNamespace(snapshot=lambda:{'config':dict(buy_percent='10',sell_percent='100',buy_offset_percent='.1',sell_offset_percent='.1')})}
  for key,value in replacements.items():
   p=patch(key,return_value=value);self.mocks[key.split('.')[-1]]=p.start();self.patches.append(p)
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def test_independent_success_no_order_calls_no_account_identity(self):
  with patch.object(us_stock,'submit') as submit,patch.object(us_stock,'cancel') as cancel:
   result=verify.verify();self.assertTrue(result['ready']);self.assertTrue(result['order_ready'])
   self.assertNotIn('DO_NOT_EXPOSE',str(result));submit.assert_not_called();cancel.assert_not_called()
 def test_actual_account_failure_each_of_holdings_history_and_buyable(self):
  for name in ('holdings','order_history','buyable'):self.mocks[name].side_effect=us_stock.BrokerRejected(ERROR)
  result=verify.verify();self.assertFalse(result['ready']);self.assertFalse(result['order_ready']);self.assertIsNone(result['holdings_count']);self.assertIsNone(result['order_count'])
  for name in ('holdings','order_history','buyable'):
   self.assertEqual(result['checks'][name]['status'],'failed');self.assertIn('90070000',result['checks'][name]['message']);self.assertIn('my_paper_stock',result['checks'][name]['remedy'])
  self.assertEqual(result['checks']['daily_signal']['status'],'passed')
 def test_each_provider_failure_is_not_authentication_success(self):
  for name in ('holdings','order_history','buyable'):
   self.mocks[name].side_effect=RuntimeError('provider unavailable')
   result=verify.verify();self.assertFalse(result['ready']);self.assertEqual(result['checks'][name]['status'],'failed')
   self.mocks[name].side_effect=None
 def test_missing_quote_is_unverified_not_passed(self):
  self.mocks['latest_minute'].side_effect=ValueError('provider time missing')
  result=verify.verify();self.assertFalse(result['ready']);self.assertEqual(result['checks']['buyable']['status'],'skipped');self.mocks['buyable'].assert_not_called()
 def test_old_and_future_quotes_block_orders_while_reads_succeed(self):
  for delta in (-180,10):
   self.mocks['latest_minute'].return_value=dict(price='100',provider_at=(datetime.now(timezone.utc)+timedelta(seconds=delta)).isoformat())
   result=verify.verify();self.assertTrue(result['ready']);self.assertFalse(result['order_ready'])
 def test_closed_or_unsupported_calendar(self):
  self.mocks['session'].return_value=dict(is_open=False);self.assertFalse(verify.verify()['order_ready'])
  self.mocks['session'].side_effect=ValueError('unsupported');self.assertFalse(verify.verify()['ready'])
 def test_live_mode_and_missing_auth_never_read_broker(self):
  for name,value in [('get_current_mode','prod'),('is_authenticated',False)]:
   self.mocks[name].return_value=value;self.assertFalse(verify.verify()['ready']);self.mocks['holdings'].assert_not_called()
 def test_endpoint_never_submits_or_cancels(self):
  with patch.object(us_stock,'submit') as submit,patch.object(us_stock,'cancel') as cancel:
   self.assertEqual(TestClient(app).post('/api/auto-trading/verify').status_code,200);submit.assert_not_called();cancel.assert_not_called()

class PaperRestrictionTests(unittest.TestCase):
 def test_auth_context_prod_denied_before_network_or_mutation(self):
  with patch.dict(os.environ,{'KIS_PAPER_ONLY':'1'}),patch.object(ka.requests,'post') as post,patch.object(ka,'_setTRENV') as setenv:
   with self.assertRaisesRegex(ValueError,'모의투자 전용'):ka.auth('prod')
   with self.assertRaisesRegex(ValueError,'모의투자 전용'):ka.changeTREnv('fake','prod')
   post.assert_not_called();setenv.assert_not_called()
 def test_cached_live_token_not_restored(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KIS_PAPER_ONLY':'1'}),patch('os.path.expanduser',return_value=tmp),patch.object(ka,'read_token',return_value='fake'),patch.object(TradingState,'_detect_mode_from_token',return_value='prod'),patch.object(ka,'auth') as auth:
   state=TradingState();self.assertEqual(state.current_mode,'vps');self.assertFalse(state.is_authenticated);auth.assert_not_called()
 def test_mode_switch_preserves_current_auth_and_token(self):
  with patch.dict(os.environ,{'KIS_PAPER_ONLY':'1'}),patch.object(TradingState,'_try_restore_auth'):
   state=TradingState();state._authenticated=True
   with patch.object(state,'_clear_token_file') as clear,patch.object(ka,'auth') as auth:
    with self.assertRaises(ValueError):state.authenticate('prod')
    clear.assert_not_called();auth.assert_not_called();self.assertTrue(state._authenticated)
 def test_raw_live_request_is_blocked(self):
  with patch.dict(os.environ,{'KIS_PAPER_ONLY':'1'}),patch.object(ka,'isPaperTrading',return_value=False),patch.object(ka.requests,'get') as get:
   with self.assertRaises(ValueError):ka._url_fetch('/fake','TTTS3012R','',{})
   get.assert_not_called()
 def test_status_and_prod_login(self):
  with patch.dict(os.environ,{'KIS_PAPER_ONLY':'1'}):
   client=TestClient(app);status=client.get('/api/auth/status').json()
   self.assertTrue(status['paper_only']);self.assertFalse(status['can_switch_mode']);self.assertEqual(client.post('/api/auth/login',json={'mode':'prod'}).status_code,400)

class RealBrokerErrorTests(unittest.TestCase):
 def test_90070000_never_becomes_empty_balance_or_pending_success(self):
  response=SimpleNamespace(isOK=lambda:False,getBody=lambda:SimpleNamespace(msg_cd='90070000',msg1=ERROR.split(': ',1)[1]),getErrorCode=lambda:'90070000')
  with patch.object(ka,'isPaperTrading',return_value=True),patch.object(ka,'getTREnv',return_value=SimpleNamespace(my_acct='00000000',my_prod='01')),patch.object(ka,'_url_fetch',return_value=response):
   for read in (us_stock.holdings,us_stock.pending,lambda:us_stock.buyable('NASDAQ:AAPL','100.10')):
    with self.assertRaisesRegex(us_stock.BrokerRejected,'90070000'):read()

class RateLimitReadTests(unittest.TestCase):
 def response(self,code):
  return SimpleNamespace(isOK=lambda:code=='0',getBody=lambda:SimpleNamespace(msg_cd=code,msg1='sanitized provider response'),getErrorCode=lambda:code)
 def test_observed_read_rate_rejection_recovers_with_backoff(self):
  from core.provider_retry import retry_read
  from unittest.mock import Mock
  call=Mock(side_effect=[self.response('EGW00201'),self.response('0')])
  with patch('core.provider_retry.time.sleep') as sleep:
   self.assertTrue(retry_read(call).isOK());sleep.assert_called_once_with(1);self.assertEqual(call.call_count,2)
 def test_rate_retry_exhaustion_and_account_error_not_retried(self):
  from core.provider_retry import retry_read
  from unittest.mock import Mock
  for code,count in [('EGW00201',3),('90070000',1)]:
   call=Mock(return_value=self.response(code))
   with patch('core.provider_retry.time.sleep'):
    self.assertFalse(retry_read(call).isOK());self.assertEqual(call.call_count,count)
 def test_orders_and_cancels_rate_denial_never_retried(self):
  with patch.object(ka,'isPaperTrading',return_value=True),patch.object(ka,'getTREnv',return_value=SimpleNamespace(my_acct='00000000',my_prod='01')),patch.object(ka,'_url_fetch',return_value=self.response('EGW00201')) as fetch:
   for operation in (lambda:us_stock.submit('NASDAQ:AAPL','BUY',1,'100.10'),lambda:us_stock.cancel('NASDAQ:AAPL','42',1)):
    fetch.reset_mock()
    with self.assertRaises(us_stock.BrokerRejected):operation()
    self.assertEqual(fetch.call_count,1)
