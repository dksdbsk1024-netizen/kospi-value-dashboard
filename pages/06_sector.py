"""섹터 분석 — PBR·ROE 중심 섹터별 투자 환경 분석 (KOSPI+KOSDAQ 전종목)."""

import sys
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.styles import inject_css, COLOR
from utils.valuation import get_investment_signal, get_quadrant, get_phase_label
from data.cache import cached_all_stocks, cached_industry_map
from data.fetcher import is_etf_etn

st.set_page_config(page_title="섹터 분석", page_icon="🏭", layout="wide")
inject_css()

# ──────────────────────────────────────────────────────────────────
# 네이버 79개 업종 → 9개 대분류 매핑
# ──────────────────────────────────────────────────────────────────

UPJONG_TO_SECTOR: dict[str, str] = {
    # 반도체/IT
    "반도체와반도체장비":   "반도체/IT",
    "디스플레이장비및부품": "반도체/IT",
    "디스플레이패널":       "반도체/IT",
    "핸드셋":               "반도체/IT",
    "IT서비스":             "반도체/IT",
    "소프트웨어":           "반도체/IT",
    "컴퓨터와주변기기":     "반도체/IT",
    "사무용전자제품":       "반도체/IT",
    "전자장비와기기":       "반도체/IT",
    "전자제품":             "반도체/IT",
    # 자동차
    "자동차":       "자동차",
    "자동차부품":   "자동차",
    # 금융
    "은행":       "금융",
    "손해보험":   "금융",
    "생명보험":   "금융",
    "증권":       "금융",
    "기타금융":   "금융",
    "카드":       "금융",
    "창업투자":   "금융",
    # 바이오/헬스
    "생물공학":               "바이오/헬스",
    "제약":                   "바이오/헬스",
    "건강관리업체및서비스":   "바이오/헬스",
    "건강관리기술":           "바이오/헬스",
    "건강관리장비와용품":     "바이오/헬스",
    "생명과학도구및서비스":   "바이오/헬스",
    # 플랫폼/통신
    "다각화된통신서비스":       "플랫폼/통신",
    "무선통신서비스":           "플랫폼/통신",
    "통신장비":                 "플랫폼/통신",
    "게임엔터테인먼트":         "플랫폼/통신",
    "방송과엔터테인먼트":       "플랫폼/통신",
    "인터넷과카탈로그소매":     "플랫폼/통신",
    "양방향미디어와서비스":     "플랫폼/통신",
    # 에너지/화학
    "화학":               "에너지/화학",
    "석유와가스":         "에너지/화학",
    "에너지장비및서비스": "에너지/화학",
    "가스유틸리티":       "에너지/화학",
    "전기유틸리티":       "에너지/화학",
    "복합유틸리티":       "에너지/화학",
    "전기제품":           "에너지/화학",
    "전기장비":           "에너지/화학",
    # 소비재/유통
    "백화점과일반상점":       "소비재/유통",
    "판매업체":               "소비재/유통",
    "화장품":                 "소비재/유통",
    "식품":                   "소비재/유통",
    "음료":                   "소비재/유통",
    "레저용장비와제품":       "소비재/유통",
    "섬유,의류,신발,호화품":  "소비재/유통",
    "가정용기기와용품":       "소비재/유통",
    "가정용품":               "소비재/유통",
    "식품과기본식료품소매":   "소비재/유통",
    "가구":                   "소비재/유통",
    "호텔,레스토랑,레저":     "소비재/유통",
    "교육서비스":             "소비재/유통",
    "담배":                   "소비재/유통",
    "전문소매":               "소비재/유통",
    "광고":                   "소비재/유통",
    "다각화된소비자서비스":   "소비재/유통",
    "문구류":                 "소비재/유통",
    "출판":                   "소비재/유통",
    "부동산":                 "소비재/유통",
    # 산업재
    "우주항공과국방":         "산업재",
    "조선":                   "산업재",
    "건설":                   "산업재",
    "기계":                   "산업재",
    "운송인프라":             "산업재",
    "항공사":                 "산업재",
    "해운사":                 "산업재",
    "도로와철도운송":         "산업재",
    "항공화물운송과물류":     "산업재",
    "복합기업":               "산업재",
    "무역회사와판매업체":     "산업재",
    "상업서비스와공급품":     "산업재",
    # 소재
    "철강":       "소재",
    "비철금속":   "소재",
    "포장재":     "소재",
    "종이와목재": "소재",
    "건축자재":   "소재",
    "건축제품":   "소재",
    "담":         "소재",
}

