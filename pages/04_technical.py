"""기술적 분석 페이지."""

import sys
from pathlib import Path
from datetime import date, timedelta

import re

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_searchbox import st_searchbox

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.styles import inject_css, COLOR
from utils.charts import apply_layout
from data.cache import cached_ohlcv, cached_all_stocks
from pykrx import stock as krx_stock

st.set_page_config(page_title="기술적 분석", page_icon="📉", layout="wide")
inject_css()

st.title("📉 기술적 분석")
st.caption("캔들스틱 · 이동평균선 · RSI · MACD")

# ──────────────────────────────────────────────
# 종목 선택 (typeahead 자동완성)
# ──────────────────────────────────────────────
def _search_stocks_tech(q: str) -> list[str]:
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

col_s1, col_s2 = st.columns([2, 2])
with col_s1:
    selected_label = st_searchbox(
        _search_stocks_tech,
        key="tech_searchbox",
        placeholder="종목명 또는 6자리 코드 입력 (예: 삼성전자)",
        default=f"{st.session_state.selected_name} ({st.session_state.selected_ticker})",
        clear_on_submit=False,
        label="종목 검색",
    )

    if selected_label and isinstance(selected_label, str):
        m = re.search(r'\((\d{6}),', selected_label)
        if m:
            _t = m.group(1)
            _n = selected_label[:selected_label.rfind(f"({_t}")].strip()
            st.session_state.selected_ticker = _t
            st.session_state.selected_name = _n

with col_s2:
    period_options = {
        "1개월": 30, "3개월": 90, "6개월": 180, "1년": 365, "3년": 1095,
    }
    period_label = st.selectbox("기간", list(period_options.keys()), index=2)
    days = period_options[period_label]

ticker = st.session_state.selected_ticker
name = st.session_state.selected_name

if name and name != ticker:
    st.caption(f"선택 종목: **{name}** ({ticker})")

# ──────────────────────────────────────────────
# OHLCV 데이터 로드
# ──────────────────────────────────────────────
end_dt = date.today()
start_dt = end_dt - timedelta(days=days)

with st.spinner(f"{name} ({ticker}) OHLCV 불러오는 중..."):
    ohlcv = cached_ohlcv(ticker, start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"))

if ohlcv.empty:
    st.error(f"OHLCV 데이터를 불러올 수 없습니다. ({ticker})")
    st.stop()

ohlcv = ohlcv.sort_values("date").reset_index(drop=True)

# ──────────────────────────────────────────────
# 기술적 지표 계산
# ──────────────────────────────────────────────
# 이동평균
for n in [20, 60, 120]:
    ohlcv[f"MA{n}"] = ohlcv["close"].rolling(n).mean()

# RSI (14일)
def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

ohlcv["RSI"] = calc_rsi(ohlcv["close"])

# MACD (12, 26, 9)
ema12 = ohlcv["close"].ewm(span=12, adjust=False).mean()
ema26 = ohlcv["close"].ewm(span=26, adjust=False).mean()
ohlcv["MACD"] = ema12 - ema26
ohlcv["MACD_signal"] = ohlcv["MACD"].ewm(span=9, adjust=False).mean()
ohlcv["MACD_hist"] = ohlcv["MACD"] - ohlcv["MACD_signal"]

# 색상 (한국 컨벤션: 상승=빨강, 하락=파랑)
ohlcv["candle_color"] = ohlcv.apply(
    lambda r: COLOR["negative"] if r["close"] >= r["open"] else COLOR["primary"], axis=1
)

# ──────────────────────────────────────────────
# 차트 생성
# ──────────────────────────────────────────────
st.subheader(f"📊 {name} ({ticker}) — {period_label}")

# 요약 메트릭
latest = ohlcv.iloc[-1]
prev = ohlcv.iloc[-2] if len(ohlcv) > 1 else latest
price_chg = latest["close"] - prev["close"]
pct_chg = price_chg / prev["close"] * 100 if prev["close"] else 0

# 기간별 지표 (선택 기간에 따라 변동)
period_ret = (latest["close"] / ohlcv.iloc[0]["close"] - 1) * 100 if ohlcv.iloc[0]["close"] else 0
period_high = ohlcv["high"].max()
period_low = ohlcv["low"].min()
avg_vol = ohlcv["volume"].mean()

rsi_val = ohlcv["RSI"].dropna().iloc[-1] if not ohlcv["RSI"].dropna().empty else None
rsi_label = "과매수" if rsi_val and rsi_val > 70 else ("과매도" if rsi_val and rsi_val < 30 else "중립")

mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
with mc1:
    st.metric("현재가", f"{latest['close']:,}원",
              delta=f"{price_chg:+,.0f}원 ({pct_chg:+.2f}%)")
with mc2:
    st.metric(f"{period_label} 수익률", f"{period_ret:+.1f}%")
with mc3:
    st.metric(f"{period_label} 최고가", f"{period_high:,.0f}원")
with mc4:
    st.metric(f"{period_label} 최저가", f"{period_low:,.0f}원")
with mc5:
    st.metric("기간 평균 거래량", f"{avg_vol:,.0f}주")
with mc6:
    st.metric(f"RSI (14일)", f"{rsi_val:.1f}" if rsi_val else "N/A",
              delta=rsi_label, delta_color="off")

# 메인 차트: 캔들 + MA + 거래량
fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    row_heights=[0.6, 0.15, 0.25],
    vertical_spacing=0.02,
    subplot_titles=["주가 & 이동평균선", "거래량", "RSI"],
)

