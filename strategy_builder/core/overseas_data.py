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