SECTOR_ORDER = [
    "반도체/IT", "자동차", "금융", "바이오/헬스",
    "플랫폼/통신", "에너지/화학", "소비재/유통", "산업재", "소재", "기타",
]


def _upjong_to_sector(upjong: str) -> str:
    return UPJONG_TO_SECTOR.get(upjong, "기타")


# ──────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _underval_ratio(sub: pd.DataFrame) -> float:
    valid = sub.dropna(subset=["pbr", "roe"])
    if valid.empty:
        return 0.0
    cnt = sum(
        1 for _, r in valid.iterrows()
        if get_investment_signal(r["pbr"], r["roe"])["label"] == "저평가 우량"
    )
    return round(cnt / len(valid) * 100, 1)


# ──────────────────────────────────────────────────────────────────
# 데이터 로딩
# ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_stocks() -> pd.DataFrame:
    return cached_all_stocks("ALL")


@st.cache_data(ttl=86400, show_spinner=False)
def load_kospi_index() -> pd.Series:
    from pykrx import stock as krx

    end   = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=400)).strftime("%Y%m%d")
    try:
        df = krx.get_index_ohlcv(start, end, "1001")
        if df.empty:
            return pd.Series(dtype=float)
        df.index = pd.to_datetime(df.index)
        return df["종가"]
    except Exception:
        return pd.Series(dtype=float)


@st.cache_data(ttl=86400, show_spinner=False)
def load_sector_snapshots_cached(sector_ticker_json: str) -> pd.DataFrame:
    """섹터별 기간 수익률. pykrx 단일 종목 OHLCV 방식 (get_market_ohlcv_by_ticker KRX 응답 변경으로 broken)."""
    import json
    import time
    from pykrx import stock as krx

    tickers_by_sector: dict[str, list[str]] = json.loads(sector_ticker_json)
    today = date.today()
    period_days = {"1M": 30, "3M": 90, "6M": 180, "12M": 365}
    max_days = max(period_days.values())

    start_str = (today - timedelta(days=max_days + 15)).strftime("%Y%m%d")
    end_str   = today.strftime("%Y%m%d")

    # 섹터별 상위 5종목 OHLCV 수집 (전체 최대 기간 한번에)
    all_tickers = list({t for tickers in tickers_by_sector.values() for t in tickers})
    ohlcv_map: dict[str, pd.Series] = {}  # ticker → 종가 Series (DatetimeIndex)

    for ticker in all_tickers:
        try:
            df = krx.get_market_ohlcv(start_str, end_str, ticker)
            if not df.empty and "종가" in df.columns:
                df.index = pd.to_datetime(df.index)
                ohlcv_map[ticker] = df["종가"]
        except Exception:
            continue
        time.sleep(0.05)  # KRX API 최소 간격

    if not ohlcv_map:
        return pd.DataFrame()

    today_ts = pd.Timestamp(today)

    def _latest_price(series: pd.Series) -> float | None:
        recent = series[series.index <= today_ts]
        if recent.empty or (today_ts - recent.index[-1]).days > 7:
            return None
        v = float(recent.iloc[-1])
        return v if v > 0 else None

    def _past_price(series: pd.Series, days: int) -> float | None:
        cutoff = today_ts - timedelta(days=days)
        past = series[series.index <= cutoff]
        if past.empty:
            return None
        v = float(past.iloc[-1])
        return v if v > 0 else None

    records = []
    for label, days in period_days.items():
        for sector, tickers in tickers_by_sector.items():
            rets = []
            for t in tickers:
                series = ohlcv_map.get(t)
                if series is None:
                    continue
                p_now = _latest_price(series)
                p_old = _past_price(series, days)
                if p_now and p_old and p_old > 0:
                    rets.append((p_now / p_old - 1) * 100)
            if rets:
                records.append({
                    "섹터": sector,
                    "기간": label,
                    "수익률(%)": float(np.mean(rets)),
                    "종목수": len(rets),
                })

    return pd.DataFrame(records)


# ──────────────────────────────────────────────────────────────────
# 데이터 준비
# ──────────────────────────────────────────────────────────────────

st.title("🏭 섹터 분석")

with st.spinner("밸류에이션 데이터 로딩..."):
    raw_df = load_all_stocks()

