"""US quote adapters. Failures propagate so strategies report ERROR, not a false HOLD."""

from datetime import datetime, timedelta
from decimal import Decimal
import math

import pandas as pd

import kis_auth as ka
from core.instruments import Instrument, US_EXCHANGES


def _fetch(path: str, tr_id: str, instrument: Instrument, extra: dict | None = None):
    params = {"AUTH": "", "EXCD": US_EXCHANGES[instrument.exchange], "SYMB": instrument.ticker}
    response = ka._url_fetch(path, tr_id, "", params | (extra or {}))
    if not response.isOK():
        raise RuntimeError(f"미국 주식 시세 조회 실패 ({instrument.code}): {response.getErrorCode()}")
    return response.getBody()


def get_daily_prices(instrument: Instrument, days: int) -> pd.DataFrame:
    if not 1 <= days <= 1000:
        raise ValueError("조회 기간은 1~1000 거래일이어야 합니다")
    rows = []
    before = ""
    columns = ["date", "open", "high", "low", "close", "volume"]
    for _ in range(20):
        body = _fetch(
            "/uapi/overseas-price/v1/quotations/dailyprice", "HHDFS76240000", instrument,
            {"GUBN": "0", "BYMD": before, "MODP": "1"},
        )
        page = getattr(body, "output2", None)
        if not page:
            break
        frame = pd.DataFrame(page).rename(columns={"xymd": "date", "clos": "close", "tvol": "volume"})
        if not set(columns).issubset(frame.columns):
            raise ValueError("미국 주식 일봉 응답에 필요한 필드가 없습니다")
        frame = frame[columns].copy()
        dates = pd.to_datetime(frame["date"], format="%Y%m%d", errors="raise")
        frame["date"] = dates.dt.strftime("%Y%m%d")
        # Some servers repeat the boundary row. Never count duplicates as history.
        if before:
            frame = frame[frame["date"] <= before]
        if frame.empty:
            break
        for column in columns[1:]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not frame[columns[1:]].map(lambda value: math.isfinite(value)).all().all():
            raise ValueError("미국 주식 일봉에 유효하지 않은 가격이 있습니다")
        rows.extend(frame.to_dict("records"))
        if len({row["date"] for row in rows}) >= days:
            break
        earliest = datetime.strptime(frame["date"].min(), "%Y%m%d")
        before = (earliest - timedelta(days=1)).strftime("%Y%m%d")
    if not rows:
        raise RuntimeError(f"미국 주식 일봉 데이터가 없습니다: {instrument.code}")
    return (pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
            .tail(days).reset_index(drop=True))


def get_current_price(instrument: Instrument) -> dict:
    body = _fetch("/uapi/overseas-price/v1/quotations/price-detail", "HHDFS76200200", instrument)
    output = getattr(body, "output", None)
    if not isinstance(output, dict) or not output.get("last") or not output.get("base"):
        raise RuntimeError(f"미국 주식 현재가 데이터가 없습니다: {instrument.code}")

    def number(field: str) -> float:
        value = float(output.get(field) or 0)
        if not math.isfinite(value):
            raise ValueError(f"미국 주식 현재가 응답 오류: {field}")
        return value

    price, base = number("last"), number("base")
    if price <= 0 or base <= 0:
        raise ValueError("미국 주식 현재가와 전일 종가는 양수여야 합니다")
    change = float(Decimal(str(price)) - Decimal(str(base)))
    return {
        "price": price, "change": change, "change_rate": change / base * 100,
        "high": number("high"), "low": number("low"), "volume": int(number("tvol")),
        "w52_high": number("h52p"), "w52_low": number("l52p"),
        "currency": instrument.currency, "exchange": instrument.exchange,
    }


def get_history_range(instrument: Instrument, start: str, end: str, warmup: int = 100):
    """Page backwards from an explicit end date. Never label calendar completeness as verified."""
    lower = datetime.strptime(start, '%Y%m%d') - timedelta(days=warmup * 3 + 14)
    before, rows, exhausted = end, [], False
    columns = ['date', 'open', 'high', 'low', 'close', 'volume']
    for _ in range(40):
        body = _fetch('/uapi/overseas-price/v1/quotations/dailyprice', 'HHDFS76240000', instrument,
                      {'GUBN': '0', 'BYMD': before, 'MODP': '1'})
        page = getattr(body, 'output2', None)
        if not page:
            exhausted = True
            break
        frame = pd.DataFrame(page).rename(columns={'xymd': 'date', 'clos': 'close', 'tvol': 'volume'})
        if not set(columns).issubset(frame.columns):
            raise ValueError('일봉 필드 누락')
        frame = frame[columns].copy()
        frame['date'] = pd.to_datetime(frame['date'], format='%Y%m%d', errors='raise').dt.strftime('%Y%m%d')
        frame = frame[frame['date'] <= before]
        if frame.empty:
            raise ValueError('일봉 페이지가 진행되지 않습니다')
        for c in columns[1:]:
            frame[c] = pd.to_numeric(frame[c], errors='raise')
        if not frame[columns[1:]].map(math.isfinite).all().all():
            raise ValueError('유효하지 않은 일봉 값')
        if (frame[['open','high','low','close']] <= 0).any().any() or (frame['volume'] < 0).any():
            raise ValueError('가격/거래량 범위 오류')
        if ((frame['high'] < frame[['open','close','low']].max(axis=1)) |
            (frame['low'] > frame[['open','close','high']].min(axis=1))).any():
            raise ValueError('OHLC 범위 오류')
        rows.extend(frame.to_dict('records'))
        earliest = datetime.strptime(frame['date'].min(), '%Y%m%d')
        if earliest <= lower:
            exhausted = True
            break
        before = (earliest - timedelta(days=1)).strftime('%Y%m%d')
    if not rows:
        raise ValueError('일봉 데이터가 없습니다')
    frame = pd.DataFrame(rows).drop_duplicates('date').sort_values('date').reset_index(drop=True)
    selected = frame[(frame.date >= start) & (frame.date <= end)]
    if len(selected) < 2:
        raise ValueError('요청 기간 데이터가 부족합니다')
    return frame, dict(source='KIS overseas dailyprice', adjusted=True, requested_start=start, requested_end=end,
                      actual_start=selected.date.min(), actual_end=selected.date.max(),
                      pagination_finished=exhausted, completeness='unverified',
                      warning='거래일 달력 및 공급자 결측 확인이 없어 전체 기간의 완전성을 보장하지 않습니다. 과거 환율 미제공: USD 성과만 표시합니다.')
