"""매크로 환경 분석 페이지."""

import re
import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.styles import inject_css, COLOR
from utils.charts import apply_layout
from utils.valuation import get_phase_label
from utils.brave_search import news_search
from data.cache import cached_us10y_yield, cached_exchange_rate_history, cached_all_stocks

st.set_page_config(page_title="매크로 환경", page_icon="🌍", layout="wide")
inject_css()

st.title("🌍 매크로 환경 분석")
st.caption("금리 · KOSPI PBR 분포 · 경기 국면 · AI 데이터센터 사이클")

# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
with st.spinner("데이터 불러오는 중..."):
    us10y = cached_us10y_yield(years=5)
    fx_history = cached_exchange_rate_history(years=3)
    kospi_stocks = cached_all_stocks("KOSPI")

# KOSPI PBR 계산 (전종목 데이터 기반)
valid_stocks = kospi_stocks.dropna(subset=["pbr"]).copy()
valid_stocks = valid_stocks[valid_stocks["pbr"] > 0]

kospi_pbr_median = valid_stocks["pbr"].median() if not valid_stocks.empty else None
kospi_pbr_mean = valid_stocks["pbr"].mean() if not valid_stocks.empty else None

# ──────────────────────────────────────────────
# 상단 지표 카드
# ──────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    if not us10y.empty:
        latest_yield = us10y["yield"].iloc[-1]
        prev_yield = us10y["yield"].iloc[-2] if len(us10y) > 1 else latest_yield
        st.metric("미국 10년 금리", f"{latest_yield:.2f}%",
                  delta=f"{latest_yield - prev_yield:+.2f}%p")
    else:
        st.metric("미국 10년 금리", "N/A")

with col2:
    if kospi_pbr_median:
        st.metric("KOSPI PBR 중위값", f"{kospi_pbr_median:.2f}x",
                  help="전 KOSPI 종목 PBR 중위값")
    else:
        st.metric("KOSPI PBR 중위값", "N/A")

with col3:
    if not fx_history.empty:
        latest_fx = fx_history["rate"].iloc[-1]
        prev_fx = fx_history["rate"].iloc[-2] if len(fx_history) > 1 else latest_fx
        st.metric("USD/KRW", f"{latest_fx:,.0f}원",
                  delta=f"{latest_fx - prev_fx:+.1f}원")
    else:
        st.metric("USD/KRW", "N/A")

with col4:
    if not us10y.empty and len(us10y) >= 20:
        recent = us10y["yield"].tail(20)
        rate_dir = "up" if recent.iloc[-1] > recent.iloc[0] else "down"
        rate_label = "↑ 상승" if rate_dir == "up" else "↓ 하락"
        st.metric("금리 방향 (20일)", rate_label,
                  help="매크로 환경 페이지 하단에서 EPS 방향까지 설정하면 경기 국면 판단")
    else:
        st.metric("금리 방향", "N/A")

st.divider()

# ──────────────────────────────────────────────
# 미국 10년 국채 금리 차트
# ──────────────────────────────────────────────
st.subheader("📈 미국 10년 국채 금리 추이")

