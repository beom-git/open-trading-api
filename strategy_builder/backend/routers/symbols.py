"""종목 검색 API 라우터

종목코드/종목명으로 검색하는 API 엔드포인트
마스터파일 수집 기능 포함 (공통 JSON 저장, 인메모리 캐시)
"""

import logging
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.instruments import EXCHANGE_NAMES, US_EXCHANGES
from core.symbol_master import SymbolRecord, make_symbol, load_master, save_master, parse_kis_domestic, parse_kis_us

logger = logging.getLogger(__name__)
router = APIRouter(tags=["symbols"])

# 마스터파일 디렉토리
MASTER_DIR = Path(".master")

# 국내 및 미국 거래소 마스터파일
MASTER_URLS = {
    "kospi": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
    "kosdaq": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
    "nasdaq": "https://new.real.download.dws.co.kr/common/master/nasmst.cod.zip",
    "nyse": "https://new.real.download.dws.co.kr/common/master/nysmst.cod.zip",
    "amex": "https://new.real.download.dws.co.kr/common/master/amsmst.cod.zip",
}

# 인메모리 캐시
_symbol_cache: dict[str, list[dict]] = {}
_last_loaded: dict[str, datetime] = {}


# ============================================
# 응답 스키마
# ============================================


SymbolSearchItem = SymbolRecord


class SymbolSearchResponse(BaseModel):
    """종목 검색 응답"""

    status: str = "success"
    query: str = Field(..., description="검색어")
    total: int = Field(..., description="검색 결과 수")
    items: list[SymbolSearchItem] = Field(default_factory=list, description="검색 결과 목록")


class SymbolDetailResponse(BaseModel):
    """종목 상세 정보 응답"""

    status: str = "success"
    data: Optional[SymbolSearchItem] = None
    message: Optional[str] = None


class MasterStatus(BaseModel):
    """마스터파일 상태"""
    kospi_count: int = 0
    kosdaq_count: int = 0
    nasdaq_count: int = 0
    nyse_count: int = 0
    amex_count: int = 0
    total_count: int = 0
    kospi_updated: Optional[str] = None
    kosdaq_updated: Optional[str] = None
    exchanges: list[dict] = Field(default_factory=list)
    updated_by_exchange: dict[str, Optional[str]] = Field(default_factory=dict)
    needs_update: bool = True


class CollectResult(BaseModel):
    """마스터파일 수집 결과"""
    success: bool
    kospi_count: int = 0
    kosdaq_count: int = 0
    nasdaq_count: int = 0
    nyse_count: int = 0
    amex_count: int = 0
    total_count: int = 0
    errors: list[str] = []


# ============================================
# 파일 시스템 유틸리티
# ============================================


def _get_master_path(exchange: str) -> Path:
    path = MASTER_DIR / f"{exchange}.json"
    return path if path.exists() else MASTER_DIR / f"{exchange}.csv"


def _get_file_mtime(path: Path) -> Optional[datetime]:
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime)
    return None


def _load_master(exchange: str) -> list[dict]:
    try:
        return load_master(MASTER_DIR, exchange)
    except (ValueError, OSError) as error:
        logger.error("마스터 로드 오류 (%s): %s", exchange, error)
        return []


def _get_all_symbols() -> list[dict]:
    """모든 종목 로드 (캐시 사용)
    
    strategy.py에서 종목명 조회에 사용됩니다.
    """
    global _symbol_cache, _last_loaded

    all_symbols = []

    for exchange in MASTER_URLS:
        # 캐시 확인
        if exchange in _symbol_cache:
            all_symbols.extend(_symbol_cache[exchange])
        else:
            # 공통 JSON 또는 이전 CSV에서 로드
            symbols = _load_master(exchange)
            if symbols:
                _symbol_cache[exchange] = symbols
                _last_loaded[exchange] = datetime.now()
                all_symbols.extend(symbols)

    return all_symbols


# ============================================
# 주요 종목 데이터 (폴백용)
# ============================================

FALLBACK_STOCKS: list[dict] = [
    make_symbol("071050", "kospi", "한국금융지주"),
]


# ============================================
# 검색 로직
# ============================================


def search_symbols(query: str, limit: int = 20, exchange: Optional[str] = None) -> list[dict]:
    """종목 검색 (코드 또는 이름)

    Args:
        query: 검색어 (종목코드 또는 종목명)
        limit: 최대 결과 수
        exchange: 거래소 필터 (kospi, kosdaq, nasdaq, nyse, amex)

    Returns:
        검색 결과 목록
    """
    query = query.lower().strip()
    results: list[dict] = []

    # 캐시된 종목 또는 폴백 사용
    all_symbols = _get_all_symbols() or FALLBACK_STOCKS

    for stock in all_symbols:
        # 거래소 필터
        if exchange and stock["exchange"] != exchange.lower():
            continue

        # 코드 또는 이름 매칭
        if any(query in stock.get(field, "").lower() for field in ("id", "ticker", "name", "english_name")):
            results.append(stock)
    results.sort(key=lambda row: (row["ticker"].lower() != query, row["name"].lower() != query, row["id"]))
    return results[:limit]


def get_symbol_by_code(code: str) -> Optional[dict]:
    """종목코드로 종목 정보 조회

    Args:
        code: 종목코드

    Returns:
        종목 정보 또는 None
    """
    all_symbols = _get_all_symbols() or FALLBACK_STOCKS
    for stock in all_symbols:
        if code.strip().upper() in (stock["id"], stock["code"]):
            return stock
    return None


# ============================================
# API 엔드포인트
# ============================================


# ============================================
# 마스터파일 상태/수집 API (/{code} 보다 먼저 정의해야 함)
# ============================================


