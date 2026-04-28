from __future__ import annotations

import json
import os
import re
import tempfile
import time
import requests

ANALYSIS_PROMPT = """이 유튜브 영상을 전문 영상 크리에이터의 시각으로 심층 분석해주세요.

⚠️ 중요: YouTube 시스템 자막이 아닌, 실제 영상 화면에 편집으로 삽입된 시각적 요소를 분석하세요.

---

## 1. 📝 화면 텍스트 & 편집 자막
타임라인 순서대로 영상 화면에 실제로 보이는 텍스트를 모두 기록하세요:
- 편집으로 추가된 자막 문구 (타임스탬프 포함)
- 화면에 나타나는 제목, 강조 문구, 해시태그, 이모지
- 상단/하단에 고정된 후킹 문구, CTA 문구
- 그래픽 / 자막 바에 포함된 텍스트

## 2. 🎬 영상 구성 흐름 (스토리 구조)
- **오프닝 훅** (첫 1~3초): 어떤 방식으로 시청자를 사로잡는가
- **전개**: 내용이 어떤 순서로 전달되는가
- **클라이맥스**: 핵심 메시지 또는 감정적 절정 장면
- **마무리 / CTA**: 어떻게 끝나는가, 어떤 행동을 유도하는가

## 3. 🖼️ 시각적 구성 요소
- 화면 레이아웃 및 구성 (텍스트 위치, 인물 배치 등)
- 사용된 그래픽, 아이콘, 애니메이션, 특수효과
- 색감 및 전체적인 비주얼 톤
- 전환 효과 및 편집 템포 (빠른 컷, 슬로우모션 등)

## 4. 🎥 촬영 & 제작 특성
- 촬영 환경 및 배경 (스튜디오, 야외, 실내 등)
- 카메라 앵글, 구도, 움직임
- 출연자 / 제품 / 브랜드 노출 방식

## 5. 🔥 바이럴 DNA 분석
- 시청자 감정을 자극하는 핵심 요소 (호기심, 공감, 놀라움 등)
- 공유 / 저장 / 댓글을 유도하는 장치
- 타겟 오디언스 추정 (연령대, 관심사 등)
- 이 영상에서 배울 수 있는 핵심 제작 인사이트 3가지

한국어로 구체적이고 상세하게 작성해주세요. 실제 영상에서 관찰한 내용만 작성하세요."""

_BASE = "https://generativelanguage.googleapis.com"
_MODEL = "gemini-2.0-flash"

_COBALT_BASE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; VideoAnalyzer/1.0)",
}
_COBALT_INSTANCES = [
    ("https://cobalt.privacydev.net", False),
    ("https://cobalt.api.timelessnesses.me", False),
    ("https://api.cobalt.tools", True),
]
_PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.in.projectsegfau.lt",
]


