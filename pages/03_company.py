"""기업 심층분석 페이지."""

import sys
from pathlib import Path
from datetime import date, timedelta

import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_searchbox import st_searchbox

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.styles import inject_css, COLOR
from utils.charts import apply_layout, bar_chart, line_chart
from utils.valuation import get_investment_signal, decompose_pbr, dupont_decompose
from utils.brave_search import news_search as brave_news
from data.cache import cached_stock_financials, cached_stock_roe, cached_ohlcv, cached_all_stocks, cached_industry_map

st.set_page_config(page_title="기업 분석", page_icon="🏢", layout="wide")
inject_css()

st.title("🏢 기업 심층분석")
st.caption("PBR 분해 · 재무 시계열 · 듀퐁 분석 · 최신 뉴스")

# ──────────────────────────────────────────────
# 섹터 내 상대 평가 함수
# ──────────────────────────────────────────────
def _get_peer_signal(ticker: str, pbr: float, roe: float) -> dict:
    """업종 내 상대 평가 신호 반환. 실패 시 절대 기준으로 폴백."""
    try:
        industry_map = cached_industry_map()
        all_df = cached_all_stocks("ALL")
        if not industry_map or all_df.empty:
            return get_investment_signal(pbr, roe)
        my_industry = industry_map.get(str(ticker).zfill(6))
        if not my_industry:
            return get_investment_signal(pbr, roe)
        peer_tickers = {t for t, ind in industry_map.items() if ind == my_industry}
        peer_df = all_df[
            all_df["ticker"].isin(peer_tickers)
            & all_df["pbr"].notna()
            & all_df["roe"].notna()
            & (all_df["pbr"] > 0)
        ]
        if len(peer_df) < 3:
            return get_investment_signal(pbr, roe)
        pbr_pct = (peer_df["pbr"] < pbr).mean() * 100
        roe_pct = (peer_df["roe"] < roe).mean() * 100
        n = len(peer_df)
        if pbr_pct < 50 and roe_pct >= 50:
            return {"label": "업종 내 저평가 우량", "color": COLOR["primary"],
                    "description": f"업종: {my_industry} | PBR 하위 {pbr_pct:.0f}% · ROE 상위 {100-roe_pct:.0f}% (비교 {n}종목)"}
        elif pbr_pct < 50:
            return {"label": "업종 내 가치함정", "color": COLOR["warning"],
                    "description": f"업종: {my_industry} | PBR 하위 {pbr_pct:.0f}% · ROE 하위 {100-roe_pct:.0f}% — 실적 개선 확인 필수"}
        elif roe_pct >= 50:
            return {"label": "업종 내 고평가 우량", "color": COLOR["text_muted"],
                    "description": f"업종: {my_industry} | PBR 상위 {100-pbr_pct:.0f}% · ROE 상위 {100-roe_pct:.0f}%"}
        else:
            return {"label": "업종 내 고평가", "color": COLOR["negative"],
                    "description": f"업종: {my_industry} | PBR 상위 {100-pbr_pct:.0f}% · ROE 하위 {100-roe_pct:.0f}%"}
    except Exception:
        return get_investment_signal(pbr, roe)

# ──────────────────────────────────────────────
# 종목 검색 (typeahead 자동완성)
# ──────────────────────────────────────────────
def _search_stocks(q: str) -> list[str]:
    """입력어와 매칭되는 종목 목록 반환 (이름 또는 코드 검색)."""
    if not q or len(q.strip()) < 1:
        return []
    q = q.strip()
    all_df = cached_all_stocks("ALL")
    if all_df.empty:
        return []
    if q.isdigit():
        matches = all_df[all_df["ticker"].str.startswith(q)]
    else:
        matches = all_df[all_df["name"].str.contains(q, na=False, case=False)]
    return [
        f"{row['name']} ({row['ticker']}, {row['market']})"
        for _, row in matches.head(10).iterrows()
    ]

if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "005930"
if "selected_name" not in st.session_state:
    st.session_state.selected_name = "삼성전자"

col_search, _ = st.columns([2, 3])
with col_search:
    selected_label = st_searchbox(
        _search_stocks,
        key="comp_searchbox",
        placeholder="종목명 또는 6자리 코드 입력 (예: 삼성전자)",
        default=f"{st.session_state.selected_name} ({st.session_state.selected_ticker})",
        clear_on_submit=False,
        label="종목 검색",
    )

