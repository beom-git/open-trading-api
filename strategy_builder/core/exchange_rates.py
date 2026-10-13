"""KIS intraday USD/KRW quotes with a bounded, per-mode cache."""

import math
import threading
import time
from datetime import datetime, timezone

import kis_auth as ka


REFRESH_SECONDS = 30
_lock = threading.Lock()
_snapshots: dict[str, dict] = {}
_attempts: dict[str, float] = {}
_errors: dict[str, str] = {}


def _fetch_usd_krw() -> dict:
    # frgn_code.mst identifies X / FX@KRW as KRW per USD (KMB).
    response = ka._url_fetch(
        "/uapi/overseas-price/v1/quotations/inquire-time-indexchartprice",
        "FHKST03030200", "",
        {"FID_COND_MRKT_DIV_CODE": "X", "FID_INPUT_ISCD": "FX@KRW",
         "FID_HOUR_CLS_CODE": "0", "FID_PW_DATA_INCU_YN": "N"},
    )
    if not response.isOK():
        raise RuntimeError("환율 API 조회 실패")
    body = response.getBody()
    output = getattr(body, "output1", None)
    if not isinstance(output, dict):
        raise ValueError("환율 응답이 없습니다")
    rate = float(output.get("ovrs_nmix_prpr") or 0)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("유효한 원/달러 환율이 없습니다")

    # This is the provider's timestamp, not the time we received the HTTP response.
    # KIS does not specify a timezone here; do not invent one.
    quote_times = []
    for row in getattr(body, "output2", None) or []:
        raw = str(row.get("stck_bsop_date", "")) + str(row.get("stck_cntg_hour", ""))
        try:
            if len(raw) == 14 and raw.isascii() and raw.isdigit():
                quote_times.append(datetime.strptime(raw, "%Y%m%d%H%M%S"))
        except ValueError:
            continue
    return {
        "base": "USD", "quote": "KRW", "rate": rate,
        "source": "KIS", "symbol": "FX@KRW",
        "source_quote_time": max(quote_times).isoformat() if quote_times else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def get_usd_krw(mode: str) -> dict:
    """Coalesce concurrent polls; failed updates never re-date the last valid quote."""
    with _lock:
        if time.monotonic() - _attempts.get(mode, -math.inf) >= REFRESH_SECONDS:
            try:
                _snapshots[mode] = _fetch_usd_krw()
                _errors.pop(mode, None)
            except Exception:
                _errors[mode] = "환율을 갱신하지 못했습니다. KIS 연결과 해당 모드의 시세 이용 가능 여부를 확인해주세요."
            finally:
                _attempts[mode] = time.monotonic()
        error = _errors.get(mode)
        return {
            "status": "error" if error else "success",
            "data": _snapshots.get(mode), "stale": bool(error),
            "message": error, "refresh_interval_seconds": REFRESH_SECONDS,
        }