def _extract_video_id(url: str) -> str | None:
    for pattern in [r"(?:v=|\/)([0-9A-Za-z_-]{11})", r"youtu\.be\/([0-9A-Za-z_-]{11})"]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def _generate_content(payload: dict, api_key: str) -> str:
    resp = requests.post(
        f"{_BASE}/v1beta/models/{_MODEL}:generateContent",
        json=payload,
        params={"key": api_key},
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API 오류 {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"응답 파싱 실패: {resp.text[:200]}") from e


# ── 다운로드 방법 1: yt-dlp (Railway 등 클라우드 IP 미차단 환경) ─────
def download_via_ytdlp(youtube_url: str) -> tuple[bytes, str]:
    """yt-dlp로 직접 다운로드 (Streamlit Cloud IP 차단 환경에서는 실패)."""
    import yt_dlp

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        ydl_opts = {
            "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]",
            "outtmpl": tmp.name,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "merge_output_format": "mp4",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        with open(tmp.name, "rb") as f:
            return f.read(), "video/mp4"
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ── 다운로드 방법 2: cobalt 프록시 ──────────────────────────────────
def download_via_cobalt(youtube_url: str, cobalt_token: str = "") -> tuple[bytes, str]:
    """cobalt 인스턴스를 순차 시도해 YouTube 영상을 다운로드합니다."""
    body = {
        "url": youtube_url,
        "videoQuality": "720",
        "filenameStyle": "basic",
        "downloadMode": "auto",
    }
    last_error = "알 수 없는 오류"

    for instance_url, requires_token in _COBALT_INSTANCES:
        if requires_token and not cobalt_token:
            continue

        headers = _COBALT_BASE_HEADERS.copy()
        if requires_token and cobalt_token:
            headers["Authorization"] = f"Api-Key {cobalt_token}"

        try:
            resp = requests.post(f"{instance_url}/", json=body, headers=headers, timeout=20)
        except Exception as e:
            last_error = str(e)
            continue

        if resp.status_code == 400 and "jwt" in resp.text.lower():
            last_error = "인증 필요"
            continue
        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}"
            continue

        data = resp.json()
        status = data.get("status")
        if status == "error":
            last_error = data.get("error", {}).get("code", "unknown")
            continue
        if status == "picker":
            download_url = data["picker"][0]["url"]
        elif status in ("stream", "tunnel", "redirect"):
            download_url = data["url"]
        else:
            last_error = f"예상치 못한 응답: {status}"
            continue

        try:
            vr = requests.get(download_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=300, stream=True)
            vr.raise_for_status()
            ct = vr.headers.get("Content-Type", "video/mp4").split(";")[0].strip()
            return vr.content, ct if "video" in ct else "video/mp4"
        except Exception as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"cobalt 실패: {last_error}")


# ── 다운로드 방법 3: Piped.video 프록시 ─────────────────────────────
def download_via_piped(video_id: str) -> tuple[bytes, str]:
    """Piped.video API를 통해 YouTube 영상을 다운로드합니다."""
    for instance in _PIPED_INSTANCES:
        try:
            resp = requests.get(f"{instance}/streams/{video_id}", timeout=15)
            if not resp.ok:
                continue
            data = resp.json()

            streams = [s for s in data.get("videoStreams", []) if not s.get("videoOnly", True)]
            if not streams:
                streams = data.get("videoStreams", [])

            def q_key(s: dict) -> int:
                return int("".join(c for c in s.get("quality", "0") if c.isdigit()) or "0")

            streams.sort(key=q_key)

            for stream in streams[:3]:
                url = stream.get("url", "")
                if not url:
                    continue
                try:
                    vr = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=300, stream=True)
                    if vr.ok:
                        ct = vr.headers.get("Content-Type", "video/mp4").split(";")[0].strip()
                        return vr.content, ct if "video" in ct else "video/mp4"
                except Exception:
                    continue
        except Exception:
            continue

    raise RuntimeError("Piped 다운로드 실패")


# ── 썸네일 + 자막 분석 (Streamlit Cloud 폴백) ───────────────────────
def _fetch_thumbnail(video_id: str) -> bytes | None:
    """i.ytimg.com에서 YouTube 썸네일을 다운로드합니다 (IP 차단 없음)."""
    for quality in ["maxresdefault", "hq720", "hqdefault"]:
        try:
            resp = requests.get(
                f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg",
                timeout=15,
            )
            if resp.ok and len(resp.content) > 5000:
                return resp.content
        except Exception:
            continue
    return None