# 캔들스틱
fig.add_trace(go.Candlestick(
    x=ohlcv["date"], open=ohlcv["open"], high=ohlcv["high"],
    low=ohlcv["low"], close=ohlcv["close"],
    name="주가",
    increasing_line_color=COLOR["negative"],   # 상승: 빨강
    decreasing_line_color=COLOR["primary"],    # 하락: 파랑
    increasing_fillcolor=COLOR["negative"],
    decreasing_fillcolor=COLOR["primary"],
), row=1, col=1)

# 이동평균선
ma_colors = {20: COLOR["primary"], 60: COLOR["warning"], 120: COLOR["negative"]}
for n, color in ma_colors.items():
    fig.add_trace(go.Scatter(
        x=ohlcv["date"], y=ohlcv[f"MA{n}"],
        mode="lines", name=f"MA{n}",
        line=dict(color=color, width=1.2, dash="solid"),
    ), row=1, col=1)

# 거래량
vol_colors = ohlcv.apply(
    lambda r: COLOR["negative"] if r["close"] >= r["open"] else COLOR["primary"], axis=1
)
fig.add_trace(go.Bar(
    x=ohlcv["date"], y=ohlcv["volume"],
    name="거래량",
    marker_color=vol_colors,
    opacity=0.7,
    showlegend=False,
), row=2, col=1)

# RSI
fig.add_trace(go.Scatter(
    x=ohlcv["date"], y=ohlcv["RSI"],
    mode="lines", name="RSI",
    line=dict(color=COLOR["warning"], width=1.5),
), row=3, col=1)
fig.add_hline(y=70, line_dash="dot", line_color=COLOR["negative"], opacity=0.5, row=3, col=1)
fig.add_hline(y=30, line_dash="dot", line_color=COLOR["primary"], opacity=0.5, row=3, col=1)
fig.add_hrect(y0=30, y1=70, fillcolor="gray", opacity=0.05, row=3, col=1)

# 레이아웃
fig.update_layout(
    font=dict(family="Noto Sans KR, sans-serif", size=12, color="#111827"),
    plot_bgcolor="white", paper_bgcolor="white",
    xaxis_rangeslider_visible=False,
    height=700,
    legend=dict(
        orientation="v",
        x=1.02, y=0.98,
        xanchor="left", yanchor="top",
        bgcolor="rgba(255,255,255,0.92)",
        bordercolor="#e5e7eb",
        borderwidth=1,
    ),
    margin=dict(l=40, r=140, t=40, b=40),
    hoverlabel=dict(font_family="Noto Sans KR, sans-serif"),
)
for i in [1, 2, 3]:
    fig.update_xaxes(gridcolor="#f3f4f6", row=i, col=1)
    fig.update_yaxes(gridcolor="#f3f4f6", row=i, col=1)
fig.update_yaxes(title_text="주가 (원)", row=1, col=1)
fig.update_yaxes(title_text="거래량", row=2, col=1)
fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])

st.plotly_chart(fig, use_container_width=True)

st.divider()

# ──────────────────────────────────────────────
# MACD 차트
# ──────────────────────────────────────────────
st.subheader("MACD (12, 26, 9)")

fig_macd = make_subplots(rows=1, cols=1)
fig_macd.add_trace(go.Scatter(
    x=ohlcv["date"], y=ohlcv["MACD"],
    mode="lines", name="MACD",
    line=dict(color=COLOR["primary"], width=1.5),
))
fig_macd.add_trace(go.Scatter(
    x=ohlcv["date"], y=ohlcv["MACD_signal"],
    mode="lines", name="Signal",
    line=dict(color=COLOR["warning"], width=1.5),
))
hist_colors = ohlcv["MACD_hist"].apply(
    lambda v: COLOR["negative"] if v >= 0 else COLOR["primary"]
)
fig_macd.add_trace(go.Bar(
    x=ohlcv["date"], y=ohlcv["MACD_hist"],
    name="Histogram",
    marker_color=hist_colors,
    opacity=0.6,
))
fig_macd.add_hline(y=0, line_dash="solid", line_color=COLOR["border"])

apply_layout(fig_macd, "")
fig_macd.update_layout(height=280, legend=dict(orientation="h"))
st.plotly_chart(fig_macd, use_container_width=True)

with st.expander("기술적 지표 해설"):
    st.markdown("""
    | 지표 | 설정 | 해석 |
    |------|------|------|
    | MA20 | 20일 이동평균 | 단기 추세, 지지/저항 |
    | MA60 | 60일 이동평균 | 중기 추세 |
    | MA120 | 120일 이동평균 | 장기 추세 (반기선) |
    | RSI | 14일 기준 | >70: 과매수, <30: 과매도 |
    | MACD | (12, 26, 9) | 골든/데드크로스 매매 신호 |

    **한국 주식 차트 컨벤션**: 🔴 빨강 = 상승봉, 🔵 파랑 = 하락봉
    """)
