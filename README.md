# YouTube 영상 분석기

한국어 숏폼 YouTube 영상의 자막, 대본, 화면 텍스트를 분석하는 웹 대시보드입니다.

## 기능

- **자막/대본**: 유튜브 공식 자막을 타임스탬프별로 원본 그대로 추출
- **화면 텍스트 (OCR)**: 영상 프레임에서 한국어 텍스트 자동 인식
- **영상 정보**: 제목, 채널, 조회수, 업로드일, 설명

## 로컬 실행

```bash
cd youtube-analyzer
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포 (무료)

1. 이 폴더를 GitHub 레포지토리에 푸시
2. [share.streamlit.io](https://share.streamlit.io) 접속
3. GitHub 레포 연결 → `app.py` 선택 → Deploy
4. `packages.txt`가 있으므로 ffmpeg 등 시스템 의존성 자동 설치됨

## 프로젝트 구조

```
youtube-analyzer/
├── app.py                  # Streamlit 메인 앱
├── requirements.txt        # Python 패키지
├── packages.txt            # 시스템 패키지 (배포용)
├── .streamlit/
│   └── config.toml         # UI 테마 설정
└── utils/
    ├── transcript.py       # 자막 추출
    ├── video.py            # 영상 다운로드 + 프레임 추출
    └── ocr.py              # EasyOCR 한국어 텍스트 인식
```
