"""
매크로 지표 수집 모듈.

- 미국 10년 국채 금리: FinanceDataReader (FRED)
- KOSPI PBR: Naver 당일 데이터 기반 (app.py에서 직접 계산)
- USD/KRW 환율: FinanceDataReader
"""

import datetime
import pandas as pd
import FinanceDataReader as fdr


def _business_days_ago(n: int) -> str:
    """오늘로부터 n 영업일 이전 날짜를 YYYYMMDD 문자열로 반환."""
    d = datetime.date.today()
    count = 0
    while count < n:
        d -= datetime.timedelta(days=1)
        if d.weekday() < 5:  # 월~금
            count += 1
    return d.strftime("%Y%m%d")


def get_us10y_yield(years: int = 3) -> pd.DataFrame:
    """미국 10년 국채 금리 시계열.

    Args:
        years: 수집 기간(년)

    Returns:
        DataFrame 컬럼: date, yield
    """
    start = (datetime.date.today() - datetime.timedelta(days=years * 365)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader("US10YT=X", start)
        if df.empty:
            # 대체: FRED 직접
            df = fdr.DataReader("FRED:DGS10", start)
    except Exception:
        df = fdr.DataReader("FRED:DGS10", start)

    df = df.reset_index()
    df.columns = ["date"] + list(df.columns[1:])
    # Close 또는 Value 컬럼을 yield로 통일
    val_col = next((c for c in df.columns if c.lower() in ("close", "value", "dgs10")), df.columns[1])
    df = df[["date", val_col]].rename(columns={val_col: "yield"})
    df = df.dropna(subset=["yield"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def get_kospi_pbr_history(years: int = 5) -> pd.DataFrame:
    """KOSPI PBR 역사적 시계열.

    현재 환경에서 pykrx get_index_fundamental / get_market_fundamental 모두
    KRX API 응답 컬럼명 변경으로 동작하지 않는다. 빈 DataFrame을 반환하며
    호출부(app.py)는 당일 Naver 데이터로 대체한다.

    Returns:
        빈 DataFrame (컬럼: date, pbr, per)
    """
    return pd.DataFrame(columns=["date", "pbr", "per"])


def get_exchange_rate() -> float:
    """USD/KRW 환율 현재값.

    Returns:
        float: 현재 환율 (예: 1380.5)
    """
    try:
        df = fdr.DataReader("USD/KRW")
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass

    # 대체: KRX에서 직접
    try:
        df = fdr.DataReader("KRX/USD")
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass

    return float("nan")


def _phase_from_signals(rate_rising: bool | None, spread_rising: bool | None) -> dict:
    """금리·스프레드 방향 신호 → 국면 dict 변환 헬퍼."""
    phase_map = {
        (False, False): ("금융장세",   "🟢", "#10b981",
                         "금리↓ + 스프레드 축소 — 유동성 장세. 성장주·금리민감주 유리."),
        (False, True):  ("실적장세",   "🔵", "#2F64E3",
                         "금리↓ + 스프레드 확대 — 최적 장세. 경기민감주·가치주 전반 유리."),
        (True,  True):  ("역금융장세", "🟡", "#f59e0b",
                         "금리↑ + 스프레드 확대 — 실적 호조, 금리 부담 시작. 고ROE 종목 선별 필요."),
        (True,  False): ("역실적장세", "🔴", "#ef4444",
                         "금리↑ + 스프레드 축소 — 최악 장세. 방어주·현금 비중 확대 권고."),
    }
    if rate_rising is None and spread_rising is None:
        return {"phase": "판단불가", "label": "데이터 부족", "emoji": "⚪",
                "color": "#6b7280", "rate_dir": None, "spread_dir": None, "description": "데이터 없음"}
    if rate_rising is None:
        rate_rising = not spread_rising
    if spread_rising is None:
        spread_rising = not rate_rising
    label, emoji, color, description = phase_map[(rate_rising, spread_rising)]
    return {
        "phase": label, "label": f"{emoji} {label}", "emoji": emoji, "color": color,
        "rate_dir": "상승" if rate_rising else "하락",
        "spread_dir": "확대" if spread_rising else "축소",
        "description": description,
    }


def get_market_phase() -> dict:
    """경기 국면 자동 판단.

    주 판단: 한국 국고채 금리(FRED 월간) 기반
    참고용: 미국 금리(FRED 일간) 기반

    Returns:
        {
          primary: 한국 기준 국면 dict,
          reference: 미국 기준 국면 dict,
          kr_rate: 한국 10년 금리 최근값,
          kr_spread: 한국 장단기 스프레드 최근값,
          us_rate: 미국 10년 금리 최근값,
          us_spread: 미국 T10Y2Y 최근값,
        }
    """
    kr_rate_rising: bool | None = None
    kr_spread_rising: bool | None = None
    us_rate_rising: bool | None = None
    us_spread_rising: bool | None = None
    kr_rate_val = kr_spread_val = us_rate_val = us_spread_val = None

    start_2y = (datetime.date.today() - datetime.timedelta(days=730)).strftime("%Y-%m-%d")
    start_1y = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    # ── 한국 10년 국고채 금리 (FRED 월간) ──
    try:
        df_kr10 = fdr.DataReader("FRED:IRLTLT01KRM156N", start_2y).reset_index().dropna()
        df_kr10.columns = ["date", "rate"]
        if len(df_kr10) >= 6:
            kr_rate_val = round(float(df_kr10["rate"].iloc[-1]), 3)
            kr_rate_rising = bool(df_kr10["rate"].iloc[-3:].mean() > df_kr10["rate"].iloc[-6:-3].mean())
    except Exception:
        pass

    # ── 한국 장단기 스프레드 (10년 - 단기) ──
    try:
        df_krst = fdr.DataReader("FRED:IRSTCI01KRM156N", start_2y).reset_index().dropna()
        df_krst.columns = ["date", "rate"]
        if kr_rate_val is not None and len(df_krst) >= 6:
            kr_spread_val = round(kr_rate_val - float(df_krst["rate"].iloc[-1]), 3)
            kr_spread_series = (
                df_kr10["rate"].iloc[-len(df_krst):].values - df_krst["rate"].values
            )
            if len(kr_spread_series) >= 6:
                kr_spread_rising = bool(kr_spread_series[-3:].mean() > kr_spread_series[-6:-3].mean())
    except Exception:
        pass

    # ── 미국 10년 금리 (일간) ──
    try:
        yield_df = get_us10y_yield(years=1)
        if len(yield_df) >= 40:
            us_rate_val = round(float(yield_df["yield"].iloc[-1]), 3)
            us_rate_rising = bool(yield_df["yield"].iloc[-20:].mean() > yield_df["yield"].iloc[-40:-20].mean())
    except Exception:
        pass

    # ── 미국 T10Y2Y 스프레드 (일간) ──
    try:
        df_us = fdr.DataReader("FRED:T10Y2Y", start_1y).reset_index().dropna()
        df_us.columns = ["date", "spread"]
        if len(df_us) >= 40:
            us_spread_val = round(float(df_us["spread"].iloc[-1]), 3)
            us_spread_rising = bool(df_us["spread"].iloc[-20:].mean() > df_us["spread"].iloc[-40:-20].mean())
    except Exception:
        pass

    return {
        "primary":   _phase_from_signals(kr_rate_rising, kr_spread_rising),
        "reference": _phase_from_signals(us_rate_rising, us_spread_rising),
        "kr_rate":   kr_rate_val,
        "kr_spread": kr_spread_val,
        "us_rate":   us_rate_val,
        "us_spread": us_spread_val,
    }


def get_exchange_rate_history(years: int = 3) -> pd.DataFrame:
    """USD/KRW 환율 시계열.

    Returns:
        DataFrame 컬럼: date, rate
    """
    start = (datetime.date.today() - datetime.timedelta(days=years * 365)).strftime("%Y-%m-%d")
    try:
        df = fdr.DataReader("USD/KRW", start).reset_index()
        df.columns = [c.lower() for c in df.columns]
        close_col = next((c for c in df.columns if "close" in c), df.columns[1])
        date_col = next((c for c in df.columns if "date" in c or c == "index"), df.columns[0])
        df = df[[date_col, close_col]].rename(columns={date_col: "date", close_col: "rate"})
        df["date"] = pd.to_datetime(df["date"])
        return df.dropna(subset=["rate"]).sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "rate"])
