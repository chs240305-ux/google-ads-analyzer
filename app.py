import streamlit as st
import os
import subprocess
import sys


@st.cache_resource(show_spinner=False)
def _ensure_playwright_chromium():
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, capture_output=True,
        )
    except Exception:
        pass


_ensure_playwright_chromium()

from utils.transcript import extract_video_id, get_transcript, format_timestamp, get_full_text
from utils.video import get_video_info, format_view_count, format_upload_date
from utils.transparency import is_transparency_url, extract_youtube_from_transparency
from utils.gemini_analysis import analyze_from_youtube_url, analyze_with_file_bytes

st.set_page_config(
    page_title="광고 영상 분석기",
    page_icon="▶",
    layout="wide",
)

st.markdown("""
<style>
.main-title { font-size: 2rem; font-weight: 800; color: #FF0000; margin-bottom: 0.2rem; }
.subtitle { font-size: 0.95rem; color: #AAAAAA; margin-bottom: 1.5rem; }
.transcript-line {
    padding: 8px 12px; margin: 4px 0;
    border-left: 3px solid #FF0000;
    background: #1E1E1E; border-radius: 0 6px 6px 0; font-size: 0.95rem;
}
.timestamp-badge { color: #FF6B6B; font-size: 0.8rem; font-weight: 600; margin-right: 8px; font-family: monospace; }
.full-text-box {
    background: #1A1A2E; border: 1px solid #333; border-radius: 8px;
    padding: 16px; font-size: 0.95rem; line-height: 1.8; white-space: pre-wrap;
    max-height: 400px; overflow-y: auto;
}
.section-header {
    font-size: 1.1rem; font-weight: 700; color: #FFFFFF;
    padding: 8px 0; border-bottom: 2px solid #FF0000; margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ── 세션 상태 초기화 ──────────────────────────────────────────────
for key, default in [
    ("analyzed", False),
    ("video_id", None),
    ("youtube_url", None),
    ("info", None),
    ("last_url", None),
    ("gemini_result", None),
    ("gemini_error", None),
    ("gemini_auto_pending", False),
    ("transcript", None),
    ("transcript_source", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _get_gemini_api_key() -> str:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


def _get_cobalt_token() -> str:
    try:
        return st.secrets.get("COBALT_API_TOKEN", "")
    except Exception:
        return os.environ.get("COBALT_API_TOKEN", "")


# ── 헤더 ─────────────────────────────────────────────────────────
st.markdown('<div class="main-title">▶ 광고 영상 분석기</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Google 광고 투명성 센터 또는 YouTube URL을 입력하면 자막과 AI 영상 분석을 자동으로 제공합니다</div>',
    unsafe_allow_html=True,
)

url_input = st.text_input(
    label="URL 입력",
    placeholder="YouTube URL 또는 Google 광고 투명성 센터 URL을 붙여넣으세요",
    label_visibility="collapsed",
)

col_btn, col_tip = st.columns([1, 4])
with col_btn:
    analyze_btn = st.button("분석 시작", type="primary", use_container_width=True)
with col_tip:
    st.caption("YouTube Shorts / 일반 영상 | Google 광고 투명성 센터(adstransparency.google.com) URL 지원")

st.divider()

# ── 분석 버튼 처리 ────────────────────────────────────────────────
if analyze_btn and url_input:
    if st.session_state.last_url != url_input:
        st.session_state.gemini_result = None
        st.session_state.gemini_error = None

    youtube_url = url_input
    if is_transparency_url(url_input):
        with st.spinner("Google 광고 투명성 센터에서 YouTube 링크를 추출하는 중... (약 10~20초)"):
            extracted, extract_msg = extract_youtube_from_transparency(url_input)
        if extracted:
            st.success(f"YouTube 링크 추출 완료: `{extracted}`")
            youtube_url = extracted
        else:
            st.error(f"YouTube 링크 추출 실패: {extract_msg}")
            st.stop()

    video_id = extract_video_id(youtube_url)
    if not video_id:
        st.error("올바른 YouTube URL 또는 Google 광고 투명성 센터 URL을 입력해주세요.")
        st.stop()

    with st.spinner("영상 정보 및 자막 로딩 중..."):
        info = get_video_info(youtube_url)
        if info is None:
            st.error("영상 정보를 불러올 수 없습니다. URL을 다시 확인해주세요.")
            st.stop()
        transcript, transcript_source = get_transcript(video_id)

    st.session_state.analyzed = True
    st.session_state.video_id = video_id
    st.session_state.youtube_url = youtube_url
    st.session_state.info = info
    st.session_state.last_url = url_input
    st.session_state.transcript = transcript
    st.session_state.transcript_source = transcript_source
    st.session_state.gemini_auto_pending = True  # AI 분석 자동 시작

elif analyze_btn and not url_input:
    st.warning("YouTube URL을 입력해주세요.")

# ── 결과 렌더링 ───────────────────────────────────────────────────
if st.session_state.analyzed:
    info = st.session_state.info
    video_id = st.session_state.video_id
    youtube_url = st.session_state.youtube_url
    transcript = st.session_state.transcript
    transcript_source = st.session_state.transcript_source

    # 영상 정보
    with st.container():
        c1, c2 = st.columns([1, 3])
        with c1:
            if info["thumbnail"]:
                st.image(info["thumbnail"], use_container_width=True)
        with c2:
            st.markdown(f"### {info['title']}")
            st.markdown(f"**채널:** {info['channel']}")
            duration_min = info["duration"] // 60
            duration_sec = info["duration"] % 60
            st.markdown(f"**길이:** {duration_min:02d}:{duration_sec:02d}")
            if info["view_count"]:
                st.markdown(f"**조회수:** {format_view_count(info['view_count'])}회")
            if info["upload_date"]:
                st.markdown(f"**업로드:** {format_upload_date(info['upload_date'])}")

    st.divider()

    # ── 분할 뷰: 자막 | AI 분석 ──────────────────────────────────
    left_col, right_col = st.columns(2, gap="large")

    # ── 왼쪽: 자막 / 대본 ────────────────────────────────────────
    with left_col:
        st.markdown('<div class="section-header">📝 자막 / 대본</div>', unsafe_allow_html=True)

        if transcript:
            st.success(f"자막 {len(transcript)}개 항목 · {transcript_source}")
            st.caption(
                "※ 음성 기반 시스템 자막입니다. 편집으로 삽입된 후킹문구·CTA·화면 고정 텍스트 등은 "
                "우측 AI 분석 **1. 화면 텍스트 & 편집 자막** 항목에서 확인하세요."
            )

            full_text = get_full_text(transcript)
            st.markdown(f'<div class="full-text-box">{full_text}</div>', unsafe_allow_html=True)

            with st.expander("타임스탬프별 자막 보기"):
                for item in transcript:
                    ts = format_timestamp(item["start"])
                    text = item["text"].replace("\n", " ")
                    st.markdown(
                        f'<div class="transcript-line">'
                        f'<span class="timestamp-badge">[{ts}]</span>{text}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            transcript_export = "\n".join(
                f"[{format_timestamp(item['start'])}] {item['text'].replace(chr(10), ' ')}"
                for item in transcript
            )
            st.download_button(
                label="자막 다운로드 (.txt)",
                data=transcript_export,
                file_name=f"{video_id}_transcript.txt",
                mime="text/plain",
            )
        else:
            st.warning(f"자막 없음: {transcript_source}")
            if any(kw in str(transcript_source) for kw in ["IP", "cloud", "blocked", "Cloud"]):
                st.info("Streamlit Cloud 서버 IP가 YouTube에 의해 차단되어 자막을 가져올 수 없습니다.")
            else:
                st.info("이 영상에는 자막이 제공되지 않습니다. 우측 AI 분석에서 편집 자막을 확인하세요.")

    # ── 오른쪽: AI 영상 분석 ──────────────────────────────────────
    with right_col:
        st.markdown('<div class="section-header">🎬 AI 영상 분석</div>', unsafe_allow_html=True)

        api_key = _get_gemini_api_key()
        cobalt_token = _get_cobalt_token()

        if not api_key:
            st.error("Gemini API 키 미설정 — Streamlit Cloud → Settings → Secrets에서 `GEMINI_API_KEY` 설정 후 앱 재시작")

        elif st.session_state.gemini_result is not None:
            # 분석 결과 표시
            with st.container(border=True):
                st.markdown(st.session_state.gemini_result)
            st.download_button(
                label="AI 분석 결과 다운로드 (.txt)",
                data=st.session_state.gemini_result,
                file_name=f"{video_id}_ai_analysis.txt",
                mime="text/plain",
            )
            if st.button("다시 분석", key="gemini_reset_btn"):
                st.session_state.gemini_result = None
                st.session_state.gemini_error = None
                st.session_state.gemini_auto_pending = True
                st.rerun()

        elif st.session_state.gemini_error is not None:
            err = st.session_state.gemini_error
            st.error(f"분석 실패: {err}")

            if "COBALT_TOKEN_REQUIRED" in err:
                st.warning(
                    "**영상 다운로드에 cobalt API 토큰이 필요합니다**\n\n"
                    "cobalt.tools는 최근 인증 방식으로 변경되었습니다. "
                    "무료 토큰 발급 후 Streamlit Secrets에 등록하면 URL만으로 자동 분석이 가능합니다.\n\n"
                    "**토큰 발급:** [cobalt.tools](https://cobalt.tools) → 설정(⚙️) → API\n\n"
                    "**Secrets 등록:** Streamlit Cloud → 앱 → Settings → Secrets\n"
                    "```\nCOBALT_API_TOKEN = \"발급받은_토큰\"\n```\n\n"
                    "토큰 등록 전까지 아래 파일 업로드로 분석할 수 있습니다."
                )

            # 파일 업로드 대안
            with st.expander("🗂 MP4 파일 직접 업로드로 분석", expanded=("COBALT_TOKEN_REQUIRED" in err)):
                st.caption("YouTube에서 영상을 다운로드한 후 MP4/MOV 파일을 업로드하세요.")
                uploaded_video = st.file_uploader(
                    "영상 파일 (MP4, MOV · 최대 200MB)",
                    type=["mp4", "mov"],
                    key="gemini_upload_fallback",
                )
                if uploaded_video:
                    if st.button("파일로 AI 분석 시작", key="gemini_file_fallback_btn", type="primary"):
                        video_bytes = uploaded_video.read()
                        mime_type = "video/quicktime" if uploaded_video.name.lower().endswith(".mov") else "video/mp4"
                        with st.spinner("Gemini 분석 중... (1~3분 소요)"):
                            try:
                                result = analyze_with_file_bytes(video_bytes, mime_type, api_key)
                                st.session_state.gemini_result = result
                                st.session_state.gemini_error = None
                                st.session_state.gemini_auto_pending = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"파일 분석 실패: {e}")

            if st.button("자동 분석 다시 시도", key="gemini_retry_btn"):
                st.session_state.gemini_error = None
                st.session_state.gemini_auto_pending = True
                st.rerun()

        elif st.session_state.gemini_auto_pending:
            # AI 분석 자동 실행
            with st.spinner("🎬 AI가 실제 영상을 분석하는 중... (약 1~3분 소요)"):
                try:
                    result = analyze_from_youtube_url(youtube_url, api_key, cobalt_token)
                    st.session_state.gemini_result = result
                    st.session_state.gemini_error = None
                except Exception as e:
                    st.session_state.gemini_error = str(e)
                    st.session_state.gemini_result = None
                finally:
                    st.session_state.gemini_auto_pending = False
            st.rerun()
