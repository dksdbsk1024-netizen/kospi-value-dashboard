"""KOSPI 가치주 발굴 대시보드 — 홈 (진입점).

국민대학교 비즈니스IT대학원 증권시장분석 기말 프로젝트.
PBR × ROE 중심의 저평가 우량주 발굴 Streamlit 앱.
"""

import sys
from pathlib import Path
from datetime import date, datetime

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from utils.styles import inject_css, COLOR
from utils.valuation import get_investment_signal
from data.cache import cached_all_stocks, cached_market_phase

st.set_page_config(
    page_title="KOSPI 가치주 발굴 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ──────────────────────────────────────────────
# 사이드바 네비게이션
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="padding:12px 0 8px;">
      <div style="font-size:1.1rem; font-weight:700; color:{COLOR['primary']};">
        📊 KOSPI 가치주 발굴
      </div>
      <div style="font-size:0.8rem; color:#6b7280; margin-top:2px;">
        국민대학교 비즈니스IT대학원
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown("**페이지 이동**")
    pages = {
        "🏠 홈 대시보드": None,
        "🌍 매크로 환경": "pages/01_macro.py",
        "🔍 종목 스크리너": "pages/02_screener.py",
        "🏢 기업 분석": "pages/03_company.py",
        "📉 기술적 분석": "pages/04_technical.py",
        "💰 절세 전략": "pages/05_tax_guide.py",
    }

    for label, path in pages.items():
        if path:
            if st.button(label, use_container_width=True, key=f"nav_{label}"):
                st.switch_page(path)
        else:
            st.markdown(f"""
            <div style="background:{COLOR['primary_light']}; color:{COLOR['primary_dark']};
                        padding:6px 12px; border-radius:6px; font-weight:500; font-size:0.9rem;
                        margin-bottom:4px;">
              {label}
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.caption(f"데이터 기준: {date.today().strftime('%Y-%m-%d')}")

# ──────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────
st.markdown(f"""
<div style="padding: 24px 0 16px;">
  <h1 style="margin:0; font-size:1.8rem; color:{COLOR['text_primary']};">
    📊 KOSPI 가치주 발굴 대시보드
  </h1>
  <p style="margin:6px 0 0; color:{COLOR['text_muted']}; font-size:0.95rem;">
    PBR × ROE 기반 저평가 우량주 스크리닝 &nbsp;|&nbsp;
    국민대학교 비즈니스IT대학원 증권시장분석 기말 프로젝트
  </p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────
with st.spinner("시장 데이터 불러오는 중..."):
    all_df = cached_all_stocks("KOSPI")

# ──────────────────────────────────────────────
# 상단 4개 Metric 카드
# ──────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

valid_df = all_df.dropna(subset=["pbr", "roe"]).copy()
valid_df = valid_df[valid_df["pbr"] > 0]

with col1:
    # KOSPI PBR: Σ시총 / Σ장부가 (지수 공식)
    index_base = valid_df[(valid_df["pbr"] > 0) & valid_df["marcap"].notna() & (~valid_df["is_etf"])]
    if not index_base.empty:
        total_mc = index_base["marcap"].sum()
        total_bv = (index_base["marcap"] / index_base["pbr"]).sum()
        kospi_pbr_idx = total_mc / total_bv if total_bv > 0 else None
        st.metric(
            "KOSPI PBR (시총 기반)",
            f"{kospi_pbr_idx:.2f}x" if kospi_pbr_idx else "N/A",
            help="Σ시가총액 / Σ장부가 — Naver 당일 데이터 기반",
        )
    else:
        st.metric("KOSPI 평균 PBR", "N/A")

with col2:
    # 저평가 종목 수
    n_value = len(valid_df[(valid_df.pbr <= 1.0) & (valid_df.roe >= 15)])
    n_total = len(valid_df)
    st.metric("저평가 우량 종목", f"{n_value}개",
              delta=f"전체 {n_total}개 중",
              help="PBR ≤ 1.0 & ROE ≥ 15%")

with col3:
    # KOSPI 평균 ROE
    avg_roe = valid_df["roe"].mean() if not valid_df.empty else None
    st.metric("KOSPI 평균 ROE", f"{avg_roe:.1f}%" if avg_roe else "N/A",
              help="스크리닝 대상 전종목 평균 ROE")

with col4:
    phase_data = cached_market_phase()
    primary = phase_data["primary"]
    ref = phase_data["reference"]
    kr_rate = phase_data.get("kr_rate")
    kr_spread = phase_data.get("kr_spread")
    st.metric(
        "현재 경기 국면 (한국 기준)",
        primary["label"],
        delta=(f"한국금리 {primary['rate_dir']} · 스프레드 {primary['spread_dir']}"
               if primary.get("rate_dir") else None),
        help=primary["description"],
    )
    with st.expander("🇺🇸 미국 기준 참고"):
        us_rate = phase_data.get("us_rate")
        us_spread = phase_data.get("us_spread")
        st.markdown(
            f"**{ref['label']}**  \n"
            f"{ref['description']}  \n"
            + (f"미국 10년 금리: **{us_rate:.2f}%** · T10Y2Y 스프레드: **{us_spread:.2f}%p**"
               if us_rate is not None else "미국 금리 데이터 없음")
        )
        if kr_rate is not None:
            st.caption(
                f"한국 10년 국고채: {kr_rate:.2f}% · 장단기 스프레드: "
                + (f"{kr_spread:.2f}%p" if kr_spread is not None else "N/A")
            )

st.divider()

# ──────────────────────────────────────────────
# 핵심 투자 철학 안내
# ──────────────────────────────────────────────
col_phi1, col_phi2 = st.columns([3, 2])

with col_phi1:
    st.subheader("🎯 핵심 투자 철학")
    st.markdown(f"""
    <div style="background:#f0f5ff; border-radius:12px; padding:20px;">
      <div style="font-size:1.5rem; font-weight:700; color:{COLOR['primary']};
                  text-align:center; padding:16px 0; letter-spacing:0.05em;">
        PBR = PER × ROE
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:8px;">
        <div style="background:white; border-radius:8px; padding:12px; text-align:center;
                    border:2px solid {COLOR['primary']};">
          <div style="font-size:0.8rem; color:#6b7280;">🔵 저평가 우량 (목표)</div>
          <div style="font-weight:600; margin-top:4px;">PBR ≤ 1 & ROE ≥ 15%</div>
        </div>
        <div style="background:white; border-radius:8px; padding:12px; text-align:center;
                    border:2px solid {COLOR['warning']};">
          <div style="font-size:0.8rem; color:#6b7280;">🟡 가치함정 (주의)</div>
          <div style="font-weight:600; margin-top:4px;">PBR ≤ 1 & ROE 낮음</div>
        </div>
      </div>
      <div style="margin-top:12px; font-size:0.85rem; color:#374151;">
        ⚠️ <strong>PBR 단독 판단 금지</strong> — 반드시 ROE와 함께 해석
      </div>
    </div>
    """, unsafe_allow_html=True)

with col_phi2:
    st.subheader("📌 이용 가이드")
    st.markdown("""
    | 단계 | 페이지 | 목적 |
    |------|--------|------|
    | 1 | 🌍 매크로 환경 | 금리·국면 파악 |
    | 2 | 🔍 종목 스크리너 | 저평가 종목 발굴 |
    | 3 | 🏢 기업 분석 | 개별 종목 심층 분석 |
    | 4 | 📉 기술적 분석 | 매매 시점 판단 |
    | 5 | 💰 절세 전략 | 절세계좌 최적화 |
    """)

st.divider()

# ──────────────────────────────────────────────
# 오늘의 주목 종목 (저PBR + 고ROE 상위 5)
# ──────────────────────────────────────────────
st.subheader("⭐ 오늘의 주목 종목 (저PBR + 고ROE 스크리닝 자동 선정)")

if not valid_df.empty:
    top_stocks = (
        valid_df[(valid_df.pbr > 0) & (valid_df.pbr <= 1.2) & (valid_df.roe >= 15)]
        .sort_values("pbr", ascending=True)
        .head(5)
    )

    if not top_stocks.empty:
        cols = st.columns(len(top_stocks))
        for i, (_, row) in enumerate(top_stocks.iterrows()):
            sig = get_investment_signal(row["pbr"], row["roe"])
            with cols[i]:
                st.markdown(f"""
                <div style="background:white; border:1px solid {COLOR['border']};
                            border-top:3px solid {sig['color']};
                            border-radius:8px; padding:14px; text-align:center;">
                  <div style="font-size:0.8rem; color:#6b7280;">{row['ticker']}</div>
                  <div style="font-size:1rem; font-weight:700; margin:4px 0;">{row['name']}</div>
                  <div style="display:flex; justify-content:space-between; margin-top:8px;
                              font-size:0.85rem;">
                    <span>PBR <b style="color:{COLOR['primary']}">{row['pbr']:.2f}x</b></span>
                    <span>ROE <b style="color:{COLOR['positive']}">{row['roe']:.1f}%</b></span>
                  </div>
                  <div style="margin-top:8px;">
                    <span style="background:{sig['color']}; color:white; padding:2px 8px;
                                 border-radius:10px; font-size:0.75rem;">{sig['label']}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("현재 조건(PBR≤1.2, ROE≥15%)에 해당하는 종목이 없습니다.")

else:
    st.warning("데이터를 불러올 수 없습니다.")

st.divider()

# 스크리너 바로가기
if st.button("🔍 전체 스크리너 보기", type="primary", use_container_width=False):
    st.switch_page("pages/02_screener.py")