# 선택 시 ticker / name 갱신
if selected_label and isinstance(selected_label, str):
    m = re.search(r'\((\d{6}),', selected_label)
    if m:
        _t = m.group(1)
        _n = selected_label[:selected_label.rfind(f"({_t}")].strip()
        st.session_state.selected_ticker = _t
        st.session_state.selected_name = _n

ticker = st.session_state.selected_ticker
name = st.session_state.selected_name

# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
with st.spinner(f"{name} ({ticker}) 데이터 불러오는 중..."):
    fin = cached_stock_financials(ticker)
    roe_df = cached_stock_roe(ticker, years=5)

if not fin or not fin.get("years"):
    st.error(f"종목 데이터를 불러올 수 없습니다. 티커를 확인해 주세요: {ticker}")
    st.stop()

years = fin.get("years", [])
pbr_vals = fin.get("pbr", [])
roe_vals = fin.get("roe", [])
per_vals = fin.get("per", [])
eps_vals = fin.get("eps", [])
bps_vals = fin.get("bps", [])
revenue_vals = fin.get("revenue", [])
op_income_vals = fin.get("op_income", [])
net_income_vals = fin.get("net_income", [])

# 가장 최신값
def _latest(vals):
    for v in reversed(vals):
        if v is not None:
            return v
    return None

latest_pbr = _latest(pbr_vals)
latest_roe = _latest(roe_vals)
latest_per = _latest(per_vals)
latest_eps = _latest(eps_vals)
latest_bps = _latest(bps_vals)

# ──────────────────────────────────────────────
# 기업 기본 정보 + 핵심 지표
# ──────────────────────────────────────────────
st.divider()
st.subheader(f"📌 {name} ({ticker})")

# 투자 판단 배너 (업종 내 상대 평가)
if latest_pbr is not None and latest_roe is not None:
    signal = _get_peer_signal(ticker, latest_pbr, latest_roe)
    sig_color = signal["color"]
    st.markdown(f"""
    <div style="background:{sig_color}15; border-left:4px solid {sig_color};
                padding:12px 16px; border-radius:8px; margin-bottom:16px;">
      <strong style="color:{sig_color}; font-size:1.1rem;">{signal['label']}</strong>
      &nbsp;&nbsp;
      <span style="color:#374151;">{signal['description']}</span>
    </div>
    """, unsafe_allow_html=True)

# 핵심 지표 5개 metric card
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("PBR", f"{latest_pbr:.2f}x" if latest_pbr else "N/A",
              help="주가순자산비율 = 시가총액 / 자기자본")
with m2:
    roe_disp = f"{latest_roe:.1f}%" if latest_roe else "N/A"
    roe_delta = None
    if len(roe_vals) >= 2 and roe_vals[-1] and roe_vals[-2]:
        roe_delta = f"{roe_vals[-1] - roe_vals[-2]:+.1f}%p"
    st.metric("ROE", roe_disp, delta=roe_delta, help="자기자본이익률")
with m3:
    st.metric("PER", f"{latest_per:.1f}x" if latest_per else "N/A",
              help="주가수익비율 = PBR / ROE")
with m4:
    st.metric("EPS", f"{latest_eps:,.0f}원" if latest_eps else "N/A",
              help="주당순이익")
with m5:
    st.metric("BPS", f"{latest_bps:,.0f}원" if latest_bps else "N/A",
              help="주당순자산")

st.divider()

# ──────────────────────────────────────────────
# PBR 분해 시각화: PBR = PER × ROE
# ──────────────────────────────────────────────
st.subheader("🔢 PBR 분해: PBR = PER × ROE")

