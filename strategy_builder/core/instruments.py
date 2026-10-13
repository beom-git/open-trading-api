"""Stable instrument IDs shared by search, market data and strategy execution."""

import re
from dataclasses import dataclass


US_EXCHANGES = {"nasdaq": "NAS", "nyse": "NYS", "amex": "AMS"}
EXCHANGE_NAMES = {
    "kospi": "코스피", "kosdaq": "코스닥",
    "nasdaq": "나스닥", "nyse": "뉴욕", "amex": "아멕스",
}


@dataclass(frozen=True)
class Instrument:
    code: str
    ticker: str
    exchange: str
    currency: str

    @property
    def id(self) -> str:
        return f"{self.exchange.upper()}:{self.ticker}"

    @property
    def market(self) -> str:
        return "US" if self.is_overseas else "KR"

    @property
    def is_overseas(self) -> bool:
        return self.exchange in US_EXCHANGES


def parse_instrument(code: str) -> Instrument:
    """Parse exchange:ticker IDs; bare domestic codes remain compatibility inputs."""
    code = code.strip().upper()
    if re.fullmatch(r"[0-9][A-Z0-9]{5}", code):
        return Instrument(code, code, "krx", "KRW")
    exchange, separator, ticker = code.partition(":")
    if separator and exchange.lower() in ("krx", "kospi", "kosdaq") and re.fullmatch(r"[A-Z0-9]{6}", ticker):
        return Instrument(code, ticker, exchange.lower(), "KRW")
    if separator and exchange.lower() in US_EXCHANGES and re.fullmatch(r"[A-Z0-9][A-Z0-9./\-]{0,19}", ticker) and ".." not in ticker:
        return Instrument(code, ticker, exchange.lower(), "USD")
    raise ValueError("종목코드는 국내 6자리 코드 또는 NASDAQ:AAPL / NYSE:IBM / AMEX:SPY 형식이어야 합니다")


def require_domestic(code: str) -> Instrument:
    instrument = parse_instrument(code)
    if instrument.is_overseas:
        raise ValueError("미국 주식은 국내 전용 API로 처리할 수 없습니다. 해외 주문·잔고는 공통 미국 API를 사용하세요.")
    return instrument
