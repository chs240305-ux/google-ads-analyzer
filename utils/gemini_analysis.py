from __future__ import annotations

from google import genai
from google.genai import types

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


def analyze_video_with_gemini(youtube_url: str, api_key: str) -> str:
    """YouTube URL을 Gemini에 직접 전달해 분석 — 다운로드 불필요."""
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_uri(
                file_uri=youtube_url,
                mime_type="video/*",
            ),
            ANALYSIS_PROMPT,
        ],
    )
    return response.text
