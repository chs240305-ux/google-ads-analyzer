from __future__ import annotations

import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

YOUTUBE_ID_PATTERN = re.compile(
    r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)([0-9A-Za-z_-]{11})'
)

TRANSPARENCY_PATTERN = re.compile(
    r'adstransparency\.google\.com/advertiser/([^/]+)/creative/([^/?]+)'
)


def is_transparency_url(url: str) -> bool:
    return bool(TRANSPARENCY_PATTERN.search(url))


def extract_youtube_from_transparency(page_url: str) -> tuple[str | None, str]:
    """
    Google 광고 투명성 센터 URL에서 YouTube 영상 ID를 추출한다.
    Returns (youtube_url, status_message)
    """
    found_id: list[str] = []  # mutable for closure

    def _capture(url: str) -> None:
        m = YOUTUBE_ID_PATTERN.search(url)
        if m and not found_id:
            found_id.append(m.group(1))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = context.new_page()

        # 모든 네트워크 요청에서 YouTube URL 감지
        page.on("request", lambda req: _capture(req.url))
        page.on("response", lambda res: _capture(res.url))

        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)

            # 1단계: DOM에서 YouTube iframe 직접 탐색
            if not found_id:
                for iframe in page.query_selector_all("iframe"):
                    src = iframe.get_attribute("src") or ""
                    _capture(src)

            # 2단계: 재생 버튼 클릭 후 네트워크 요청 대기
            if not found_id:
                _click_play_button(page)
                # 재생 후 YouTube URL 등장 대기 (최대 10초)
                for _ in range(20):
                    if found_id:
                        break
                    page.wait_for_timeout(500)

            # 3단계: 재생 후 iframe 재탐색
            if not found_id:
                for iframe in page.query_selector_all("iframe"):
                    src = iframe.get_attribute("src") or ""
                    _capture(src)

        except PlaywrightTimeout:
            pass
        except Exception:
            pass
        finally:
            browser.close()

    if found_id:
        yt_url = f"https://www.youtube.com/watch?v={found_id[0]}"
        return yt_url, f"YouTube ID 추출 완료: {found_id[0]}"
    return None, "YouTube URL을 찾지 못했습니다. 광고에 YouTube 영상이 없거나 재생이 차단되었을 수 있습니다."


def _click_play_button(page) -> None:
    """다양한 재생 버튼 선택자를 순서대로 시도한다."""
    selectors = [
        # Google Ads Transparency 재생 버튼
        'button[aria-label*="재생"]',
        'button[aria-label*="Play"]',
        '[role="button"][aria-label*="재생"]',
        '[role="button"][aria-label*="Play"]',
        # 일반적인 비디오 플레이어 오버레이
        '.play-button',
        '[data-testid="play-button"]',
        '[class*="PlayButton"]',
        '[class*="play-btn"]',
        # 비디오 요소 자체 클릭
        'video',
        # 광고 크리에이티브 컨테이너
        '[class*="creative"] video',
        '[class*="ad-preview"] video',
        'div[class*="video"] > div',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue
