"""Read-only endpoints; this module has no order path."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend import is_authenticated,get_current_mode
from core import watchlist
from strategy_core import StrategyRegistry
router=APIRouter()
class SignalRequest(BaseModel):
    instrument_id:str
    strategy_id:str
    builder_state:dict|None=None

def read(call):
    if not is_authenticated():raise HTTPException(401,'인증이 필요합니다')
    try:return call()
    except Exception as e:raise HTTPException(502,str(e)) from e
@router.get('/quote/{instrument_id:path}')
def quote(instrument_id:str):return read(lambda:watchlist.quote(instrument_id,get_current_mode()))
@router.post('/signal')
def signal(request:SignalRequest):
    def run():
        state=request.builder_state or (StrategyRegistry.get(request.strategy_id) or {}).get('builder_state')
        if not state:raise ValueError('지원되는 시각적 전략을 선택하세요')
        return watchlist.signal(request.instrument_id,get_current_mode(),state,request.strategy_id)
    return read(run)
