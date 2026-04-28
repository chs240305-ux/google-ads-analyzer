import streamlit as st
import tempfile
import os
import subprocess
import sys


@st.cache_resource(show_spinner=False)
def _ensure_playwright_chromium():
    """Streamlit Cloud 등 서버 환경에서 Chromium 바이너리를 설치한다."""
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

st.set_page_config(
    page_title="YouTube 영상 분석기",
    page_icon="▶",
    layout="wide",
)

st.markdown("""
<style>
.main-title {
    font-size: 2rem;
    font-weight: 800;
    color: #FF0000;
    margin-bottom: 0.2rem;
}
.subtitle {
    font-size: 0.95rem;
    color: #AAAAAA;
    margin-bottom: 1.5rem;
}
.transcript-line {
    padding: 8px 12px;
    margin: 4px 0;
    border-left: 3px solid #FF0000;
    background: #1E1E1E;
    border-radius: 0 6px 6px 0;
    font-size: 0.95rem;
}
.timestamp-badge {
    color: #FF6B6B;
    font-size: 0.8rem;
    font-weight: 600;
    margin-right: 8px;
    font-family: monospace;
}
.info-card {
    background: #1E1E1E;
    border-radius: 10px;
    padding: 16px;
    margin: 8px 0;
}
.full-text-box {
    background: #1A1A2E;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 16px;
    font-size: 0.95rem;
    line-height: 1.8;
    white-space: pre-wrap;
}
.ocr-frame-header {
    color: #FFD700;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 4px;
}
.ocr-text-item {
    background: #1E1E1E;
    border-radius: 6px;
    padding: 6px 10px;
    margin: 3px 0;
    font-size: 0.9rem;
}
.confidence-badge {
    font-size: 0.75rem;
    color: #888;
    margin-left: 8px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">▶ YouTube 영상 분석기</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">YouTube 숏폼 영상의 자막, 대본, 화면 텍스트를 분석합니다</div>', unsafe_allow_html=True)

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

if analyze_btn and url_input:

    # ── Google 광고 투명성 센터 URL 처리 ───────────────────────────
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

    # ── 영상 기본 정보 ──────────────────────────────────────────────
    with st.spinner("영상 정보를 불러오는 중..."):
        info = get_video_info(youtube_url)

    if info is None:
        st.error("영상 정보를 불러올 수 없습니다. URL을 다시 확인해주세요.")
        st.stop()

    # 영상 기본 정보 헤더
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

    # ── 탭 구성 ────────────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs(["📝 자막 / 대본", "🔤 화면 텍스트 (OCR)", "ℹ️ 영상 설명"])

    # ── 탭 1: 자막 ─────────────────────────────────────────────────
    with tab1:
        with st.spinner("자막을 가져오는 중..."):
            transcript, transcript_source = get_transcript(video_id)

        if transcript:
            st.success(f"자막 {len(transcript)}개 항목을 불러왔습니다. ({transcript_source})")

            # 전체 대본 (원본 그대로)
            st.markdown("#### 전체 대본 (원본)")
            full_text = get_full_text(transcript)
            st.markdown(f'<div class="full-text-box">{full_text}</div>', unsafe_allow_html=True)

            st.markdown("---")

            # 타임스탬프별 자막
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

            # 다운로드 버튼
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

    # ── 탭 2: 화면 텍스트 OCR ──────────────────────────────────────
    with tab2:
        st.info("영상을 다운로드하고 프레임별 한국어 텍스트를 인식합니다. 잠시 기다려주세요.")

        ocr_placeholder = st.empty()
        ocr_placeholder.warning("'화면 텍스트 분석 시작' 버튼을 누르면 분석이 시작됩니다. (약 30초~1분 소요)")

        if st.button("화면 텍스트 분석 시작", key="ocr_btn"):
            ocr_placeholder.empty()

            with tempfile.TemporaryDirectory() as tmpdir:
                # 영상 다운로드
                progress = st.progress(0, text="영상 다운로드 중...")
                video_path = download_video(youtube_url, tmpdir)

                if not video_path:
                    st.error("영상 다운로드에 실패했습니다.")
                    st.stop()

                progress.progress(30, text="프레임 추출 중...")

                # 프레임 추출 (1.5초 간격)
                frames = extract_frames(video_path, interval_seconds=1.5)

                if not frames:
                    st.error("프레임 추출에 실패했습니다.")
                    st.stop()

                progress.progress(50, text=f"OCR 분석 중... ({len(frames)}개 프레임)")

                # EasyOCR 실행
                all_frame_results = []
                frame_display_data = []

                for i, frame_data in enumerate(frames):
                    texts = extract_text_from_image(frame_data["image"])
                    all_frame_results.append(texts)
                    if texts:
                        frame_display_data.append({
                            "timestamp": frame_data["timestamp"],
                            "image": frame_data["image"],
                            "texts": texts,
                        })
                    pct = 50 + int((i + 1) / len(frames) * 45)
                    progress.progress(pct, text=f"OCR 분석 중... ({i+1}/{len(frames)})")

                progress.progress(100, text="완료!")
                progress.empty()

            # 결과 출력
            unique_texts = deduplicate_texts(all_frame_results)

            if unique_texts:
                st.success(f"총 {len(unique_texts)}개의 텍스트를 감지했습니다.")

                # 감지된 전체 텍스트 목록
                st.markdown("#### 감지된 전체 텍스트 목록")
                for t in unique_texts:
                    st.markdown(f'<div class="ocr-text-item">📌 {t}</div>', unsafe_allow_html=True)

                st.markdown("---")

                # 프레임별 상세 결과
                st.markdown("#### 프레임별 상세 결과")
                if frame_display_data:
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
                                    st.image(fd["image"], use_container_width=True)
                                    for item in fd["texts"]:
                                        st.markdown(
                                            f'<div class="ocr-text-item">{item["text"]}'
                                            f'<span class="confidence-badge">{item["confidence"]}%</span>'
                                            f'</div>',
                                            unsafe_allow_html=True,
                                        )

                # 다운로드
                ocr_export = "\n".join(unique_texts)
                st.download_button(
                    label="화면 텍스트 다운로드 (.txt)",
                    data=ocr_export,
                    file_name=f"{video_id}_ocr.txt",
                    mime="text/plain",
                )
            else:
                st.warning("화면에서 감지된 텍스트가 없습니다.")

    # ── 탭 3: 영상 설명 ────────────────────────────────────────────
    with tab3:
        if info.get("description"):
            st.markdown("#### 영상 설명 (원본)")
            st.markdown(f'<div class="full-text-box">{info["description"]}</div>', unsafe_allow_html=True)
        else:
            st.info("영상 설명이 없습니다.")

elif analyze_btn and not url_input:
    st.warning("YouTube URL을 입력해주세요.")
