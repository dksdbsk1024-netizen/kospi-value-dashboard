import streamlit as st
from utils.styles import inject_css, COLOR
from utils.video_analyzer import extract_video_id, analyze_video

inject_css()

st.title("🎬 영상 분석")
st.caption("YouTube 영상을 분석하여 전체 요약, 핵심 장면, 키워드를 추출합니다.")

MAX_DURATION = 90 * 60  # 90분 (초)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_analyze(url: str, anthropic_key: str, openai_key: str) -> dict:
    return analyze_video(url, anthropic_key, openai_key)


url = st.text_input("YouTube URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if st.button("분석 시작", type="primary", disabled=not bool(url)):
    video_id = extract_video_id(url)
    if not video_id:
        st.error("올바른 YouTube URL을 입력해주세요.")
        st.stop()

    try:
        anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
        openai_key = st.secrets["OPENAI_API_KEY"]
    except KeyError as e:
        st.error(f"secrets.toml에 {e} 키가 없습니다. .streamlit/secrets.toml을 확인하세요.")
        st.stop()

    try:
        with st.spinner("영상 분석 중... (자막 추출 → Claude 분석, 최대 2~3분 소요)"):
            result = _cached_analyze(url, anthropic_key, openai_key)
    except Exception as e:
        err = str(e)
        if "private" in err.lower() or "unavailable" in err.lower():
            st.error("비공개 또는 접근할 수 없는 영상입니다.")
        elif "whisper" in err.lower() or "audio" in err.lower():
            st.error("음성 인식에 실패했습니다. 다른 영상을 시도하거나 잠시 후 재시도하세요.")
        else:
            st.error(f"분석 중 오류가 발생했습니다: {e}")
        st.stop()

    meta = result["meta"]
    source_label = "자동자막" if result["source"] == "captions" else "Whisper 음성인식"
    duration_min = meta["duration"] // 60

    if meta["duration"] > MAX_DURATION:
        st.warning(f"⚠️ 영상 길이가 {duration_min}분으로 90분을 초과합니다. 결과가 불완전할 수 있습니다.")

    st.markdown(
        f"**{meta['title']}** · {meta['channel']} · {duration_min}분 · 자막 출처: `{source_label}`"
    )
    st.divider()

    tab1, tab2, tab3 = st.tabs(["📋 전체 요약", "🕐 핵심 장면", "🔑 키워드 분석"])

    with tab1:
        st.markdown(result["summary"])

    with tab2:
        for moment in result.get("key_moments", []):
            st.markdown(
                f"`{moment['timestamp']}` &nbsp; {moment['description']}",
                unsafe_allow_html=True,
            )

    with tab3:
        keywords = result.get("keywords", [])
        if not keywords:
            st.info("추출된 키워드가 없습니다.")
        else:
            keyword_names = [k["keyword"] for k in keywords]
            selected = st.radio(
                "키워드 선택",
                keyword_names,
                horizontal=True,
                label_visibility="collapsed",
            )
            kw_data = next(k for k in keywords if k["keyword"] == selected)

            st.markdown(
                f'<span class="badge" style="background:{COLOR["primary_light"]};color:{COLOR["primary_dark"]};">'
                f'{kw_data["keyword"]}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(kw_data["summary"])

            if kw_data.get("timestamps"):
                ts_str = " · ".join(f"`{t}`" for t in kw_data["timestamps"])
                st.markdown(f"**등장 시점:** {ts_str}")