if not us10y.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=us10y["date"], y=us10y["yield"],
        mode="lines", name="미국 10년 금리",
        line=dict(color=COLOR["primary"], width=2),
        fill="tozeroy",
        fillcolor="rgba(47,100,227,0.1)",
    ))
    for level, label in [(4.0, "4.0%"), (5.0, "5.0%")]:
        fig.add_hline(y=level, line_dash="dot", line_color=COLOR["warning"], opacity=0.7,
                      annotation_text=label, annotation_position="right")
    apply_layout(fig, "")
    fig.update_yaxes(title_text="금리 (%)", ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("금리 데이터를 불러올 수 없습니다.")

st.divider()

# ──────────────────────────────────────────────
# KOSPI PBR 현재 분포
# ──────────────────────────────────────────────
st.subheader("📊 KOSPI PBR 현재 분포")

if not valid_stocks.empty:
    col_chart, col_stats = st.columns([2, 1])

    with col_chart:
        # PBR 분포 히스토그램
        pbr_clipped = valid_stocks["pbr"].clip(0, 5)
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=pbr_clipped, nbinsx=60,
            marker_color=COLOR["primary"], opacity=0.75,
            name="종목 수",
        ))
        # 기준선
        for val, label, color in [
            (0.8, "0.8x", COLOR["positive"]),
            (1.0, "1.0x", COLOR["warning"]),
            (1.2, "1.2x", COLOR["text_muted"]),
        ]:
            fig_hist.add_vline(x=val, line_dash="dash", line_color=color, opacity=0.8,
                               annotation_text=label, annotation_position="top")
        # 중위값 표시
        if kospi_pbr_median:
            fig_hist.add_vline(x=kospi_pbr_median, line_dash="solid",
                               line_color=COLOR["negative"], line_width=2,
                               annotation_text=f"중위 {kospi_pbr_median:.2f}x",
                               annotation_position="top right")
        apply_layout(fig_hist, "")
        fig_hist.update_layout(
            xaxis_title="PBR (배)",
            yaxis_title="종목 수",
            height=320,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_stats:
        # PBR 구간별 종목 비율
        pbr = valid_stocks["pbr"]
        n_total = len(pbr)
        bands = [
            ("PBR < 0.8x", pbr < 0.8, COLOR["positive"]),
            ("0.8 ~ 1.0x", (pbr >= 0.8) & (pbr < 1.0), COLOR["primary"]),
            ("1.0 ~ 1.2x", (pbr >= 1.0) & (pbr < 1.2), COLOR["text_muted"]),
            ("1.2x 초과", pbr >= 1.2, COLOR["negative"]),
        ]

        st.markdown("**구간별 종목 비율**")
        for label, mask, color in bands:
            n = mask.sum()
            pct = n / n_total * 100
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center;
                        padding:6px 0; border-bottom:1px solid {COLOR['border']};">
              <span style="color:{color}; font-weight:500;">{label}</span>
              <span><b>{n}</b>종목 ({pct:.0f}%)</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:12px; padding:10px; background:#f8f9fa; border-radius:8px;
                    font-size:0.85rem;">
          <b>중위값:</b> {kospi_pbr_median:.2f}x<br>
          <b>평균:</b> {kospi_pbr_mean:.2f}x<br>
          <b>분석 종목:</b> {n_total:,}개
        </div>
        """, unsafe_allow_html=True)

    # 역사적 참고 레벨
    st.markdown("""
    | PBR 레벨 | 의미 |
    |----------|------|
    | **< 0.8x** | 역사적 저점 구간 (위기 시 수준) |
    | **0.8 ~ 1.0x** | 저평가 구간 |
    | **1.0 ~ 1.2x** | 적정 구간 |
    | **> 1.2x** | 고평가 신호 |
    """)
else:
    st.warning("PBR 데이터를 불러올 수 없습니다.")

st.divider()

# ──────────────────────────────────────────────
# 경기 국면 판단
# ──────────────────────────────────────────────
st.subheader("🔄 경기 국면 판단")
st.caption("금리 방향 + EPS 추정치 방향으로 현재 국면 판단")

col_rate, col_eps = st.columns(2)
with col_rate:
    rate_dir = st.radio("금리 방향", ["down", "flat", "up"],
                        format_func=lambda x: {"down": "↓ 하락", "flat": "→ 보합", "up": "↑ 상승"}[x],
                        index=0, horizontal=True)
with col_eps:
    eps_dir = st.radio("EPS 추정치 방향", ["up", "flat", "down"],
                       format_func=lambda x: {"up": "↑ 상향", "flat": "→ 보합", "down": "↓ 하향"}[x],
                       index=0, horizontal=True)

phase = get_phase_label(rate_dir, eps_dir)

phase_color_map = {
    "금융장세": COLOR["positive"],
    "실적장세": COLOR["primary"],
    "역금융장세": COLOR["warning"],
    "역실적장세": COLOR["negative"],
}
phase_color = phase_color_map.get(phase["phase"], COLOR["text_muted"])

st.markdown(f"""
<div style="background:{phase_color}15; border-left:4px solid {phase_color};
            padding:16px 20px; border-radius:8px; margin:12px 0;">
  <h3 style="color:{phase_color}; margin:0 0 8px 0;">{phase['label']}</h3>
  <p style="margin:0 0 8px 0;"><strong>전략:</strong> {phase['strategy']}</p>
  <p style="margin:0;"><strong>유리한 섹터:</strong> {' · '.join(phase['favorable_sectors'])}</p>
</div>
""", unsafe_allow_html=True)

with st.expander("4국면 가이드"):
    st.markdown("""
    | 국면 | 금리 | EPS | 전략 | 유리 섹터 |
    |------|------|-----|------|-----------|
    | 📈 금융장세 | ↓ | ↑ | 저PBR 반등 매수 | 건설, 금융, 저PBR 가치주 |
    | 🚀 실적장세 | ↑ | ↑ | 실적 주도주 유지 | IT, 반도체, 자동차, 방산 |
    | ⚠️ 역금융장세 | ↑ | ↓ | 방어주 비중 확대 | 유틸리티, 헬스케어, 통신 |
    | 🔴 역실적장세 | ↓ | ↓ | 현금 비중 최대화 | 현금, 채권, 금 |
    """)

st.divider()

# ──────────────────────────────────────────────
# AI 데이터센터 사이클 분석
# ──────────────────────────────────────────────
st.subheader("🤖 AI 데이터센터 투자 사이클 분석")
st.caption("최신 뉴스 검색 기반 자동 신호 판단")

SEARCH_TOPICS = {
    "빅테크 AI 투자": "빅테크 구글 마이크로소프트 메타 아마존 AI 데이터센터 투자 Capex",
    "반도체 수출": "한국 반도체 수출 HBM 메모리",
    "전력기기 수주": "변압기 전력기기 데이터센터 수주 한국전력기기",
    "데이터센터 전력 수요": "데이터센터 전력 전기 수요 한국",
}

POSITIVE_KEYWORDS = [
    "증가", "확대", "수주", "호조", "급증", "상향", "성장", "기대",
    "투자", "계획", "확정", "역대", "최고", "개선", "최대", "수혜",
    "공급", "증설", "계약", "선정",
]
NEGATIVE_KEYWORDS = [
    "감소", "축소", "취소", "불확실", "우려", "둔화", "하락",
    "하향", "부진", "위축", "감축", "연기", "급락", "감소",
]


def _age_to_hours(age_str: str) -> float:
    """Brave 'age' 문자열 → 시간(float) 변환. 정렬용."""
    if not age_str:
        return float("inf")
    s = age_str.lower()
    m = re.search(r"(\d+)\s*(min|hour|day|week|month)", s)
    if not m:
        return float("inf")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"min": 1/60, "hour": 1, "day": 24, "week": 168, "month": 720}[unit]


def _sort_by_latest(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: _age_to_hours(r.get("age", "")))


def _score_signal(results: list[dict]) -> tuple[str, str]:
    pos, neg = 0, 0
    for r in results:
        text = r.get("title", "") + " " + r.get("description", "")
        pos += sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
        neg += sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos == 0 and neg == 0:
        return "neutral", "🟡"
    if pos > neg * 1.3:
        return "positive", "🟢"
    if neg > pos * 1.3:
        return "negative", "🔴"
    return "neutral", "🟡"


if "ai_cycle_results" not in st.session_state:
    st.session_state.ai_cycle_results = {}
if "ai_cycle_fetched_at" not in st.session_state:
    st.session_state.ai_cycle_fetched_at = ""

col_btn, col_info = st.columns([1, 3])
with col_btn:
    fetch_clicked = st.button("🔍 최신 뉴스 수집 및 분석", type="primary")
with col_info:
    if st.session_state.ai_cycle_fetched_at:
        st.caption(f"수집 시각: {st.session_state.ai_cycle_fetched_at}")

if fetch_clicked:
    with st.spinner("최신 뉴스 수집 중 (Brave Search, 최근 1개월 기준)..."):
        for topic, query in SEARCH_TOPICS.items():
            # 뉴스 전용 엔드포인트 + 1개월 이내 기사만
            st.session_state.ai_cycle_results[topic] = news_search(query, count=5, freshness="pm")
        st.session_state.ai_cycle_fetched_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

results_data = st.session_state.ai_cycle_results

if results_data:
    signals = {}
    for topic in SEARCH_TOPICS:
        res = results_data.get(topic, [])
        signal, icon = _score_signal(res)
        signals[topic] = (signal, icon, res)

    pos_count = sum(1 for s, _, _ in signals.values() if s == "positive")
    neg_count = sum(1 for s, _, _ in signals.values() if s == "negative")
    total = len(signals)

    if pos_count >= 3:
        overall_color = COLOR["positive"]
        overall_text = "AI 사이클 강세 — 전력기기·반도체·AI 인프라 관련주 주목"
        overall_icon = "🚀"
    elif neg_count >= 3:
        overall_color = COLOR["negative"]
        overall_text = "AI 사이클 둔화 신호 — 보수적 접근 권고"
        overall_icon = "⚠️"
    elif pos_count >= 2:
        overall_color = COLOR["warning"]
        overall_text = "AI 사이클 진행 중 — 선별적 접근"
        overall_icon = "📊"
    else:
        overall_color = COLOR["text_muted"]
        overall_text = "혼재된 신호 — 추이 모니터링 필요"
        overall_icon = "🔎"

    st.markdown(f"""
    <div style="background:{overall_color}18; border:2px solid {overall_color};
                padding:14px 20px; border-radius:10px; margin-bottom:16px;">
      <span style="font-size:1.2rem; font-weight:700; color:{overall_color};">
        {overall_icon} 종합 판단: {overall_text}
      </span>
      <div style="color:#6b7280; font-size:0.85rem; margin-top:4px;">
        긍정 신호 {pos_count}/{total} · 부정 신호 {neg_count}/{total} &nbsp;|&nbsp; 최근 1개월 뉴스 기준
      </div>
    </div>
    """, unsafe_allow_html=True)

    for topic, (signal, icon, res) in signals.items():
        sig_label = {"positive": "긍정적", "negative": "부정적", "neutral": "중립"}.get(signal, "중립")
        with st.expander(f"{icon} **{topic}** — {sig_label} ({len(res)}건)"):
            if res:
                for r in _sort_by_latest(res)[:5]:
                    age_str = r.get("age", "")
                    src_str = r.get("source", "")
                    st.markdown(f"""
                    <div style="padding:8px 0; border-bottom:1px solid {COLOR['border']};">
                      <a href="{r['url']}" target="_blank"
                         style="color:{COLOR['primary']}; font-weight:500; text-decoration:none; line-height:1.4;">
                        {r['title']}
                      </a>
                      <div style="display:flex; gap:8px; margin-top:3px; font-size:0.75rem; color:#9ca3af;">
                        {f'<span>🕐 {age_str}</span>' if age_str else ''}
                        {f'<span>📰 {src_str}</span>' if src_str else ''}
                      </div>
                      {f'<div style="color:#6b7280; font-size:0.82rem; margin-top:4px;">{r.get("description","")[:120]}</div>' if r.get("description") else ""}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("최근 1개월 내 관련 뉴스 없음")
else:
    st.info("위 버튼을 클릭하면 최신 뉴스(최근 1개월)를 수집하여 AI 사이클 신호를 분석합니다.")
