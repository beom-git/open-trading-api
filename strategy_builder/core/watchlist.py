"""Read-only monitor snapshots, closed daily bars and mode-aware coalescing caches."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from threading import Lock
import hashlib,json,time,math
import pandas as pd
from core import data_fetcher
from core.instruments import parse_instrument
from strategy_core.dsl.converter import builder_state_to_dsl
from strategy_core.dsl.parser import parse_strategy
from strategy_core.evidence import EvidenceEvaluator

_lock=Lock()
_cache={}

def cached(key,ttl,load):
    # Serialize monitoring reads so simultaneous tabs cannot duplicate provider requests.
    with _lock:
        now=time.monotonic()
        item=_cache.get(key)
        if item and now-item[0]<ttl:return item[1]
        result=load()
        _cache[key]=(time.monotonic(),result)
        # Bound this per-process cache; expired snapshots are never re-labelled as fresh.
        if len(_cache)>400:
            oldest=min(_cache,key=lambda k:_cache[k][0]);del _cache[oldest]
        return result

def cutoff(code,now=None):
    value=parse_instrument(code)
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/New_York' if value.is_overseas else 'Asia/Seoul')).strftime('%Y%m%d')

def quote(code,mode):
    value=parse_instrument(code)
    def load():
        data=data_fetcher.get_current_price(value.id,mode)
        if not data or 'price' not in data:raise ValueError('현재가 데이터가 없습니다')
        if not math.isfinite(float(data['price'])) or float(data['price'])<=0 or not math.isfinite(float(data.get('change_rate',float('nan')))):
            raise ValueError('유효하지 않은 현재가 응답')
        return dict(instrument_id=value.id,currency=value.currency,data=data,
                    fetched_at=datetime.now(timezone.utc).isoformat(),provider_date=data.get('provider_date'),
                    provider_time=data.get('provider_time'),market_status='unknown')
    return cached(('quote',mode,value.id),25,load)

def signal(code,mode,state,strategy_id):
    value=parse_instrument(code)
    buy,sell=builder_state_to_dsl(state)
    if not buy:raise ValueError('매수 조건이 있는 시각적 전략이 필요합니다')
    definition=parse_strategy('monitor',state.get('metadata',{}).get('name',strategy_id),buy,sell)
    evaluator=EvidenceEvaluator(definition)
    definition_hash=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    today=cutoff(value.id)
    def load():
        frame=data_fetcher.get_daily_prices(value.id,min(1000,definition.get_required_days()+20))
        if frame.empty:raise ValueError('전략 일봉 데이터가 없습니다')
        frame=frame.copy()
        frame['date']=pd.to_datetime(frame['date'].astype(str),format='%Y%m%d',errors='raise').dt.strftime('%Y%m%d')
        for column in ['open','high','low','close','volume']:
            frame[column]=pd.to_numeric(frame[column],errors='raise')
            if not frame[column].map(math.isfinite).all():raise ValueError('일봉에 유효하지 않은 숫자가 있습니다')
        if (frame[['open','high','low','close']]<=0).any().any() or (frame['volume']<0).any():raise ValueError('일봉 가격/거래량 범위 오류')
        frame=frame.drop_duplicates('date').sort_values('date')
        frame=frame[frame.date<today].reset_index(drop=True)
        if frame.empty:raise ValueError('완성된 과거 일봉이 없습니다')
        result=evaluator.evaluate(frame)
        if result['action']=='INSUFFICIENT_DATA':raise ValueError('전략 계산에 필요한 완성 일봉이 부족합니다')
        basis=str(frame.date.iloc[-1])
        identity=f'{value.id}:{strategy_id}:{definition_hash}:{basis}'
        return result | dict(instrument_id=value.id,currency=value.currency,strategy_id=strategy_id,
                strategy_name=definition.name_ko,basis_date=basis,basis='closed_daily',signal_id=identity,
                signal_time=None,fetched_at=datetime.now(timezone.utc).isoformat(),
                limitation='오늘 진행 중인 봉을 제외합니다. 공급자 일봉 실제 발생 시각과 시장 달력이 없어 거래일 날짜만 표시합니다.')
    return cached(('signal',mode,value.id,definition_hash,strategy_id,today),60,load)
