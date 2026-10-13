"""Single US instrument backtests using the shared visual strategy DSL."""
import sys
from pathlib import Path
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend import is_authenticated
from core.instruments import parse_instrument
from core.overseas_data import get_history_range
from strategy_core import StrategyRegistry
from strategy_core.dsl.converter import builder_state_to_dsl
from strategy_core.dsl.parser import parse_strategy
from strategy_core.evidence import EvidenceEvaluator
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'backtester'))
from portable.daily import simulate
router = APIRouter()
class Request(BaseModel):
    instrument_id: str
    start: date
    end: date
    strategy_id: str
    builder_state: dict | None = None
    initial_cash: float = Field(default=10000, gt=0, allow_inf_nan=False)
    fee_rate: float = Field(default=0.001, ge=0, lt=1, allow_inf_nan=False)
    slippage: float = Field(default=0.001, ge=0, lt=1, allow_inf_nan=False)
@router.post('')
def run(request: Request):
    if not is_authenticated():
        raise HTTPException(401, 'KIS 인증이 필요합니다')
    try:
        instrument = parse_instrument(request.instrument_id)
        if not instrument.is_overseas:
            raise ValueError('미국 단일 종목 전용입니다. 국내 Lean 백테스터를 사용하세요.')
        if request.start >= request.end or request.end > date.today():
            raise ValueError('시작일은 종료일 이전이어야 하며 미래 기간은 지원하지 않습니다')
        schema = StrategyRegistry.get(request.strategy_id)
        state = request.builder_state or (schema or {}).get('builder_state')
        if not state:
            raise ValueError('시각적 전략 정의가 필요합니다. Python 전용 전략은 지원하지 않습니다')
        name = state.get('metadata', {}).get('name') or (schema or {}).get('name') or request.strategy_id
        buy, sell = builder_state_to_dsl(state)
        definition = parse_strategy(name='historical', name_ko=name, buy_condition=buy, sell_condition=sell)
        evaluator = EvidenceEvaluator(definition)
        start, end = request.start.strftime('%Y%m%d'), request.end.strftime('%Y%m%d')
        frame, metadata = get_history_range(instrument, start, end, definition.get_required_days())
        indices = frame.index[(frame.date >= start) & (frame.date <= end)].tolist()
        result = simulate(frame.loc[indices].to_dict('records'),lambda i: evaluator.evaluate(frame.iloc[:indices[i]+1]),
                          request.initial_cash, request.fee_rate, request.slippage)
        if all(d['action'] == 'INSUFFICIENT_DATA' for d in result['decisions']):
            raise ValueError('전략 지표 계산에 필요한 과거 봉이 부족합니다')
        return result | dict(instrument_id=instrument.code, currency='USD', strategy_name=name,
                             metadata=metadata, initial_cash=request.initial_cash)
    except (ValueError, RuntimeError, IndexError) as error:
        raise HTTPException(422, str(error)) from error
