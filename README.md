# 씬메이커 (Scene Maker)

대본 + 상품 사진 → 자동으로 쇼츠/릴스용 영상을 만들어주는 로컬 프로그램입니다.

---

## 1. 처음 한 번만 준비하기

### ① 파이썬(Python) 설치
- 이미 설치되어 있는지 확인: 터미널(맥은 "터미널", 윈도우는 "명령 프롬프트")을 열고 아래 입력
  ```
  python3 --version
  ```
  `Python 3.10` 같은 버전이 나오면 이미 설치되어 있는 것입니다. 안 나오면:
- [https://www.python.org/downloads/](https://www.python.org/downloads/) 접속 → 다운로드 → 설치
  (설치 화면에서 **"Add Python to PATH"** 체크박스를 꼭 체크하세요)

### ② ffmpeg 설치 (영상 합성에 필요)
- **Mac**: 터미널에 `brew install ffmpeg` (Homebrew가 없다면 먼저 [brew.sh](https://brew.sh) 안내대로 설치)
- **Windows**: [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) 에서 "release essentials" 다운로드 → 압축 풀기 → 폴더 안 `bin` 경로를 환경변수 PATH에 추가
  (막히면 저에게 캡처와 함께 물어봐주세요)

### ③ 이 폴더를 원하는 위치에 저장
지금 받은 `coupang_video_app` 폴더를 바탕화면 등 원하는 곳에 둡니다.

### ④ 필요한 패키지 설치
터미널에서 이 폴더로 이동한 뒤:
```
cd 폴더가_있는_경로/coupang_video_app
pip install -r requirements.txt
```

### ⑤ 타입캐스트 API 키 등록
1. `.env.example` 파일을 복사해서 이름을 `.env` 로 바꿉니다.
2. `.env` 파일을 열어서 `TYPECAST_API_KEY=` 뒤에 발급받은 키를 붙여넣습니다.
3. 저장합니다.

> ⚠️ `.env` 파일은 절대 다른 사람과 공유하거나 깃허브 등에 올리지 마세요.

---

## 2. 실행하기

터미널에서:
```
python3 app.py
```

아래처럼 나오면 성공:
```
브라우저에서 http://localhost:5000 으로 접속하세요.
```

브라우저(크롬 등)를 열고 주소창에 `http://localhost:5000` 을 입력하면 화면이 뜹니다.

## 3. 사용법

1. 상품명 / 가격 입력
2. 상품 사진 업로드 (여러 장 가능, 순서대로 장면에 배치됨)
3. 대본 입력 — **장면을 나누고 싶은 곳에서 엔터를 두 번** (빈 줄)
4. 타입캐스트에서 고른 목소리(Voice ID) 입력 — 비워두면 임시 테스트 음성으로 대체
5. "영상 만들기" 클릭 → 완성되면 미리보기 + 다운로드

## 4. 목소리(Voice ID) 찾는 법

https://typecast.ai/developers/api/voices 에서 마음에 드는 목소리를 고르면
`tc_`로 시작하는 ID를 확인할 수 있어요. 이 값을 화면의 "목소리" 칸에 붙여넣으면 됩니다.

## 5. 종료하기

터미널 창에서 `Ctrl + C`

---

## 알아두면 좋은 것

- 이 프로그램은 **내 컴퓨터 안에서만** 실행돼요. 인터넷에 공개된 사이트가 아니라, 나만 쓸 수 있는 개인용 도구입니다.
- 영상은 `outputs` 폴더 안에 파일로도 저장됩니다.
- 문제가 생기면 터미널 창에 나오는 빨간 글씨(에러 메시지)를 그대로 복사해서 알려주시면 같이 해결할 수 있어요.