if latest_pbr and latest_per and latest_roe:
    decomp = decompose_pbr(latest_pbr, latest_per, latest_roe)

    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.markdown(f"""
        <div style="text-align:center; padding:20px; background:#f0f5ff; border-radius:12px;">
          <div style="font-size:0.85rem; color:#6b7280; margin-bottom:4px;">PBR (실제)</div>
          <div style="font-size:2rem; font-weight:700; color:{COLOR['primary']};">{decomp['pbr_actual']:.2f}x</div>
        </div>
        """, unsafe_allow_html=True)
    with col_d2:
        st.markdown(f"""
        <div style="text-align:center; padding:20px; background:#f0fdf4; border-radius:12px;">
          <div style="font-size:0.85rem; color:#6b7280; margin-bottom:4px;">PER</div>
          <div style="font-size:2rem; font-weight:700; color:{COLOR['positive']};">{decomp['per']:.1f}x</div>
        </div>
        """, unsafe_allow_html=True)
    with col_d3:
        st.markdown(f"""
        <div style="text-align:center; padding:20px; background:#fffbeb; border-radius:12px;">
          <div style="font-size:0.85rem; color:#6b7280; margin-bottom:4px;">ROE</div>
          <div style="font-size:2rem; font-weight:700; color:{COLOR['warning']};">{decomp['roe_pct']:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center; padding:8px; color:#6b7280; font-size:0.9rem;">
      PBR 계산값: {decomp['pbr_calc']:.3f}x &nbsp;|&nbsp;
      실제 PBR: {decomp['pbr_actual']:.3f}x &nbsp;|&nbsp;
      {"✅ 일관성 확인 (오차 " + str(decomp['diff_pct']) + "%)" if decomp['is_consistent'] else "⚠️ 오차 " + str(decomp['diff_pct']) + "% (분기/연간 기준 차이)"}
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ──────────────────────────────────────────────
# 주가 추이 · 수익률
# ──────────────────────────────────────────────
st.subheader("💹 주가 추이 · 수익률")

_period_map = {"1개월": 30, "3개월": 90, "6개월": 180, "1년": 365, "3년": 1095}
price_period = st.radio("기간", list(_period_map.keys()), horizontal=True, key="price_period")
_days = _period_map[price_period]
_end = date.today()
_start = _end - timedelta(days=_days)

with st.spinner(f"{name} 주가 데이터 수집 중..."):
    price_df = cached_ohlcv(ticker, _start.strftime("%Y%m%d"), _end.strftime("%Y%m%d"))

if not price_df.empty:
    price_df = price_df.sort_values("date").reset_index(drop=True)

    last_row = price_df.iloc[-1]
    prev_row = price_df.iloc[-2] if len(price_df) >= 2 else last_row
    day_chg = last_row["close"] - prev_row["close"]
    day_chg_pct = day_chg / prev_row["close"] * 100 if prev_row["close"] else 0
    period_ret = (last_row["close"] / price_df.iloc[0]["close"] - 1) * 100
    avg_vol = price_df["volume"].mean()
    _prev_close = last_row["close"]  # 전일 종가 기준

    # 실시간 현재가 자동갱신 (30초)
    @st.fragment(run_every=30)
    def _price_metrics():
        from data.fetcher import get_realtime_price
        rt = get_realtime_price(ticker)
        mc1, mc2, mc3, mc4 = st.columns([2, 1, 1, 1])
        with mc1:
            if rt and rt > 0:
                rt_chg = rt - _prev_close
                rt_pct = rt_chg / _prev_close * 100 if _prev_close else 0
                delta_color = "normal"
                st.metric(
                    "현재가 (실시간 · 30초 자동갱신)",
                    f"{rt:,}원",
                    delta=f"{rt_chg:+,.0f}원 ({rt_pct:+.2f}%) 전일대비",
                    delta_color=delta_color,
                )
            else:
                st.metric(
                    "현재가 (최근 거래일)",
                    f"{_prev_close:,.0f}원",
                    delta=f"{day_chg:+,.0f}원 ({day_chg_pct:+.2f}%) 전일대비",
                )
        with mc2:
            st.metric(f"{price_period} 수익률", f"{period_ret:+.1f}%")
        with mc3:
            st.metric("기간 최고가", f"{price_df['high'].max():,.0f}원")
        with mc4:
            st.metric("평균 거래량", f"{avg_vol:,.0f}주")

    _price_metrics()

    # 종가 + 거래량 서브플롯
    fig_price = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.04,
    )
    fig_price.add_trace(go.Scatter(
        x=price_df["date"], y=price_df["close"],
        mode="lines",
        name="종가",
        line=dict(color=COLOR["primary"], width=1.8),
        fill="tozeroy",
        fillcolor="rgba(47,100,227,0.07)",
        hovertemplate="%{x|%Y-%m-%d}<br>종가: %{y:,.0f}원<extra></extra>",
    ), row=1, col=1)

    vol_colors = [
        COLOR["negative"] if price_df.at[i, "close"] >= price_df.at[i, "open"]
        else COLOR["primary"]
        for i in range(len(price_df))
    ]
    fig_price.add_trace(go.Bar(
        x=price_df["date"], y=price_df["volume"],
        name="거래량",
        marker_color=vol_colors,
        opacity=0.65,
        hovertemplate="%{x|%Y-%m-%d}<br>거래량: %{y:,.0f}<extra></extra>",
    ), row=2, col=1)

    apply_layout(fig_price, "")
    fig_price.update_layout(
        height=460,
        showlegend=False,
        yaxis=dict(title="주가 (원)", tickformat=","),
        yaxis2=dict(title="거래량", tickformat=","),
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # 누적 수익률 라인
    price_df["cum_ret"] = (price_df["close"] / price_df.iloc[0]["close"] - 1) * 100
    ret_color = COLOR["positive"] if period_ret >= 0 else COLOR["negative"]
    fill_color = "rgba(16,185,129,0.08)" if period_ret >= 0 else "rgba(239,68,68,0.08)"

    fig_ret = go.Figure()
    fig_ret.add_hline(y=0, line_dash="dot", line_color=COLOR["border"])
    fig_ret.add_trace(go.Scatter(
        x=price_df["date"], y=price_df["cum_ret"],
        mode="lines",
        line=dict(color=ret_color, width=1.8),
        fill="tozeroy",
        fillcolor=fill_color,
        hovertemplate="%{x|%Y-%m-%d}<br>수익률: %{y:+.2f}%<extra></extra>",
    ))
    apply_layout(fig_ret, f"{price_period} 누적 수익률")
    fig_ret.update_layout(height=260, showlegend=False)
    fig_ret.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_ret, use_container_width=True)
else:
    st.info("주가 데이터를 불러올 수 없습니다.")

st.divider()

# ──────────────────────────────────────────────
# 재무 시계열 차트
# ──────────────────────────────────────────────
st.subheader("📈 재무 시계열 (3~5년)")

chart_tab1, chart_tab2 = st.tabs(["밸류에이션 추이", "손익 추이"])

with chart_tab1:
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        # PBR 추이
        pbr_df = pd.DataFrame({"year": years, "PBR": pbr_vals}).dropna()
        if not pbr_df.empty:
            fig_pbr = go.Figure()
            fig_pbr.add_trace(go.Scatter(
                x=pbr_df["year"].astype(str), y=pbr_df["PBR"],
                mode="lines+markers+text",
                line=dict(color=COLOR["primary"], width=2),
                marker=dict(size=8),
                text=[f"{v:.2f}" for v in pbr_df["PBR"]],
                textposition="top center",
                name="PBR",
            ))
            fig_pbr.add_hline(y=1.0, line_dash="dot", line_color=COLOR["warning"],
                              annotation_text="PBR 1.0x")
            apply_layout(fig_pbr, "PBR 추이")
            fig_pbr.update_yaxes(ticksuffix="x")
            st.plotly_chart(fig_pbr, use_container_width=True)

    with col_c2:
        # ROE 추이
        roe_ts = pd.DataFrame({"year": years, "ROE": roe_vals}).dropna()
        if not roe_ts.empty:
            fig_roe = go.Figure()
            fig_roe.add_trace(go.Scatter(
                x=roe_ts["year"].astype(str), y=roe_ts["ROE"],
                mode="lines+markers+text",
                line=dict(color=COLOR["positive"], width=2),
                marker=dict(size=8),
                text=[f"{v:.1f}%" for v in roe_ts["ROE"]],
                textposition="top center",
                name="ROE",
            ))
            fig_roe.add_hline(y=8.0, line_dash="dot", line_color=COLOR["primary"],
                              annotation_text="ROE 8%")
            fig_roe.add_hline(y=0, line_dash="solid", line_color=COLOR["negative"], opacity=0.3)
            apply_layout(fig_roe, "ROE 추이")
            fig_roe.update_yaxes(ticksuffix="%")
            st.plotly_chart(fig_roe, use_container_width=True)

with chart_tab2:
    # 매출/영업이익/순이익
    income_df = pd.DataFrame({
        "year": years,
        "매출액": revenue_vals,
        "영업이익": op_income_vals,
        "당기순이익": net_income_vals,
    }).dropna(subset=["매출액"])

    if not income_df.empty:
        fig_income = go.Figure()
        colors = [COLOR["primary"], COLOR["positive"], COLOR["warning"]]
        for col_name, color in zip(["매출액", "영업이익", "당기순이익"], colors):
            if col_name in income_df.columns:
                fig_income.add_trace(go.Bar(
                    x=income_df["year"].astype(str),
                    y=income_df[col_name],
                    name=col_name,
                    marker_color=color,
                    opacity=0.85,
                ))
        apply_layout(fig_income, "매출·영업이익·순이익 (억원)")
        fig_income.update_layout(barmode="group", yaxis_title="억원")
        st.plotly_chart(fig_income, use_container_width=True)
    else:
        st.info("손익 데이터가 없습니다.")

st.divider()

# ──────────────────────────────────────────────
# 듀퐁 분석
# ──────────────────────────────────────────────
st.subheader("🧮 듀퐁 분석: ROE = 순이익률 × 자산회전율 × 레버리지")

dupont_years = []
net_margins = []
asset_turnovers = []
leverages = []
roe_calcs = []

for i, yr in enumerate(years):
    rev = revenue_vals[i] if i < len(revenue_vals) else None
    net = net_income_vals[i] if i < len(net_income_vals) else None
    if rev and net and rev > 0:
        nm = (net / rev) * 100
        net_margins.append(nm)
        dupont_years.append(str(yr))

if dupont_years and net_margins:
    fig_dp = go.Figure()
    fig_dp.add_trace(go.Bar(
        x=dupont_years, y=net_margins,
        name="순이익률 (%)",
        marker_color=COLOR["primary"],
    ))
    apply_layout(fig_dp, "순이익률 추이 (%)")
    fig_dp.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_dp, use_container_width=True)

with st.expander("듀퐁 공식 해설"):
    st.markdown(f"""
    **ROE = 순이익률 × 자산회전율 × 재무레버리지**

    | 요소 | 공식 | 의미 |
    |------|------|------|
    | 순이익률 | 당기순이익 / 매출액 | 매출 1원당 순이익 |
    | 자산회전율 | 매출액 / 총자산 | 자산 활용 효율 |
    | 재무레버리지 | 총자산 / 자기자본 | 부채 활용도 |

    > ROE가 높아도 **레버리지**가 원인이라면 재무 위험 동반 → 반드시 3요소 분해 필요
    """)

# ──────────────────────────────────────────────
# 최신 뉴스 (Brave Search)
# ──────────────────────────────────────────────
st.divider()
st.subheader(f"📰 {name} 최신 뉴스")

news_key = f"news_{ticker}"
if news_key not in st.session_state:
    st.session_state[news_key] = []

col_news_btn, col_news_period, _ = st.columns([1, 1, 2])
with col_news_btn:
    fetch_news = st.button("🔍 뉴스 검색", key=f"btn_news_{ticker}")
with col_news_period:
    news_period = st.selectbox(
        "기간",
        ["오늘", "1주", "1개월"],
        index=1,
        key=f"np_{ticker}",
        label_visibility="collapsed",
    )

if fetch_news:
    freshness = {"오늘": "pd", "1주": "pw", "1개월": "pm"}.get(news_period, "pw")
    with st.spinner(f"{name} 뉴스 검색 중 (최근 {news_period})..."):
        raw = brave_news(
            f"{name} 실적 OR 수주 OR 사업 OR 투자",
            count=10,
            freshness=freshness,
        )
        # 제목에 종목명이 없는 일반 증시 뉴스 제거
        filtered = [r for r in raw if name in r.get("title", "")]
        # 필터 후 결과가 너무 적으면 원본에서 보완 (최대 5개)
        if len(filtered) < 3:
            seen = {r["url"] for r in filtered}
            for r in raw:
                if r["url"] not in seen:
                    filtered.append(r)
                if len(filtered) >= 5:
                    break
        st.session_state[news_key] = filtered[:5]

news_results = st.session_state.get(news_key, [])
if news_results:
    st.caption(f"최근 {news_period} 뉴스 {len(news_results)}건")
    for r in news_results:
        age_str = r.get("age", "")
        src_str = r.get("source", "")
        desc = r.get("description", "")
        st.markdown(f"""
        <div style="padding:10px 0; border-bottom:1px solid {COLOR['border']};">
          <a href="{r['url']}" target="_blank"
             style="color:{COLOR['primary']}; font-weight:500; text-decoration:none; font-size:0.93rem; line-height:1.4;">
            {r['title']}
          </a>
          <div style="display:flex; gap:10px; margin-top:4px; font-size:0.75rem; color:#9ca3af;">
            {f'<span>🕐 {age_str}</span>' if age_str else ''}
            {f'<span>📰 {src_str}</span>' if src_str else ''}
          </div>
          {f'<div style="color:#6b7280; font-size:0.82rem; margin-top:4px;">{desc[:160]}</div>' if desc else ""}
        </div>
        """, unsafe_allow_html=True)
else:
    st.caption("버튼을 클릭하면 최신 뉴스를 검색합니다.")

# 기업 분석 페이지 링크
st.divider()
col_nav1, col_nav2 = st.columns(2)
with col_nav1:
    if st.button("📊 기술적 분석으로 이동", use_container_width=True):
        st.switch_page("pages/04_technical.py")
with col_nav2:
    if st.button("💰 절세 전략으로 이동", use_container_width=True):
        st.switch_page("pages/05_tax_guide.py")