@router.get("/status", response_model=MasterStatus)
async def get_master_status() -> MasterStatus:
    """마스터파일 상태 조회
    
    현재 로드된 종목 수, 마지막 업데이트 시간, 업데이트 필요 여부를 반환합니다.
    """
    counts = {ex: len(_symbol_cache.get(ex) or _load_master(ex)) for ex in MASTER_URLS}
    updated = {ex: _get_file_mtime(_get_master_path(ex)) for ex in MASTER_URLS}
    timestamps = {ex: value.isoformat() if value else None for ex, value in updated.items()}
    return MasterStatus(
        **{f"{ex}_count": count for ex, count in counts.items()},
        total_count=sum(counts.values()),
        kospi_updated=timestamps["kospi"], kosdaq_updated=timestamps["kosdaq"],
        updated_by_exchange=timestamps, needs_update=_check_needs_update(),
        exchanges=[{"exchange": ex, "name": EXCHANGE_NAMES[ex], "count": counts[ex],
                    "updated_at": timestamps[ex]} for ex in MASTER_URLS],
    )


@router.post("/collect", response_model=CollectResult)
async def collect_master_files() -> CollectResult:
    """Collect domestic and US masters, retaining prior data on individual failures."""
    errors = []
    counts = {}
    for exchange in MASTER_URLS:
        symbols, error = await _download_and_parse(exchange)
        if error:
            errors.append(f"{exchange}: {error}")
            symbols = _symbol_cache.get(exchange) or _load_master(exchange)
        counts[f"{exchange}_count"] = len(symbols)
    return CollectResult(success=not errors, **counts, total_count=sum(counts.values()), errors=errors)


# ============================================
# 검색 API
# ============================================


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols_api(
    q: str = Query(..., min_length=1, max_length=50, description="검색어 (종목코드 또는 종목명)"),
    limit: int = Query(default=20, ge=1, le=50, description="최대 결과 수"),
    exchange: Optional[str] = Query(default=None, description="거래소 필터 (kospi, kosdaq, nasdaq, nyse, amex)"),
) -> SymbolSearchResponse:
    """종목 검색

    종목코드 또는 종목명으로 검색합니다.

    Args:
        q: 검색어 (종목코드 또는 종목명)
        limit: 최대 결과 수 (1-50, 기본 20)
        exchange: 거래소 필터 (kospi, kosdaq, nasdaq, nyse, amex)

    Returns:
        검색 결과

    Examples:
        - GET /api/symbols/search?q=삼성
        - GET /api/symbols/search?q=005930
        - GET /api/symbols/search?q=에코&exchange=kosdaq
    """
    # 거래소 필터 검증
    if exchange and exchange.lower() not in MASTER_URLS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 거래소입니다: {exchange}. kospi, kosdaq, nasdaq, nyse, amex를 지원합니다.",
        )

    results = search_symbols(q, limit=limit, exchange=exchange)

    return SymbolSearchResponse(
        query=q,
        total=len(results),
        items=[SymbolSearchItem(**stock) for stock in results],
    )


@router.get("/{code:path}", response_model=SymbolDetailResponse)
async def get_symbol_detail(
    code: str,
) -> SymbolDetailResponse:
    """종목 상세 정보 조회

    종목코드로 상세 정보를 조회합니다.

    Args:
        code: 종목코드 (예: 005930)

    Returns:
        종목 상세 정보

    Examples:
        - GET /api/symbols/005930
    """
    stock = get_symbol_by_code(code)

    if stock is None:
        raise HTTPException(
            status_code=404,
            detail=f"종목을 찾을 수 없습니다: {code}",
        )

    return SymbolDetailResponse(
        data=SymbolSearchItem(**stock),
    )


# ============================================
# 마스터파일 수집 API
# ============================================


async def _download_and_parse(exchange: str, timeout: float = 60.0) -> tuple[list[dict], Optional[str]]:
    """마스터파일 다운로드 및 파싱"""
    global _symbol_cache, _last_loaded
    
    url = MASTER_URLS.get(exchange)
    if not url:
        return [], f"알 수 없는 거래소: {exchange}"
    
    try:
        logger.info(f"마스터파일 다운로드 시작: {exchange}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        content = response.content
        
        # ZIP 압축 해제
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                suffix = ".cod" if exchange in US_EXCHANGES else ".mst"
                member = next(name for name in zf.namelist() if name.lower().endswith(suffix))
                extracted = zf.read(member)
        except zipfile.BadZipFile:
            extracted = content
        
        # 파싱
        parser = parse_kis_us if exchange in US_EXCHANGES else parse_kis_domestic
        symbols = parser(extracted, exchange)
        if not symbols:
            return [], "유효한 종목이 없습니다. 기존 데이터를 유지합니다."
        
        if symbols:
            # 공통 JSON 저장
            save_master(MASTER_DIR, exchange, symbols)
            # 캐시 업데이트
            _symbol_cache[exchange] = symbols
            _last_loaded[exchange] = datetime.now()
            logger.info(f"마스터파일 수집 완료: {exchange} - {len(symbols)}개 종목")
        
        return symbols, None
        
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code}"
        logger.error(f"HTTP 오류 ({exchange}): {error}")
        return [], error
    except Exception as e:
        logger.error(f"수집 실패 ({exchange}): {e}")
        return [], str(e)


def _check_needs_update() -> bool:
    """오늘 업데이트가 필요한지 확인"""
    for exchange in MASTER_URLS:
        master_path = _get_master_path(exchange)
        if not master_path.exists() or not (_symbol_cache.get(exchange) or _load_master(exchange)):
            return True
        mtime = _get_file_mtime(master_path)
        if mtime and mtime.date() < date.today():
            return True
    return False
