import streamlit as st

COLOR = {
    "primary":       "#2F64E3",
    "primary_light": "#e8f0fd",
    "primary_dark":  "#1a3fa0",
    "positive":      "#10b981",
    "warning":       "#f59e0b",
    "negative":      "#ef4444",
    "bg_surface":    "#f8f9fa",
    "bg_card":       "#ffffff",
    "text_primary":  "#111827",
    "text_muted":    "#6b7280",
    "border":        "#e5e7eb",
}


def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Noto Sans KR', sans-serif !important;
        }

        .metric-value {
            font-variant-numeric: tabular-nums;
        }

        /* 사이드바 */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
        }

        /* 버튼 */
        .stButton > button {
            font-family: 'Noto Sans KR', sans-serif !important;
            border-radius: 6px;
        }

        /* 뱃지 공통 */
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
            font-family: 'Noto Sans KR', sans-serif;
        }

        /* 테이블 헤더 */
        thead tr th {
            background-color: #f8f9fa !important;
            color: #6b7280 !important;
            font-weight: 500 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_badge_html(label: str, color_key: str) -> str:
    """판단 뱃지 HTML 반환. color_key는 COLOR 딕셔너리 키."""
    bg_map = {
        "primary":   (COLOR["primary_light"], COLOR["primary_dark"]),
        "positive":  ("#d1fae5", "#065f46"),
        "warning":   ("#fef3c7", "#92400e"),
        "negative":  ("#fee2e2", "#991b1b"),
        "text_muted": ("#f3f4f6", "#374151"),
    }
    bg, text = bg_map.get(color_key, ("#f3f4f6", "#374151"))
    return (
        f'<span class="badge" style="background:{bg};color:{text};">{label}</span>'
    )


def style_pbr(val):
    """pandas Styler용 — PBR 컬럼 파란색 강조."""
    try:
        return f"color: {COLOR['primary']}; font-weight: 500;"
    except Exception:
        return ""


def style_roe(val):
    """pandas Styler용 — ROE 양수=초록, 음수=빨간."""
    try:
        v = float(val)
        color = COLOR["positive"] if v >= 0 else COLOR["negative"]
        return f"color: {color}; font-weight: 500;"
    except Exception:
        return ""
