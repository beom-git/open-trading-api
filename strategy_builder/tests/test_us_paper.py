import os,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from core import us_paper
class Response:
    def __init__(self,**body):self.body=SimpleNamespace(**body)
    def isOK(self):return True
    def getBody(self):return self.body
    def getHeader(self):return SimpleNamespace(tr_cont='')
class PaperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.dict(os.environ,{'KIS_ORDER_JOURNAL':self.temp.name+'/orders.db'}),patch('backend.routers.us_paper.is_authenticated',return_value=True),patch('backend.routers.us_paper.get_current_mode',return_value='vps'),patch('core.us_paper.ka.isPaperTrading',return_value=True),patch('core.us_paper.ka.getTREnv',return_value=SimpleNamespace(my_acct='00000000',my_prod='01'))]
        for p in self.patches:p.start()
        self.client=TestClient(app)
        self.request=dict(request_id='test-order-id-0001',instrument_id='NYSE:BRK/B',action='BUY',quantity=2,price='185.25',currency='USD')
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_buy_sell_mapping_decimal_class(self):
        for action,tr in [('BUY','VTTT1002U'),('SELL','VTTT1001U')]:
            with patch('core.us_paper.ka._url_fetch',return_value=Response(output={'ODNO':'123'})) as fetch:
                result=self.client.post('/api/us-paper/order',json=self.request|dict(action=action,request_id='test-order-id-'+action))
            self.assertEqual(result.json()['status'],'accepted')
            self.assertEqual(fetch.call_args.args[1],tr)
            params=fetch.call_args.args[3]
            self.assertEqual((params['OVRS_EXCG_CD'],params['PDNO'],params['OVRS_ORD_UNPR'],params['ORD_DVSN']),('NYSE','BRK/B','185.25','00'))
            self.assertEqual(fetch.call_args.kwargs['timeout'],30)
    def test_exchanges(self):
        for id,ex in [('NASDAQ:AAPL','NASD'),('AMEX:SPY','AMEX')]:
            with patch('core.us_paper.ka._url_fetch',return_value=Response(output={'ODNO':'123'})) as fetch:
                us_paper.submit(id,'BUY',1,'10.01')
                self.assertEqual(fetch.call_args.args[3]['OVRS_EXCG_CD'],ex)
    def test_invalid_input_no_external_order(self):
        for changes in [dict(quantity=0),dict(quantity=1.5),dict(quantity=True),dict(price='NaN'),dict(price='10.001'),dict(currency='KRW'),dict(action='HOLD'),dict(instrument_id='KOSPI:005930')]:
            with patch('core.us_paper.ka._url_fetch') as fetch:
                self.assertEqual(self.client.post('/api/us-paper/order',json=self.request|changes).status_code,422)
                fetch.assert_not_called()
        self.assertEqual(us_paper.validate_price('.1234'),'0.1234')
    def test_live_guard_and_actual_mode_mismatch(self):
        for target in ['backend.routers.us_paper.get_current_mode','core.us_paper.ka.isPaperTrading']:
            with patch(target,return_value='prod' if 'get_current_mode' in target else False),patch('core.us_paper.ka._url_fetch') as fetch:
                self.assertEqual(self.client.post('/api/us-paper/order',json=self.request).status_code,403)
                for path in ['holdings','pending']:self.assertEqual(self.client.get('/api/us-paper/'+path).status_code,403)
                fetch.assert_not_called()
    def test_durable_duplicate_and_conflict(self):
        with patch('core.us_paper.ka._url_fetch',return_value=Response(output={'ODNO':'42'})) as fetch:
            first=self.client.post('/api/us-paper/order',json=self.request).json()
            second=TestClient(app).post('/api/us-paper/order',json=self.request).json()
            self.assertEqual(first,second)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(self.client.post('/api/us-paper/order',json=self.request|dict(price='186.25')).status_code,409)
    def test_timeout_unknown_no_resend(self):
        import requests
        with patch('core.us_paper.ka._url_fetch',side_effect=requests.Timeout()) as fetch:
            for _ in range(2):self.assertEqual(self.client.post('/api/us-paper/order',json=self.request).json()['status'],'unknown')
            self.assertEqual(fetch.call_count,1)
    def test_rejected(self):
        response=Response(msg1='paper rejected');response.isOK=lambda:False
        with patch('core.us_paper.ka._url_fetch',return_value=response):result=self.client.post('/api/us-paper/order',json=self.request).json()
        self.assertEqual(result['status'],'rejected')
        self.assertIn('paper rejected',result['message'])
    def test_holdings_adapter(self):
        row=dict(ovrs_excg_cd='NYSE',ovrs_pdno='BRK/B',ovrs_cblc_qty='2',pchs_avg_pric='185.25',now_pric2='186.01',ovrs_stck_evlu_amt='372.02',frcr_evlu_pfls_amt='1.52',evlu_pfls_rt='0.41')
        with patch('core.us_paper.ka._url_fetch',return_value=Response(output1=[row])):result=self.client.get('/api/us-paper/holdings').json()
        self.assertEqual(result['data'][0]['instrument_id'],'NYSE:BRK/B')
        self.assertEqual(result['data'][0]['current_price'],186.01)
        self.assertEqual(result['data'][0]['currency'],'USD')
        self.assertIn('fetched_at',result)
    def test_pending_and_cancel(self):
        row=dict(ovrs_excg_cd='NASD',pdno='AAPL',odno='42',nccs_qty='2',ft_ord_qty='3',ft_ord_unpr3='185.25',sll_buy_dvsn_cd='02')
        with patch('core.us_paper.ka._url_fetch',return_value=Response(output=[row])) as fetch:
            result=self.client.get('/api/us-paper/pending').json()
            self.assertEqual(fetch.call_args.args[1],'VTTS3035R')
            self.assertEqual(fetch.call_args.args[3]['CCLD_NCCS_DVSN'],'00')
        self.assertEqual(result['data'][0]['remaining'],2)
        with patch('core.us_paper.ka._url_fetch',return_value=Response(output={'ODNO':'43'})) as fetch:
            result=self.client.post('/api/us-paper/cancel',json=dict(request_id='test-cancel-id-0001',instrument_id='NASDAQ:AAPL',quantity=2,order_no='42'))
            self.assertEqual(result.json()['status'],'accepted')
            self.assertEqual(fetch.call_args.args[1],'VTTT1004U')
            self.assertEqual(fetch.call_args.args[3]['RVSE_CNCL_DVSN_CD'],'02')
    def test_missing_data_and_buyable(self):
        with patch('core.us_paper.ka._url_fetch',return_value=Response()):self.assertEqual(self.client.get('/api/us-paper/holdings').status_code,502)
        with patch('core.us_paper.ka._url_fetch',return_value=Response(output={'ovrs_ord_psbl_amt':'123.45','max_ord_psbl_qty':'3'})):
            result=self.client.get('/api/us-paper/buyable?instrument_id=NASDAQ:AAPL&price=10.25').json()
            self.assertEqual(result['data']['amount'],123.45)
    def test_concurrent_same_request_only_one_submission(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        entered,finish=threading.Event(),threading.Event()
        def fetch(*args,**kwargs):
            entered.set();finish.wait(5);return Response(output={'ODNO':'42'})
        with patch('core.us_paper.ka._url_fetch',side_effect=fetch) as external,ThreadPoolExecutor(2) as pool:
            first=pool.submit(self.client.post,'/api/us-paper/order',json=self.request)
            self.assertTrue(entered.wait(5))
            second=pool.submit(TestClient(app).post,'/api/us-paper/order',json=self.request)
            self.assertEqual(second.result(timeout=5).json()['status'],'unknown')
            finish.set()
            self.assertEqual(first.result(timeout=5).json()['status'],'accepted')
            self.assertEqual(external.call_count,1)
    def test_page_cursor_continuation_and_failure(self):
        first=Response(output=[],ctx_area_fk200='a',ctx_area_nk200='b')
        first.getHeader=lambda:SimpleNamespace(tr_cont='M')
        second=Response(output=[])
        with patch('core.us_paper.ka._url_fetch',side_effect=[first,second]) as fetch:
            self.assertEqual(us_paper.pending(),[])
            self.assertEqual(fetch.call_args.args[2],'N')
            self.assertEqual(fetch.call_args.args[3]['CTX_AREA_NK200'],'b')
        with patch('core.us_paper.ka._url_fetch',return_value=first),self.assertRaises(ValueError):us_paper.pending()