if raw_df.empty:
    st.error("데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    st.stop()

with st.spinner("업종 데이터 로딩... (최초 약 30초, 이후 24시간 캐시)"):
    industry_map: dict = cached_industry_map()

# ETF/ETN 제외 (is_etf 컬럼 없는 구버전 캐시 fallback 포함)
if "is_etf" not in raw_df.columns:
    raw_df = raw_df.copy()
    raw_df["is_etf"] = raw_df["name"].apply(is_etf_etn)

# 전종목에 네이버 업종 → 9개 대분류 매핑 (ETF/ETN 제외)
_base_df = raw_df[~raw_df["is_etf"]].copy()
_base_df["upjong"] = _base_df["ticker"].map(industry_map).fillna("기타")
_base_df["sector"] = _base_df["upjong"].map(_upjong_to_sector)

# ── 시장 필터 ──
_mkt_col, _ = st.columns([2, 5])
with _mkt_col:
    market_filter = st.radio("시장", ["전체", "KOSPI", "KOSDAQ"], horizontal=True)

if market_filter == "전체":
    all_df = _base_df.copy()
else:
    all_df = _base_df[_base_df["market"] == market_filter].copy()

# ── 섹터 내 상대 저평가 백분위 계산 ──
all_df["pbr_pct"] = 50.0
all_df["roe_pct"] = 50.0
for _sec, _grp_idx in all_df.groupby("sector").groups.items():
    _grp = all_df.loc[_grp_idx]
    if len(_grp) > 1:
        all_df.loc[_grp_idx, "pbr_pct"] = (
            _grp["pbr"].rank(pct=True, na_option="bottom") * 100
        ).round(1)
        all_df.loc[_grp_idx, "roe_pct"] = (
            _grp["roe"].rank(pct=True, na_option="bottom") * 100
        ).round(1)
all_df["rel_score"] = (
    (1 - all_df["pbr_pct"] / 100) * 50 + all_df["roe_pct"] / 100 * 50
).round(1)

total_stocks = len(all_df)
mapped_stocks = (all_df["sector"] != "기타").sum()

st.caption(
    f"{market_filter} {total_stocks:,}개 종목 | "
    f"업종 분류 완료 {mapped_stocks:,}개"
)

# 섹터별 집계 (전종목 기준)
sector_agg = (
    all_df.groupby("sector")
    .agg(
        종목수=("ticker", "count"),
        평균PBR=("pbr", lambda x: x.dropna().mean()),
        평균ROE=("roe", lambda x: x.dropna().mean()),
        평균PER=("per", lambda x: x.dropna().mean()),
        총시가총액=("marcap", lambda x: x.dropna().sum()),
    )
    .reset_index()
    .rename(columns={"sector": "섹터"})
)
sector_agg["저평가비율(%)"] = sector_agg["섹터"].apply(
    lambda s: _underval_ratio(all_df[all_df["sector"] == s])
)
sector_agg["평균PBR"] = sector_agg["평균PBR"].round(2)
sector_agg["평균ROE"] = sector_agg["평균ROE"].round(2)
sector_agg["평균PER"] = sector_agg["평균PER"].round(1)

# SECTOR_ORDER 기준 정렬
sector_agg["_order"] = sector_agg["섹터"].map(
    {s: i for i, s in enumerate(SECTOR_ORDER)}
).fillna(99)
sector_agg = sector_agg.sort_values("_order").drop(columns="_order").reset_index(drop=True)

# ──────────────────────────────────────────────────────────────────
# 탭
# ──────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 섹터 개요",
    "🎯 PBR-ROE 포지션",
    "🔄 섹터 로테이션",
    "🧭 경기국면 연동",
    "📋 종목 현황",
])

