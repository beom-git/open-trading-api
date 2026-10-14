import unittest
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import patch
from scripts.verify_auto_trading import run

class ProbeTests(unittest.TestCase):
 def client(self, ready=True, error=None, filled=False):
  self.calls=[]
  def request(method,url,json=None,timeout=None):
   self.calls.append((method,url,json))
   path=url.split('http://localhost')[1]
   if path=='/api/auth/status':data=dict(mode='vps',paper_only=True)
   elif path=='/api/auth/login':data=dict(authenticated=True,mode='vps')
   elif path=='/api/auto-trading/verify':data=dict(ready=ready,order_ready=ready,quote=dict(price='100',provider_at=datetime.now(timezone.utc).isoformat()))
   elif path=='/api/auto-trading':data=dict(running=False)
   elif path=='/api/us-paper/pending':data=dict(data=[])
   elif path.startswith('/api/us-paper/buyable'):data=dict(data=dict(amount=1000,quantity=10))
   elif path=='/api/us-paper/order':
    if error:raise TimeoutError('timeout')
    data=dict(status='accepted',order_no='42')
   elif path=='/api/us-paper/cancel':data=dict(status='accepted')
   elif path=='/api/us-stock/history':data=dict(data=[dict(order_no='42',instrument_id='NASDAQ:AAPL',filled=1 if filled else 0,remaining=0,cancelled=not filled)])
   else:raise AssertionError(path)
   return SimpleNamespace(raise_for_status=lambda:None,json=lambda:data)
  return SimpleNamespace(request=request)
 def test_default_never_posts_orders(self):
  result=run('http://localhost',http=self.client());self.assertEqual(result['paper_order']['status'],'not_run')
  self.assertFalse(any(path.endswith('/order') for _,path,_ in self.calls))
 def test_account_or_closed_market_never_posts_orders(self):
  result=run('http://localhost',True,self.client(ready=False));self.assertEqual(result['paper_order']['status'],'blocked')
  self.assertFalse(any(path.endswith('/order') for _,path,_ in self.calls))
 def test_probe_is_one_share_cancel_and_followup_confirmed(self):
  result=run('http://localhost',True,self.client());self.assertEqual(result['paper_order']['status'],'cancel_confirmed')
  orders=[body for _,url,body in self.calls if url.endswith('/order')]
  self.assertEqual(len(orders),1);self.assertEqual(orders[0]['quantity'],1);self.assertEqual(orders[0]['action'],'BUY')
  cancel=[body for _,url,body in self.calls if url.endswith('/cancel')][0];self.assertEqual(cancel['order_no'],'42')
 def test_timeout_reports_unique_id_and_never_retries(self):
  result=run('http://localhost',True,self.client(error=True));self.assertEqual(result['paper_order']['status'],'unknown')
  self.assertTrue(result['paper_order']['request_id'].startswith('paper-check-'))
  self.assertEqual(sum(url.endswith('/order') for _,url,_ in self.calls),1)
 def test_fill_does_not_sell_manual_holdings_or_claim_cancel_success(self):
  result=run('http://localhost',True,self.client(filled=True));self.assertEqual(result['paper_order']['status'],'filled')
  self.assertFalse(any(body and body.get('action')=='SELL' for _,_,body in self.calls))
 def test_nonrestricted_or_live_server_refused_before_login(self):
  for status in (dict(mode='prod',paper_only=True),dict(mode='vps',paper_only=False)):
   http=SimpleNamespace(request=lambda *a,**kw:SimpleNamespace(raise_for_status=lambda:None,json=lambda:status))
   with self.assertRaises(ValueError):run('http://localhost',True,http)
