"""
캐싱 레이어.

- st.cache_data TTL 래퍼: 앱 실행 중 메모리 캐시
- parquet 디스크 캐시: 재실행 시 재사용 (data/.cache/ 디렉토리)

캐시 우선순위:
  1. st.cache_data (메모리, TTL 만료 전)
  2. parquet 파일 (디스크, MAX_AGE_HOURS 내)
  3. 실제 수집 후 저장
"""

import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from data.fetcher import (
    get_all_stocks_valuation,
    get_industry_map,
    get_ohlcv,
    get_stock_financials,
    get_stock_roe,
)
from data.macro_fetcher import (
    get_exchange_rate,
    get_exchange_rate_history,
    get_kospi_pbr_history,
    get_market_phase,
    get_us10y_yield,
)

_CACHE_DIR = Path(__file__).parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)

_ALL_STOCKS_TTL = 3600          # 전종목 스크리닝: 1시간
_STOCK_DETAIL_TTL = 86400       # 개별 종목 재무: 1일
_MACRO_TTL = 3600               # 매크로 지표: 1시간
_OHLCV_TTL = 3600               # OHLCV: 1시간
_HIST_PBR_TTL = 60 * 60 * 24 * 7  # KOSPI PBR 히스토리: 7일 (역사적 데이터)

MAX_AGE_HOURS = 24              # parquet 캐시 최대 보관 시간


# ──────────────────────────────────────────────
# parquet 디스크 캐시 헬퍼
# ──────────────────────────────────────────────

def _parquet_path(name: str) -> Path:
    return _CACHE_DIR / f"{name}.parquet"


def _is_fresh(path: Path, max_hours: float) -> bool:
    if not path.exists():
        return False
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.datetime.now() - mtime).total_seconds() < max_hours * 3600


def _load_parquet(name: str, max_hours: float = MAX_AGE_HOURS) -> pd.DataFrame | None:
    path = _parquet_path(name)
    if _is_fresh(path, max_hours):
        try:
            return pd.read_parquet(path)
        except Exception:
            pass
    return None


def _save_parquet(name: str, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_parquet_path(name), index=False)
    except Exception:
        pass  # 캐시 저장 실패 시 무시


# ──────────────────────────────────────────────
# 전종목 스크리닝 캐시
# ──────────────────────────────────────────────

@st.cache_data(ttl=_ALL_STOCKS_TTL, show_spinner="전종목 데이터 로딩 중...")
def cached_all_stocks(market: str = "ALL") -> pd.DataFrame:
    """전종목 PBR/PER/BPS/EPS/시가총액. parquet 선행 확인."""
    cache_name = f"all_stocks_{market}"
    disk = _load_parquet(cache_name, max_hours=1)
    if disk is not None:
        return disk
    df = get_all_stocks_valuation(market)
    _save_parquet(cache_name, df)
    return df


# ──────────────────────────────────────────────
# 업종 맵 캐시
# ──────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner="업종 데이터 로딩 중...")
def cached_industry_map() -> dict:
    """ticker → 네이버 업종명 매핑. 24시간 캐시."""
    cache_name = "industry_map"
    path = _parquet_path(cache_name)
    if _is_fresh(path, max_hours=24):
        try:
            df = pd.read_parquet(path)
            return dict(zip(df["ticker"], df["industry"]))
        except Exception:
            pass
    data = get_industry_map()
    if data:
        try:
            pd.DataFrame(
                list(data.items()), columns=["ticker", "industry"]
            ).to_parquet(path, index=False)
        except Exception:
            pass
    return data


# ──────────────────────────────────────────────
# 개별 종목 캐시
# ──────────────────────────────────────────────

@st.cache_data(ttl=_STOCK_DETAIL_TTL, show_spinner="ROE 데이터 로딩 중...")
def cached_stock_roe(ticker: str, years: int = 5) -> pd.DataFrame:
    ticker = str(ticker).zfill(6)
    cache_name = f"roe_{ticker}"
    disk = _load_parquet(cache_name)
    if disk is not None:
        return disk
    df = get_stock_roe(ticker, years)
    if not df.empty:
        _save_parquet(cache_name, df)
    return df


@st.cache_data(ttl=_STOCK_DETAIL_TTL, show_spinner="재무데이터 로딩 중...")
def cached_stock_financials(ticker: str) -> dict:
    ticker = str(ticker).zfill(6)
    # dict는 parquet 저장 불가 → DataFrame으로 변환 저장
    cache_name = f"financials_{ticker}"
    disk = _load_parquet(cache_name)
    if disk is not None:
        return disk.to_dict(orient="list")
    data = get_stock_financials(ticker)
    if data:
        try:
            df = pd.DataFrame(data)
            _save_parquet(cache_name, df)
        except Exception:
            pass
    return data


@st.cache_data(ttl=_OHLCV_TTL, show_spinner="주가 데이터 로딩 중...")
def cached_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    ticker = str(ticker).zfill(6)
    cache_name = f"ohlcv_{ticker}_{start}_{end}"
    disk = _load_parquet(cache_name, max_hours=1)
    if disk is not None:
        return disk
    df = get_ohlcv(ticker, start, end)
    if not df.empty:
        _save_parquet(cache_name, df)
    return df


# ──────────────────────────────────────────────
# 매크로 캐시
# ──────────────────────────────────────────────

@st.cache_data(ttl=_MACRO_TTL, show_spinner="매크로 데이터 로딩 중...")
def cached_us10y_yield(years: int = 3) -> pd.DataFrame:
    cache_name = f"us10y_{years}y"
    disk = _load_parquet(cache_name, max_hours=1)
    if disk is not None:
        return disk
    df = get_us10y_yield(years)
    if not df.empty:
        _save_parquet(cache_name, df)
    return df


@st.cache_data(ttl=_HIST_PBR_TTL, show_spinner="KOSPI PBR 히스토리 수집 중 (최초 1회, 약 15초)...")
def cached_kospi_pbr_history(years: int = 5) -> pd.DataFrame:
    cache_name = f"kospi_pbr_{years}y"
    disk = _load_parquet(cache_name, max_hours=24 * 7)  # 7일 parquet 재사용
    if disk is not None:
        return disk
    df = get_kospi_pbr_history(years)
    if not df.empty:
        _save_parquet(cache_name, df)
    return df


@st.cache_data(ttl=_MACRO_TTL, show_spinner="경기 국면 분석 중...")
def cached_market_phase() -> dict:
    """금리+EPS 기반 경기 국면 자동 판단. 1시간 캐시."""
    return get_market_phase()


@st.cache_data(ttl=_MACRO_TTL, show_spinner="환율 데이터 로딩 중...")
def cached_exchange_rate() -> float:
    return get_exchange_rate()


@st.cache_data(ttl=_MACRO_TTL, show_spinner="환율 시계열 로딩 중...")
def cached_exchange_rate_history(years: int = 3) -> pd.DataFrame:
    cache_name = f"usdkrw_{years}y"
    disk = _load_parquet(cache_name, max_hours=1)
    if disk is not None:
        return disk
    df = get_exchange_rate_history(years)
    if not df.empty:
        _save_parquet(cache_name, df)
    return df
