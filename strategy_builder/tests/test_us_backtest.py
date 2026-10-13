import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backtester'))
from portable.daily import simulate
from strategy_core.evidence import EvidenceEvaluator
from strategy_core.dsl.parser import parse_strategy
class DailyTests(unittest.TestCase):
    def test_next_open_decimal_fees_and_cash(self):
        bars = [dict(date=str(i), open=p, close=p) for i,p in enumerate([10.01,10.25,12.5,12.75])]
        result = simulate(bars, lambda i: {'action':['BUY','HOLD','SELL','HOLD'][i]},100,0.01,0)
        self.assertEqual(result['fills'][0]['signal_date'], '0')
        self.assertEqual(result['fills'][0]['execution_date'], '1')
        self.assertEqual(result['fills'][0]['quantity'], 9)
        self.assertAlmostEqual(result['fills'][0]['cost'], .9225)
        self.assertAlmostEqual(result['trades'][0]['profit_loss'],20.43)
        self.assertAlmostEqual(result['final_equity'],120.43)
        self.assertEqual(result['points'][-1]['quantity'],0)
    def test_no_trades_and_empty(self):
        bars=[dict(date=str(i),open=10,close=10) for i in range(3)]
        result=simulate(bars,lambda i:dict(action='HOLD'))
        self.assertIsNone(result['win_rate'])
        self.assertEqual(result['total_trades'],0)
        with self.assertRaises(ValueError): simulate([],lambda i:None)
    def test_prefix_future_and_structured_evidence(self):
        evaluator=EvidenceEvaluator(parse_strategy('test','test','close > ma(2)','close < ma(2)'))
        frame=pd.DataFrame([dict(close=float(i),open=float(i),high=float(i),low=float(i),volume=100) for i in range(1,70)])
        before=evaluator.evaluate(frame.iloc[:40])
        frame.loc[40:,'close']=99999
        self.assertEqual(before,evaluator.evaluate(frame.iloc[:40]))
        self.assertEqual(before['buy']['left'],40)
        self.assertEqual(before['buy']['right'],39.5)
        self.assertTrue(before['buy']['satisfied'])
    def test_crossover_evidence(self):
        evaluator=EvidenceEvaluator(parse_strategy('test','test','ma(2) crosses_above ma(3)','close < 0'))
        df=pd.DataFrame({'close':[10.0]*40+[8.,7.,8.,15.]})
        result=evaluator.evaluate(df)
        self.assertEqual(result['action'],'BUY')
        self.assertLess(result['buy']['previous']['left'],result['buy']['previous']['right'])
        self.assertGreater(result['buy']['left'],result['buy']['right'])

class HistoryTests(unittest.TestCase):
    def setUp(self):
        from core.instruments import parse_instrument
        self.instrument = parse_instrument('NYSE:BRK/B')
    @staticmethod
    def body(dates):
        from types import SimpleNamespace
        return SimpleNamespace(output2=[dict(xymd=d,open='10.25',high='11.5',low='9.5',clos='10.75',tvol='100') for d in dates])
    def test_range_pagination_boundaries_and_decimal(self):
        from unittest.mock import patch
        from core.overseas_data import get_history_range
        with patch('core.overseas_data._fetch',side_effect=[self.body(['20250103','20250102']),self.body(['20250102','20250101','20241230']),self.body([])]) as fetch:
            frame,metadata=get_history_range(self.instrument,'20250101','20250103',2)
        self.assertEqual(frame.date.tolist(),['20241230','20250101','20250102','20250103'])
        self.assertEqual(frame.close.iloc[-1],10.75)
        self.assertEqual(fetch.call_args_list[1].args[3]['BYMD'],'20250101')
        self.assertEqual(metadata['completeness'],'unverified')
        self.assertTrue(metadata['pagination_finished'])
    def test_empty_short_and_nonprogressing(self):
        from unittest.mock import patch
        from core.overseas_data import get_history_range
        for pages in [[self.body([])],[self.body(['20250103']),self.body([])], [self.body(['20250103','20250102']),self.body(['20250103'])]]:
            with patch('core.overseas_data._fetch',side_effect=pages),self.assertRaises(ValueError):
                get_history_range(self.instrument,'20250101','20250103')
    def test_insufficient_does_not_claim_hold(self):
        evaluator=EvidenceEvaluator(parse_strategy('test','test','close > ma(20)','close < 1'))
        self.assertEqual(evaluator.evaluate(pd.DataFrame({'close':[10.]}))['action'],'INSUFFICIENT_DATA')
    def test_slippage_reduces_return(self):
        bars=[dict(date=str(i),open=p,close=p) for i,p in enumerate([10,10,20,20])]
        decide=lambda i:dict(action=['BUY','SELL','HOLD','HOLD'][i])
        self.assertLess(simulate(bars,decide,100,0,.01)['final_equity'],simulate(bars,decide,100,0,0)['final_equity'])

class EndpointTests(unittest.TestCase):
    def test_auth_and_domestic_guard(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.main import app
        client=TestClient(app)
        request=dict(instrument_id='NASDAQ:AAPL',start='2025-01-01',end='2025-01-05',strategy_id='sma')
        with patch('backend.routers.backtest.is_authenticated',return_value=False):
            self.assertEqual(client.post('/api/backtest',json=request).status_code,401)
        with patch('backend.routers.backtest.is_authenticated',return_value=True):
            request['instrument_id']='KOSPI:005930'
            self.assertEqual(client.post('/api/backtest',json=request).status_code,422)
