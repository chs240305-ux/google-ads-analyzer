import streamlit as st
import tempfile
import os
import io
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
from utils.video import get_video_info, download_video, extract_frames, format_view_count, format_upload_date
from utils.ocr import extract_text_from_image, deduplicate_texts
from utils.transparency import is_transparency_url, extract_youtube_from_transparency
from utils.gemini_analysis import analyze_video_with_gemini

st.set_page_config(
    page_title="YouTube 영상 분석기",
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
}
.ocr-frame-header { color: #FFD700; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; }
.ocr-text-item { background: #1E1E1E; border-radius: 6px; padding: 6px 10px; margin: 3px 0; font-size: 0.9rem; }
.confidence-badge { font-size: 0.75rem; color: #888; margin-left: 8px; }
.gemini-result {
    background: #0D1117; border: 1px solid #30363D;
    border-radius: 10px; padding: 20px; line-height: 1.8;
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
    ("ocr_results", None),
    ("gemini_result", None),
    ("transcript", None),
    ("transcript_source", None),
    ("transcript_loaded_for", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _get_gemini_api_key() -> str:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")


def _display_ocr_results(results: dict, video_id: str) -> None:
    unique_texts = results["unique_texts"]
    frame_display_data = results["frames"]

    if unique_texts:
        st.success(f"총 {len(unique_texts)}개의 텍스트를 감지했습니다.")

        st.markdown("#### 감지된 전체 텍스트 목록")
        for t in unique_texts:
            st.markdown(f'<div class="ocr-text-item">📌 {t}</div>', unsafe_allow_html=True)

        if frame_display_data:
            st.markdown("---")
            st.markdown("#### 프레임별 상세 결과")
            cols_per_row = 3
            for i in range(0, len(frame_display_data), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(frame_display_data):
                        fd = frame_display_data[idx]
                        with col:
                            ts = format_timestamp(fd["timestamp"])
                            st.markdown(f'<div class="ocr-frame-header">⏱ {ts}</div>', unsafe_allow_html=True)
                            st.image(fd["image_bytes"], use_container_width=True)
                            for item in fd["texts"]:
                                st.markdown(
                                    f'<div class="ocr-text-item">{item["text"]}'
                                    f'<span class="confidence-badge">{item["confidence"]}%</span>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )

        st.download_button(
            label="화면 텍스트 다운로드 (.txt)",
            data="\n".join(unique_texts),
            file_name=f"{video_id}_ocr.txt",
            mime="text/plain",
        )
    else:
        st.warning("화면에서 감지된 텍스트가 없습니다.")


# ── 헤더 ─────────────────────────────────────────────────────────
st.markdown('<div class="main-title">▶ YouTube 영상 분석기</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">YouTube 숏폼 영상의 자막, 대본, 화면 텍스트, AI 영상 분석을 제공합니다</div>', unsafe_allow_html=True)

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

# ── 분석 시작 버튼 처리 ──────────────────────────────────────────
if analyze_btn and url_input:
    if st.session_state.last_url != url_input:
        st.session_state.ocr_results = None
        st.session_state.gemini_result = None

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

    with st.spinner("영상 정보를 불러오는 중..."):
        info = get_video_info(youtube_url)

    if info is None:
        st.error("영상 정보를 불러올 수 없습니다. URL을 다시 확인해주세요.")
        st.stop()

    st.session_state.analyzed = True
    st.session_state.video_id = video_id
    st.session_state.youtube_url = youtube_url
    st.session_state.info = info
    st.session_state.last_url = url_input

elif analyze_btn and not url_input:
    st.warning("YouTube URL을 입력해주세요.")

# ── 분석 결과 렌더링 ─────────────────────────────────────────────
if st.session_state.analyzed:
    info = st.session_state.info
    video_id = st.session_state.video_id
    youtube_url = st.session_state.youtube_url

    with st.container():
        c1, c2 = st.columns([1, 2])
        with c1:
            if info["thumbnail"]:
                st.image(info["thumbnail"], use_container_width=True)
        with c2:
            st.markdown(f"### {info['title']}")
            st.markdown(f"**채널:** {info['channel']}")
            duration_min = info['duration'] // 60
            duration_sec = info['duration'] % 60
            st.markdown(f"**길이:** {duration_min:02d}:{duration_sec:02d}")
            if info["view_count"]:
                st.markdown(f"**조회수:** {format_view_count(info['view_count'])}회")
            if info["upload_date"]:
                st.markdown(f"**업로드:** {format_upload_date(info['upload_date'])}")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 자막 / 대본",
        "🔤 화면 텍스트 (OCR)",
        "ℹ️ 영상 설명",
        "🎬 AI 영상 분석 (Gemini)",
    ])

    # ── 탭 1: 자막 ─────────────────────────────────────────────
    with tab1:
        if st.session_state.transcript_loaded_for != video_id:
            with st.spinner("자막을 가져오는 중..."):
                transcript, transcript_source = get_transcript(video_id)
            st.session_state.transcript = transcript
            st.session_state.transcript_source = transcript_source
            st.session_state.transcript_loaded_for = video_id
        else:
            transcript = st.session_state.transcript
            transcript_source = st.session_state.transcript_source

        if transcript:
            st.success(f"자막 {len(transcript)}개 항목을 불러왔습니다. ({transcript_source})")
            st.markdown("#### 전체 대본 (원본)")
            full_text = get_full_text(transcript)
            st.markdown(f'<div class="full-text-box">{full_text}</div>', unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("#### 타임스탬프별 자막")
            for item in transcript:
                ts = format_timestamp(item["start"])
                text = item["text"].replace("\n", " ")
                st.markdown(
                    f'<div class="transcript-line">'
                    f'<span class="timestamp-badge">[{ts}]</span>{text}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            st.markdown("---")
            transcript_export = "\n".join(
                f"[{format_timestamp(item['start'])}] {item['text'].replace(chr(10), ' ')}"
                for item in transcript
            )
            st.download_button(
                label="자막 텍스트 다운로드 (.txt)",
                data=transcript_export,
                file_name=f"{video_id}_transcript.txt",
                mime="text/plain",
            )
        else:
            st.warning(f"자막을 불러올 수 없습니다: {transcript_source}")
            st.info("자막이 비활성화되어 있거나 이 영상에는 자막이 제공되지 않을 수 있습니다.")

    # ── 탭 2: 화면 텍스트 OCR ────────────────────────────────────
    with tab2:
        # 이미 분석된 결과가 있으면 바로 표시
        if st.session_state.ocr_results is not None:
            _display_ocr_results(st.session_state.ocr_results, video_id)
            if st.button("OCR 다시 분석", key="ocr_reset_btn"):
                st.session_state.ocr_results = None
                st.rerun()
        else:
            st.info("영상을 다운로드하고 프레임별 한국어 텍스트를 인식합니다.")
            st.warning("'화면 텍스트 분석 시작' 버튼을 누르면 분석이 시작됩니다. (약 30초~1분 소요)")

            if st.button("화면 텍스트 분석 시작", key="ocr_btn"):
                download_ok = False
                with tempfile.TemporaryDirectory() as tmpdir:
                    progress = st.progress(0, text="영상 다운로드 중...")
                    video_path = download_video(youtube_url, tmpdir)

                    if not video_path:
                        progress.empty()
                        st.error(
                            "영상 다운로드에 실패했습니다. "
                            "Streamlit Cloud 환경에서는 일부 YouTube 영상의 다운로드가 제한될 수 있습니다. "
                            "AI 영상 분석(Gemini) 탭을 이용해주세요."
                        )
                    else:
                        download_ok = True
                        progress.progress(30, text="프레임 추출 중...")
                        frames = extract_frames(video_path, interval_seconds=1.5)

                        if not frames:
                            progress.empty()
                            st.error("프레임 추출에 실패했습니다.")
                        else:
                            progress.progress(50, text=f"OCR 분석 중... ({len(frames)}개 프레임)")
                            all_frame_results = []
                            frame_display_data = []

                            for i, frame_data in enumerate(frames):
                                texts = extract_text_from_image(frame_data["image"])
                                all_frame_results.append(texts)
                                if texts:
                                    buf = io.BytesIO()
                                    frame_data["image"].save(buf, format="PNG")
                                    frame_display_data.append({
                                        "timestamp": frame_data["timestamp"],
                                        "image_bytes": buf.getvalue(),
                                        "texts": texts,
                                    })
                                pct = 50 + int((i + 1) / len(frames) * 45)
                                progress.progress(pct, text=f"OCR 분석 중... ({i+1}/{len(frames)})")

                            progress.progress(100, text="완료!")
                            progress.empty()

                            unique_texts = deduplicate_texts(all_frame_results)
                            results = {"unique_texts": unique_texts, "frames": frame_display_data}
                            st.session_state.ocr_results = results
                            _display_ocr_results(results, video_id)

    # ── 탭 3: 영상 설명 ─────────────────────────────────────────
    with tab3:
        if info.get("description"):
            st.markdown("#### 영상 설명 (원본)")
            st.markdown(f'<div class="full-text-box">{info["description"]}</div>', unsafe_allow_html=True)
        else:
            st.info("영상 설명이 없습니다.")

    # ── 탭 4: AI 영상 분석 (Gemini) ─────────────────────────────
    with tab4:
        st.markdown("""
**Gemini가 YouTube 영상을 직접 분석합니다.**
다운로드 없이 URL만으로 편집 자막 · 화면 구성 · 스토리 흐름 · 바이럴 요소를 분석합니다.
        """)

        api_key = _get_gemini_api_key()

        if not api_key:
            st.error(
                "Gemini API 키가 설정되지 않았습니다. "
                "Streamlit Cloud → Settings → Secrets에서 `GEMINI_API_KEY`를 설정해주세요."
            )
        elif st.session_state.gemini_result is not None:
            st.markdown(
                f'<div class="gemini-result">{st.session_state.gemini_result}</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                label="AI 분석 결과 다운로드 (.txt)",
                data=st.session_state.gemini_result,
                file_name=f"{video_id}_ai_analysis.txt",
                mime="text/plain",
            )
            if st.button("AI 분석 다시 실행", key="gemini_reset_btn"):
                st.session_state.gemini_result = None
                st.rerun()
        else:
            st.info("YouTube URL을 Gemini에 직접 전달합니다. 영상 길이에 따라 30초~2분 소요됩니다.")
            if st.button("AI 영상 분석 시작", key="gemini_btn", type="primary"):
                with st.spinner("Gemini가 영상을 분석하는 중..."):
                    try:
                        result = analyze_video_with_gemini(youtube_url, api_key)
                        st.session_state.gemini_result = result
                        st.markdown(
                            f'<div class="gemini-result">{result}</div>',
                            unsafe_allow_html=True,
                        )
                        st.download_button(
                            label="AI 분석 결과 다운로드 (.txt)",
                            data=result,
                            file_name=f"{video_id}_ai_analysis.txt",
                            mime="text/plain",
                        )
                    except Exception as e:
                        st.error(f"분석 실패: {e}")
