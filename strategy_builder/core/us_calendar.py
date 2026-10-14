"""NYSE published 2026–2028 equity calendar; fail closed outside this range.
Source: https://www.nyse.com/trade/hours-calendars (verified 2026-10-14).
"""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York')
HOLIDAYS = set('20260101 20260119 20260216 20260403 20260525 20260619 20260703 20260907 20261126 20261225 20270101 20270118 20270215 20270326 20270531 20270618 20270705 20270906 20271125 20271224 20280117 20280221 20280414 20280529 20280619 20280704 20280904 20281123 20281225'.split())
EARLY = set('20261127 20261224 20271126 20280703 20281124'.split())

def trading_day(day):
    if day.year not in (2026, 2027, 2028):
        raise ValueError('공식 거래소 일정 지원 범위 밖 (2026–2028)')
    return day.weekday() < 5 and day.strftime('%Y%m%d') not in HOLIDAYS

def session(now):
    local = now.astimezone(NY)
    day = local.date()
    opened = trading_day(day)
    previous = day - timedelta(days=1)
    while not trading_day(previous):
        previous -= timedelta(days=1)
    close = time(13) if day.strftime('%Y%m%d') in EARLY else time(16)
    return dict(is_open=opened and time(9,30) <= local.time().replace(tzinfo=None) < close,
                previous=previous.strftime('%Y%m%d'), close=datetime.combine(day,close,NY).isoformat())
