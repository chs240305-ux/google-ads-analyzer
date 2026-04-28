from __future__ import annotations

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
import re

_api = YouTubeTranscriptApi()


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"shorts\/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_transcript(video_id: str) -> tuple[list[dict] | None, str]:
    """
    Returns (transcript_list, source_description).
    transcript_list: list of {start, duration, text}
    source_description: 자막 출처 설명 문자열
    """
    try:
        transcript_list = _api.list(video_id)

        # 1순위: 수동 작성 한국어 자막
        try:
            t = transcript_list.find_manually_created_transcript(["ko"])
            return _to_dicts(t.fetch()), "수동 작성 한국어 자막"
        except NoTranscriptFound:
            pass

        # 2순위: 자동 생성 한국어 자막
        try:
            t = transcript_list.find_generated_transcript(["ko"])
            return _to_dicts(t.fetch()), "자동 생성 한국어 자막"
        except NoTranscriptFound:
            pass

        # 3순위: 한국어 번역 가능한 자막 탐색 (수동 생성 포함)
        try:
            for transcript in transcript_list:
                try:
                    translated = transcript.translate("ko")
                    return _to_dicts(translated.fetch()), f"{transcript.language} 자막 → 한국어 번역"
                except Exception:
                    continue
        except Exception:
            pass

        # 4순위: 언어 무관하게 첫 번째 사용 가능한 자막
        try:
            for transcript in transcript_list:
                return _to_dicts(transcript.fetch()), f"{transcript.language} 자막 (원어)"
        except Exception:
            pass

        return None, "자막 없음"

    except (TranscriptsDisabled, VideoUnavailable) as e:
        return None, f"자막 비활성화 또는 영상 접근 불가"
    except Exception as e:
        return None, f"자막 오류: {str(e)}"


def _to_dicts(fetched) -> list[dict]:
    return [
        {"start": s.start, "duration": s.duration, "text": s.text}
        for s in fetched
    ]


def format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def get_full_text(transcript: list[dict]) -> str:
    return " ".join(item["text"].replace("\n", " ") for item in transcript)
