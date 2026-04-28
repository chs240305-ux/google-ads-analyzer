from __future__ import annotations

import json
import time
import requests

ANALYSIS_PROMPT = """이 유튜브 영상을 전문 영상 크리에이터의 시각으로 심층 분석해주세요.

⚠️ 중요: YouTube 시스템 자막이 아닌, 실제 영상 화면에 편집으로 삽입된 시각적 요소를 분석하세요.

---

## 1. 📝 화면 텍스트 & 편집 자막
타임라인 순서대로 영상 화면에 실제로 보이는 텍스트를 모두 기록하세요:
- 편집으로 추가된 자막 문구 (타임스탬프 포함)
- 화면에 나타나는 제목, 강조 문구, 해시태그, 이모지
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

# 공식 인스턴스 + 커뮤니티 인스턴스 (인증 불필요한 것 우선 시도)
_COBALT_INSTANCES = [
    ("https://cobalt.privacydev.net", False),
    ("https://cobalt.api.timelessnesses.me", False),
    ("https://api.cobalt.tools", True),  # 공식: 토큰 필요
]


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


def download_via_cobalt(youtube_url: str, cobalt_token: str = "") -> tuple[bytes, str]:
    """cobalt를 프록시로 YouTube 영상을 다운로드합니다. 여러 인스턴스를 순차 시도합니다."""
    body = {
        "url": youtube_url,
        "videoQuality": "720",
        "filenameStyle": "basic",
        "downloadMode": "auto",
    }
    last_error = "알 수 없는 오류"

    for instance_url, requires_token in _COBALT_INSTANCES:
        if requires_token and not cobalt_token:
            continue  # 토큰 없으면 공식 인스턴스 건너뜀

        headers = _COBALT_BASE_HEADERS.copy()
        if requires_token and cobalt_token:
            headers["Authorization"] = f"Api-Key {cobalt_token}"

        try:
            resp = requests.post(
                f"{instance_url}/",
                json=body,
                headers=headers,
                timeout=20,
            )
        except Exception as e:
            last_error = str(e)
            continue

        if resp.status_code == 400 and "jwt" in resp.text.lower():
            last_error = "토큰_필요"
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
            video_resp = requests.get(
                download_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=300,
                stream=True,
            )
            video_resp.raise_for_status()
            content_type = video_resp.headers.get("Content-Type", "video/mp4")
            mime_type = content_type.split(";")[0].strip() if "video" in content_type else "video/mp4"
            return video_resp.content, mime_type
        except Exception as e:
            last_error = str(e)
            continue

    if last_error == "토큰_필요":
        raise RuntimeError("COBALT_TOKEN_REQUIRED")
    raise RuntimeError(f"모든 cobalt 인스턴스 실패: {last_error}")


def analyze_from_youtube_url(youtube_url: str, api_key: str, cobalt_token: str = "") -> str:
    """YouTube URL → cobalt 다운로드 → Gemini Files API 분석 자동 파이프라인."""
    video_bytes, mime_type = download_via_cobalt(youtube_url, cobalt_token)
    return analyze_with_file_bytes(video_bytes, mime_type, api_key)


def analyze_with_url(youtube_url: str, api_key: str) -> str:
    """YouTube URL을 Gemini에 직접 전달해 분석 (API 권한에 따라 작동 여부 다름)."""
    payload = {
        "contents": [{"parts": [
            {"fileData": {"fileUri": youtube_url, "mimeType": "video/*"}},
            {"text": ANALYSIS_PROMPT},
        ]}],
        "generationConfig": {"temperature": 0.3},
    }
    return _generate_content(payload, api_key)


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
        for _ in range(24):  # 최대 2분 대기
            st_resp = requests.get(
                f"{_BASE}/v1beta/{file_name}",
                params={"key": api_key},
                timeout=30,
            )
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
            requests.delete(
                f"{_BASE}/v1beta/{file_name}",
                params={"key": api_key},
                timeout=30,
            )
        except Exception:
            pass
