"""Global mode routing. Every external submission is mocked, including prod."""
import unittest
from unittest.mock import patch
import test_us_paper as fixtures
Response = fixtures.Response
from core import us_stock
# Reuse fixture setup, not the inherited test suite.
class ModeTests(unittest.TestCase):
 setUp=fixtures.PaperTests.setUp
 tearDown=fixtures.PaperTests.tearDown
 def test_global_mode_buy_and_sell_ids(self):
  for mode,paper in [('vps',True),('prod',False)]:
   for action,tr in [('BUY','VTTT1002U' if paper else 'TTTT1002U'),('SELL','VTTT1001U' if paper else 'TTTT1006U')]:
    with patch('backend.routers.us_paper.get_current_mode',return_value=mode),patch('core.us_stock.ka.isPaperTrading',return_value=paper),patch('core.us_stock.ka._url_fetch',return_value=Response(output={'ODNO':'42'})) as external:
     result=self.client.post('/api/us-stock/order',json=self.request|dict(action=action,request_id='mode-test-'+mode+'-'+action)).json()
     self.assertEqual(result['status'],'accepted');self.assertEqual(result['mode'],mode)
     self.assertEqual(external.call_args.args[1],tr)
     self.assertEqual(external.call_args.args[3]['OVRS_ORD_UNPR'],'185.25')
 def test_actual_mode_mismatch_is_blocked(self):
  with patch('backend.routers.us_paper.get_current_mode',return_value='prod'),patch('core.us_stock.ka.isPaperTrading',return_value=True),patch('core.us_stock.ka._url_fetch') as external:
   self.assertEqual(self.client.post('/api/us-stock/order',json=self.request).status_code,403)
   external.assert_not_called()
 def test_prod_read_and_cancel_ids(self):
  with patch('backend.routers.us_paper.get_current_mode',return_value='prod'),patch('backend.routers.us_stock.get_current_mode',return_value='prod'),patch('core.us_stock.ka.isPaperTrading',return_value=False):
   with patch('core.us_stock.ka._url_fetch',return_value=Response(output1=[])) as external:
    self.assertEqual(self.client.get('/api/us-stock/holdings').status_code,200)
    self.assertEqual(external.call_args.args[1],'TTTS3012R')
   with patch('core.us_stock.ka._url_fetch',return_value=Response(output=[])) as external:
    self.assertEqual(self.client.get('/api/us-stock/pending').status_code,200)
    self.assertEqual(external.call_args.args[1],'TTTS3035R')
   with patch('core.us_stock.ka._url_fetch',return_value=Response(output={'ODNO':'43'})) as external:
    result=self.client.post('/api/us-stock/cancel',json=dict(request_id='prod-cancel-test-001',instrument_id='NYSE:BRK/B',quantity=2,order_no='42'))
    self.assertEqual(result.json()['status'],'accepted');self.assertEqual(external.call_args.args[1],'TTTT1004U')
 def test_context_lock_holds_during_submission(self):
  import threading
  entered,release,changed=threading.Event(),threading.Event(),threading.Event()
  def submit(*args,**kwargs):entered.set();release.wait(5);return Response(output={'ODNO':'42'})
  def change():
   with us_stock.ka.trading_context_lock:changed.set()
  with patch('core.us_stock.ka._url_fetch',side_effect=submit):
   order=threading.Thread(target=us_stock.submit,args=('NASDAQ:AAPL','BUY',1,'10.25','vps'));order.start();self.assertTrue(entered.wait(5))
   switch=threading.Thread(target=change);switch.start();self.assertFalse(changed.wait(.05));release.set();order.join(5);switch.join(5);self.assertTrue(changed.is_set())
 def test_mode_sets_actual_provider_rate_limit(self):
  ka=us_stock.ka
  cfg=dict(my_prod='01',my_app='fake-live',my_sec='fake-live-secret',paper_app='fake-paper',paper_sec='fake-paper-secret',my_acct_stock='11111111',my_paper_stock='22222222',my_htsid='fake',prod='https://live.invalid',vps='https://paper.invalid',ops='ws://live.invalid',vops='ws://paper.invalid')
  with patch.object(ka,'_cfg',cfg),patch.object(ka,'_setTRENV'),patch.object(ka,'_isPaper',False),patch.object(ka,'_smartSleep',.1):
   ka.changeTREnv('fake-token','vps','01');self.assertEqual(ka._smartSleep,.5)
   ka.changeTREnv('fake-token','prod','01');self.assertEqual(ka._smartSleep,.05)
 def test_unstructured_http_failure_is_unknown_not_rejected(self):
  response=us_stock.ka.APIRespError(500,'upstream unavailable')
  with patch('core.us_stock.ka._url_fetch',return_value=response) as external:
   for _ in range(2):self.assertEqual(self.client.post('/api/us-stock/order',json=self.request).json()['status'],'unknown')
   self.assertEqual(external.call_count,1)
 def test_structured_rate_rejection_is_explicit(self):
  response=us_stock.ka.APIRespError(500,'{"rt_cd":"1","msg_cd":"EGW00201","msg1":"rate limit"}')
  with patch('core.us_stock.ka._url_fetch',return_value=response):result=self.client.post('/api/us-stock/order',json=self.request).json()
  self.assertEqual(result['status'],'rejected');self.assertIn('EGW00201',result['message'])