def analyze_with_thumbnail(
    video_id: str,
    transcript_text: str,
    api_key: str,
) -> str:
    """썸네일 이미지 + 자막으로 Gemini 분석 (영상 다운로드 불가 환경의 폴백)."""
    import base64

    thumb_bytes = _fetch_thumbnail(video_id)
    parts: list[dict] = []

    if thumb_bytes:
        parts.append({
            "inlineData": {
                "data": base64.b64encode(thumb_bytes).decode(),
                "mimeType": "image/jpeg",
            }
        })

    has_transcript = bool(transcript_text and transcript_text.strip())
    transcript_section = (
        f"## 2. 📝 자막 / 대본 분석\n\n**전체 자막:**\n{transcript_text[:4000]}\n\n"
        "- 오프닝 훅 / 후킹 문구 분석\n"
        "- 내용 전개 방식\n"
        "- CTA / 마무리 메시지"
        if has_transcript else
        "## 2. 📝 자막 분석\n자막 없음 — 썸네일 기반으로만 분석합니다."
    )

    prompt = f"""이 YouTube 광고의 썸네일{"과 자막" if has_transcript else ""}을 분석해주세요.

## 1. 🖼️ 썸네일 & 시각 요소
- 썸네일에 보이는 텍스트, 강조 문구, 이모지
- 인물, 제품, 배경 구성
- 색감, 폰트, 전체 시각적 톤
- 클릭 유도 요소 (호기심, 긴급성, 감정 등)
- 썸네일이 전달하는 핵심 메시지

{transcript_section}

## 3. 🔥 바이럴 DNA 분석
- 감정적 트리거 요소
- 타겟 오디언스 추정 (연령대, 관심사 등)
- 이 광고에서 배울 수 있는 핵심 인사이트 3가지

한국어로 구체적이고 상세하게 분석해주세요."""

    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.3},
    }
    result = _generate_content(payload, api_key)
    return (
        "> 📌 **썸네일 + 자막 기반 분석** "
        "*(Streamlit Cloud IP 제한으로 전체 영상 대신 썸네일 분석 적용)*\n\n"
        + result
    )


# ── 통합 분석 함수 ───────────────────────────────────────────────────
def analyze_from_youtube_url(youtube_url: str, api_key: str, cobalt_token: str = "") -> str:
    """YouTube URL → 다운로드(yt-dlp → cobalt → Piped 순서) → Gemini Files API 분석."""
    video_id = _extract_video_id(youtube_url)

    # 1순위: yt-dlp (비차단 환경 — Railway, 로컬 등)
    try:
        video_bytes, mime_type = download_via_ytdlp(youtube_url)
        return analyze_with_file_bytes(video_bytes, mime_type, api_key)
    except Exception:
        pass

    # 2순위: cobalt
    try:
        video_bytes, mime_type = download_via_cobalt(youtube_url, cobalt_token)
        return analyze_with_file_bytes(video_bytes, mime_type, api_key)
    except Exception:
        pass

    # 3순위: Piped
    if video_id:
        try:
            video_bytes, mime_type = download_via_piped(video_id)
            return analyze_with_file_bytes(video_bytes, mime_type, api_key)
        except Exception:
            pass

    raise RuntimeError("DOWNLOAD_FAILED")


def analyze_with_file_bytes(video_bytes: bytes, mime_type: str, api_key: str) -> str:
    """영상 파일을 Gemini Files API에 업로드 후 분석."""
    boundary = "gemini_upload_bound"
    meta = json.dumps({"file": {"display_name": "video_analysis"}})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        + meta
        + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n"
    ).encode() + video_bytes + f"\r\n--{boundary}--".encode()

    up = requests.post(
        f"{_BASE}/upload/v1beta/files",
        params={"key": api_key, "uploadType": "multipart"},
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=300,
    )
    up.raise_for_status()
    file_info = up.json()["file"]
    file_uri = file_info["uri"]
    file_name = file_info["name"]

    try:
        for _ in range(24):
            st_resp = requests.get(f"{_BASE}/v1beta/{file_name}", params={"key": api_key}, timeout=30)
            if st_resp.status_code != 200:
                break
            state = st_resp.json().get("state", "")
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise RuntimeError("파일 처리 실패 (FAILED)")
            time.sleep(5)
        else:
            raise TimeoutError("파일 처리 시간 초과 (2분)")

        payload = {
            "contents": [{"parts": [
                {"fileData": {"fileUri": file_uri, "mimeType": mime_type}},
                {"text": ANALYSIS_PROMPT},
            ]}],
            "generationConfig": {"temperature": 0.3},
        }
        return _generate_content(payload, api_key)

    finally:
        try:
            requests.delete(f"{_BASE}/v1beta/{file_name}", params={"key": api_key}, timeout=30)
        except Exception:
            pass