# ══════════════════════════════════════════════════════════════════
# 탭 1 — 섹터 개요
# ══════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("섹터별 밸류에이션 요약")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("분석 섹터 수", f"{sector_agg['섹터'].nunique()}개")
    c2.metric("전체 종목 수", f"{total_stocks:,}개")
    if not sector_agg.empty:
        best_val_sec = sector_agg.loc[sector_agg["저평가비율(%)"].idxmax(), "섹터"]
        low_pbr_sec  = sector_agg.dropna(subset=["평균PBR"]).loc[
            sector_agg.dropna(subset=["평균PBR"])["평균PBR"].idxmin(), "섹터"
        ]
        c3.metric("저평가 비율 1위 섹터", best_val_sec)
        c4.metric("평균 PBR 최저 섹터", low_pbr_sec)

    st.dataframe(
        sector_agg[["섹터", "종목수", "평균PBR", "평균ROE", "평균PER", "총시가총액", "저평가비율(%)"]]
        .style
        .background_gradient(subset=["저평가비율(%)"], cmap="Blues")
        .background_gradient(subset=["평균ROE"], cmap="RdYlGn"),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    tree_df = sector_agg[sector_agg["총시가총액"] > 0].copy()
    if not tree_df.empty:
        fig_tree = px.treemap(
            tree_df,
            path=["섹터"],
            values="총시가총액",
            color="평균ROE",
            color_continuous_scale="RdYlGn",
            hover_data={"평균PBR": True, "저평가비율(%)": True, "종목수": True},
            title="섹터별 시가총액 비중 (색상: 평균 ROE)",
        )
        fig_tree.update_layout(
            height=420, margin=dict(t=50, b=0),
            font=dict(family="Noto Sans KR, sans-serif"),
        )
        st.plotly_chart(fig_tree, use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# 탭 2 — PBR-ROE 포지션
# ══════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("섹터별 PBR-ROE 4사분면 포지셔닝")
    st.caption(f"X축: 평균 ROE(%) | Y축: 평균 PBR | 버블 크기: 총 시가총액 | 전체 {total_stocks:,}종목 기준")

    _QUAD_LABEL = {
        "low_pbr_high_roe":  "저평가 우량 (목표 영역)",
        "high_pbr_high_roe": "고평가 우량",
        "low_pbr_low_roe":   "가치함정",
        "high_pbr_low_roe":  "고평가 위험",
    }
    _QUAD_COLOR = {
        "low_pbr_high_roe":  COLOR["primary"],
        "high_pbr_high_roe": COLOR["text_muted"],
        "low_pbr_low_roe":   COLOR["warning"],
        "high_pbr_low_roe":  COLOR["negative"],
    }

    plot_df = sector_agg.dropna(subset=["평균PBR", "평균ROE"]).copy()
    plot_df["quadrant"] = plot_df.apply(
        lambda r: get_quadrant(r["평균PBR"], r["평균ROE"],
                               pbr_threshold=1.0, roe_threshold=15.0), axis=1
    )
    max_cap = plot_df["총시가총액"].max() or 1

    fig_quad = go.Figure()
    fig_quad.add_hline(
        y=1.0, line_dash="dash", line_color="#9ca3af", line_width=1.5,
        annotation_text="PBR=1.0", annotation_position="right",
    )
    fig_quad.add_vline(
        x=15.0, line_dash="dash", line_color="#9ca3af", line_width=1.5,
        annotation_text="ROE=15%", annotation_position="top",
    )

    for _, row in plot_df.iterrows():
        bubble_size = max(row["총시가총액"] / max_cap * 70, 18)
        clr = _QUAD_COLOR.get(row["quadrant"], "#6b7280")
        fig_quad.add_trace(go.Scatter(
            x=[row["평균ROE"]], y=[row["평균PBR"]],
            mode="markers+text",
            text=[row["섹터"]],
            textposition="top center",
            marker=dict(size=bubble_size, color=clr, opacity=0.82,
                        line=dict(color="white", width=2)),
            name=row["섹터"],
            hovertemplate=(
                f"<b>{row['섹터']}</b><br>"
                f"종목 수: {int(row['종목수'])}개<br>"
                f"평균 PBR: {row['평균PBR']:.2f}배<br>"
                f"평균 ROE: {row['평균ROE']:.2f}%<br>"
                f"저평가비율: {row['저평가비율(%)']}%<br>"
                f"판단: {_QUAD_LABEL.get(row['quadrant'], '')}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    for label, x, y, color in [
        ("저평가 우량 ★", 15, 0.4, "#dbeafe"),
        ("고평가 우량",   15, 2.2, "#f3f4f6"),
        ("가치함정",       2, 0.4, "#fef3c7"),
        ("고평가 위험",    2, 2.2, "#fee2e2"),
    ]:
        fig_quad.add_annotation(
            x=x, y=y, text=label, showarrow=False,
            font=dict(size=11, color="#6b7280"),
            bgcolor=color, borderpad=4, opacity=0.7,
        )

    fig_quad.update_layout(
        xaxis=dict(title="평균 ROE (%)", gridcolor="#f3f4f6", zeroline=False),
        yaxis=dict(title="평균 PBR (배)", gridcolor="#f3f4f6", zeroline=False),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Noto Sans KR, sans-serif", size=12),
        height=500, margin=dict(l=50, r=50, t=40, b=50),
    )
    st.plotly_chart(fig_quad, use_container_width=True)

    st.divider()
    st.markdown("**섹터별 저평가 우량주 비율**")
    bar_df = sector_agg.sort_values("저평가비율(%)", ascending=True)
    fig_bar = px.bar(
        bar_df,
        x="저평가비율(%)", y="섹터",
        orientation="h",
        color="저평가비율(%)",
        color_continuous_scale=[[0, "#e8f0fd"], [1, COLOR["primary"]]],
        text="저평가비율(%)",
        title=f"섹터별 저평가 우량주 비율 (저PBR + 고ROE 기준, {total_stocks:,}종목 중)",
    )
    fig_bar.update_traces(texttemplate="%{text}%", textposition="outside")
    fig_bar.update_layout(
        height=420, showlegend=False, coloraxis_showscale=False,
        font=dict(family="Noto Sans KR, sans-serif"),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=40, r=60, t=50, b=40),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# 탭 3 — 섹터 로테이션 (전종목 기준)
# ══════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("섹터 로테이션 분석")

    # 섹터별 시가총액 상위 5종목만 사용 (pykrx 단일 OHLCV 방식 전환으로 속도 제한)
    tickers_by_sector = (
        all_df[all_df["sector"] != "기타"]
        .sort_values("marcap", ascending=False)
        .groupby("sector")["ticker"]
        .apply(lambda x: list(x)[:5])
        .to_dict()
    )
    analyzed_count = sum(len(v) for v in tickers_by_sector.values())
    st.caption(
        f"업종 분류 완료 {analyzed_count:,}종목 동일비중 수익률 기준 "
        "| 최초 로드 시 약 30초 소요 (이후 24시간 캐시)"
    )

    with st.spinner("기간별 수익률 계산 중... (시장 스냅샷 방식, 최초 약 30초)"):
        import json as _json
        sector_ret_df = load_sector_snapshots_cached(
            _json.dumps(tickers_by_sector, ensure_ascii=False)
        )

    if sector_ret_df.empty:
        st.warning("수익률 데이터를 불러오지 못했습니다.")
    else:
        period_order = ["1M", "3M", "6M", "12M"]
        melt_df = sector_ret_df.copy()
        melt_df["기간"] = pd.Categorical(melt_df["기간"], categories=period_order, ordered=True)
        melt_df = melt_df.sort_values("기간")

        fig_rot = px.bar(
            melt_df,
            x="섹터", y="수익률(%)", color="기간",
            barmode="group",
            title=f"섹터별 기간별 평균 수익률 (전종목 동일비중, {analyzed_count:,}종목)",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_rot.update_layout(
            height=450, margin=dict(t=50, b=0),
            font=dict(family="Noto Sans KR, sans-serif"),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_rot, use_container_width=True)

        m3_df = sector_ret_df[sector_ret_df["기간"] == "3M"].dropna(subset=["수익률(%)"])
        if not m3_df.empty:
            best  = m3_df.nlargest(1,  "수익률(%)").iloc[0]
            worst = m3_df.nsmallest(1, "수익률(%)").iloc[0]
            c1, c2 = st.columns(2)
            c1.success(f"3M 최강세 섹터: **{best['섹터']}** ({best['수익률(%)']:.2f}%)")
            c2.warning(f"3M 최약세 섹터: **{worst['섹터']}** ({worst['수익률(%)']:.2f}%)")

        st.divider()
        st.markdown("**섹터별 기간별 수익률 히트맵**")
        pivot_df = sector_ret_df.pivot(
            index="섹터", columns="기간", values="수익률(%)"
        ).reindex(columns=period_order)
        if not pivot_df.empty:
            fig_heat = px.imshow(
                pivot_df.astype(float),
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0,
                text_auto=".1f",
                title="섹터별 기간 수익률 히트맵 (%)",
                aspect="auto",
            )
            fig_heat.update_layout(
                height=380, margin=dict(t=50, b=0),
                font=dict(family="Noto Sans KR, sans-serif"),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig_heat, use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# 탭 4 — 경기국면 연동
# ══════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("경기 국면 × 섹터 적합도")

    col_l, col_r = st.columns(2)
    rate_dir = col_l.selectbox(
        "금리 방향",
        ["down", "up", "flat"],
        format_func=lambda x: {"down": "↓ 하락", "up": "↑ 상승", "flat": "→ 보합"}[x],
    )
    eps_dir = col_r.selectbox(
        "EPS(실적) 방향",
        ["up", "down", "flat"],
        format_func=lambda x: {"up": "↑ 상승", "down": "↓ 하락", "flat": "→ 보합"}[x],
    )

    phase = get_phase_label(rate_dir, eps_dir)

    st.markdown(
        f"""
        <div style="background:{COLOR['primary_light']};border-left:4px solid {COLOR['primary']};
                    padding:16px 20px;border-radius:8px;margin:12px 0 16px;">
          <div style="font-size:20px;font-weight:700;color:{COLOR['primary_dark']};">{phase['label']}</div>
          <div style="margin-top:8px;color:{COLOR['text_primary']};">{phase['strategy']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if phase["favorable_sectors"]:
        st.markdown("**이 국면에서 유리한 섹터/자산:**")
        cols = st.columns(len(phase["favorable_sectors"]))
        for col_item, sec_name in zip(cols, phase["favorable_sectors"]):
            col_item.markdown(
                f'<div style="text-align:center;background:{COLOR["bg_surface"]};'
                f'border:1px solid {COLOR["border"]};border-radius:8px;padding:10px 6px;'
                f'font-weight:500;font-size:14px;">{sec_name}</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown(f"**섹터별 현재 국면 적합도 점수** (전체 {total_stocks:,}종목 기준)")

    fit_df = sector_agg[["섹터", "평균PBR", "평균ROE", "저평가비율(%)", "종목수"]].copy()

    if phase["phase"] in ("금융장세", "역실적장세"):
        fit_df["적합도점수"] = (
            (1 / fit_df["평균PBR"].clip(0.1)) * 25
            + fit_df["저평가비율(%)"] * 0.75
        )
    elif phase["phase"] == "실적장세":
        fit_df["적합도점수"] = (
            fit_df["평균ROE"].clip(0) * 2.0
            + fit_df["저평가비율(%)"] * 0.5
        )
    else:
        fit_df["적합도점수"] = (
            fit_df["평균ROE"].clip(0) * 0.8
            + (10 - fit_df["평균PBR"].clip(0, 10)) * 3
        )

    mn, mx = fit_df["적합도점수"].min(), fit_df["적합도점수"].max()
    if mx > mn:
        fit_df["적합도점수"] = ((fit_df["적합도점수"] - mn) / (mx - mn) * 100).round(1)
    else:
        fit_df["적합도점수"] = 50.0

    fit_df = fit_df.sort_values("적합도점수", ascending=False)

    st.dataframe(
        fit_df.style
        .background_gradient(subset=["적합도점수"], cmap="Blues")
        .background_gradient(subset=["평균ROE"], cmap="RdYlGn"),
        use_container_width=True,
        hide_index=True,
    )

    fig_fit = px.bar(
        fit_df.sort_values("적합도점수"),
        x="적합도점수", y="섹터",
        orientation="h",
        color="적합도점수",
        color_continuous_scale=[[0, "#e8f0fd"], [1, COLOR["primary"]]],
        text="적합도점수",
        title=f"'{phase['phase']}' 국면 섹터 적합도",
    )
    fig_fit.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig_fit.update_layout(
        height=420, showlegend=False, coloraxis_showscale=False,
        font=dict(family="Noto Sans KR, sans-serif"),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=40, r=60, t=50, b=40),
    )
    st.plotly_chart(fig_fit, use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# 탭 5 — 종목 현황 + 섹터 내 상대 저평가
# ══════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("섹터별 종목 현황")

    available_sectors = [s for s in SECTOR_ORDER if s in all_df["sector"].values]
    sel_sec = st.selectbox("섹터 선택", available_sectors, key="sector_stock_detail")

    sec_stocks = all_df[all_df["sector"] == sel_sec].copy()

    if sec_stocks.empty:
        st.info("해당 섹터 종목 데이터가 없습니다.")
    else:
        sec_stocks["판단"] = sec_stocks.apply(
            lambda r: (
                get_investment_signal(r["pbr"], r["roe"])["label"]
                if pd.notna(r["pbr"]) and pd.notna(r["roe"]) else "데이터 없음"
            ),
            axis=1,
        )

        st.caption(
            f"{sel_sec} 섹터 총 {len(sec_stocks)}개 종목 "
            "| 상대저평가점수: 섹터 내 PBR·ROE 백분위 기반 (0~100, 높을수록 저평가 우량)"
        )

        # ── Top 3 섹터 내 상대 저평가 하이라이트 ──
        top3 = sec_stocks.dropna(subset=["pbr", "roe"]).nlargest(3, "rel_score")
        if not top3.empty:
            st.markdown("**섹터 내 상대 저평가 Top 3 종목**")
            tcols = st.columns(len(top3))
            for tc, (_, tr) in zip(tcols, top3.iterrows()):
                score_color = COLOR["primary"] if tr["rel_score"] >= 70 else COLOR["warning"]
                tc.markdown(
                    f"""<div style="background:white;border:2px solid {score_color};
                            border-radius:10px;padding:12px 14px;text-align:center;">
                      <div style="font-size:14px;font-weight:700;">{tr['name']}</div>
                      <div style="font-size:11px;color:#6b7280;">{tr['ticker']} | {tr['market']}</div>
                      <div style="margin-top:6px;">
                        <span style="font-size:11px;color:#6b7280;">PBR </span>
                        <span style="font-size:15px;font-weight:600;color:{COLOR['primary']};">{tr['pbr']:.2f}</span>
                        <span style="font-size:11px;color:#6b7280;margin-left:8px;">ROE </span>
                        <span style="font-size:15px;font-weight:600;color:{COLOR['positive']};">{tr['roe']:.1f}%</span>
                      </div>
                      <div style="margin-top:4px;font-size:11px;color:#6b7280;">
                        섹터내 저평가 점수
                        <b style="color:{score_color};">{tr['rel_score']:.0f}</b>/100
                      </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            st.markdown("")

        # ── 정렬 옵션 ──
        sort_col = st.selectbox(
            "정렬 기준",
            ["섹터 내 상대 저평가 우선", "시가총액(억) 내림차순", "PBR 오름차순", "ROE(%) 내림차순", "저평가 우량 우선"],
            key="sector_sort",
        )

        if sort_col == "섹터 내 상대 저평가 우선":
            sec_stocks = sec_stocks.sort_values("rel_score", ascending=False)
        elif sort_col == "PBR 오름차순":
            sec_stocks = sec_stocks.sort_values("pbr", ascending=True)
        elif sort_col == "ROE(%) 내림차순":
            sec_stocks = sec_stocks.sort_values("roe", ascending=False)
        elif sort_col == "저평가 우량 우선":
            _order_map = {
                "저평가 우량": 0, "고평가 우량": 1,
                "가치함정": 2, "고평가 위험": 3, "데이터 없음": 4,
            }
            sec_stocks["_sort"] = sec_stocks["판단"].map(_order_map).fillna(9)
            sec_stocks = sec_stocks.sort_values(["_sort", "pbr"]).drop(columns="_sort")
        else:
            sec_stocks = sec_stocks.sort_values("marcap", ascending=False)

        # ── 종목 테이블 (백분위 + 상대저평가점수 컬럼 포함) ──
        disp_df = (
            sec_stocks[[
                "name", "ticker", "market", "upjong",
                "pbr", "pbr_pct", "roe", "roe_pct",
                "per", "eps", "marcap", "rel_score", "판단",
            ]].rename(columns={
                "name": "종목명", "ticker": "코드", "market": "시장",
                "upjong": "업종", "pbr": "PBR", "pbr_pct": "PBR백분위",
                "roe": "ROE(%)", "roe_pct": "ROE백분위",
                "per": "PER", "eps": "EPS", "marcap": "시가총액(억)",
                "rel_score": "상대저평가점수", "판단": "절대판단",
            })
        )

        st.dataframe(
            disp_df.style
            .background_gradient(subset=["ROE(%)"], cmap="RdYlGn")
            .background_gradient(subset=["상대저평가점수"], cmap="Blues"),
            use_container_width=True,
            hide_index=True,
        )

        # ── 섹터 내 포지셔닝 스캐터 ──
        st.divider()
        st.markdown("**섹터 내 PBR-ROE 상대 포지셔닝** (백분위 기준)")
        st.caption("우하단(저PBR백분위 + 고ROE백분위)이 섹터 내 상대적 저평가 우량 영역")

        plot_sec = sec_stocks.dropna(subset=["pbr_pct", "roe_pct"])
        if not plot_sec.empty:
            for _ann_x, _ann_y, _ann_text, _ann_bg in [
                (75, 25, "섹터 내 저평가 우량 ★", "#dbeafe"),
                (75, 75, "고평가 우량",            "#f3f4f6"),
                (25, 25, "가치함정",               "#fef3c7"),
                (25, 75, "고평가 위험",            "#fee2e2"),
            ]:
                pass  # annotations added after figure creation

            fig_rel = go.Figure()
            fig_rel.add_hline(y=50, line_dash="dash", line_color="#9ca3af", line_width=1)
            fig_rel.add_vline(x=50, line_dash="dash", line_color="#9ca3af", line_width=1)

            for _ann_x, _ann_y, _ann_text, _ann_bg in [
                (75, 25, "섹터 내 저평가 우량 ★", "#dbeafe"),
                (75, 75, "고평가 우량",            "#f3f4f6"),
                (25, 25, "가치함정",               "#fef3c7"),
                (25, 75, "고평가 위험",            "#fee2e2"),
            ]:
                fig_rel.add_annotation(
                    x=_ann_x, y=_ann_y, text=_ann_text, showarrow=False,
                    font=dict(size=10, color="#6b7280"), bgcolor=_ann_bg,
                    borderpad=3, opacity=0.75,
                )

            fig_rel.add_trace(go.Scatter(
                x=plot_sec["roe_pct"],
                y=plot_sec["pbr_pct"],
                mode="markers",
                text=plot_sec["name"],
                marker=dict(
                    size=(plot_sec["rel_score"] / 100 * 28 + 8).clip(8, 36),
                    color=plot_sec["rel_score"],
                    colorscale=[[0, "#fee2e2"], [0.5, "#fef3c7"], [1, COLOR["primary"]]],
                    colorbar=dict(title="상대저평가점수", thickness=12),
                    showscale=True,
                    line=dict(color="white", width=1),
                ),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "ROE 백분위: %{x:.0f}%<br>"
                    "PBR 백분위: %{y:.0f}%<br>"
                    "상대저평가점수: %{marker.color:.0f}"
                    "<extra></extra>"
                ),
            ))
            fig_rel.update_layout(
                xaxis=dict(
                    title="ROE 섹터 내 백분위 (%) — 높을수록 수익성 우수",
                    range=[-5, 110], gridcolor="#f3f4f6",
                ),
                yaxis=dict(
                    title="PBR 섹터 내 백분위 (%) — 낮을수록 저렴",
                    range=[-5, 110], gridcolor="#f3f4f6",
                ),
                plot_bgcolor="white", paper_bgcolor="white",
                font=dict(family="Noto Sans KR, sans-serif", size=12),
                height=500, margin=dict(l=50, r=80, t=30, b=50),
            )
            st.plotly_chart(fig_rel, use_container_width=True)

        # ── 레이더 차트 — 상위 6개 종목 상대 지표 비교 ──
        radar_stocks = sec_stocks.dropna(subset=["pbr", "roe", "per"]).head(6)
        if len(radar_stocks) >= 2:
            st.divider()
            st.markdown("**섹터 내 상위 6개 종목 상대 지표 레이더 (높을수록 유리)**")

            def _norm(series: pd.Series, invert: bool = False) -> pd.Series:
                mn, mx = series.min(), series.max()
                if mx == mn:
                    return pd.Series([50.0] * len(series), index=series.index)
                n = (series - mn) / (mx - mn) * 100
                return (100 - n) if invert else n

            radar_df = pd.DataFrame({
                "종목":  radar_stocks["name"].values,
                "ROE":   _norm(radar_stocks["roe"].reset_index(drop=True)).values,
                "저PBR": _norm(radar_stocks["pbr"].reset_index(drop=True), invert=True).values,
                "저PER": _norm(radar_stocks["per"].reset_index(drop=True), invert=True).values,
                "EPS":   _norm(radar_stocks["eps"].fillna(0).reset_index(drop=True)).values,
            })

            categories = ["ROE", "저PBR", "저PER", "EPS"]
            clrs_r = px.colors.qualitative.Plotly
            fig_radar = go.Figure()

            for i, row in radar_df.iterrows():
                vals = [row[c] for c in categories]
                fig_radar.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=categories + [categories[0]],
                    name=row["종목"],
                    line=dict(color=clrs_r[i % len(clrs_r)]),
                    fill="toself",
                    fillcolor=_hex_to_rgba(clrs_r[i % len(clrs_r)], 0.12),
                ))

            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                title=f"{sel_sec} 섹터 종목 상대 지표 비교",
                height=460, margin=dict(t=60, b=10),
                font=dict(family="Noto Sans KR, sans-serif"),
            )
            st.plotly_chart(fig_radar, use_container_width=True)
