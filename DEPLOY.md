# 웹사이트로 배포하기 (무료, Render.com 사용)

코딩 없이, 계정 가입과 클릭만으로 진짜 인터넷 주소를 가진 사이트를 만드는 과정이에요.
처음 한 번만 하면 되고, 그다음부터는 그 주소로 계속 접속하면 됩니다.

**필요한 계정 2개**: GitHub(코드 저장소), Render(서버 호스팅) — 둘 다 무료.

---

## 1단계. GitHub에 코드 올리기

1. [github.com](https://github.com) 접속 → 계정 없으면 가입 (이메일만 있으면 됨)
2. 로그인 후 오른쪽 위 **+** 버튼 → **New repository** 클릭
3. Repository name: `coupang-video-app` 입력 → **Create repository** 클릭
4. 새로 생긴 빈 페이지에서 **"uploading an existing file"** 링크 클릭
5. 압축 풀어놓은 `coupang_video_app` 폴더 안의 **모든 파일과 폴더**를 통째로 끌어다 놓기 (드래그 앤 드롭)
   - `.env` 파일은 올리지 마세요 (없어도 정상 — 키는 다음 단계에서 안전하게 따로 등록해요)
6. 아래 **Commit changes** 버튼 클릭

이제 내 코드가 인터넷에 저장됐어요 (아직 사이트로 켜진 건 아니에요).

---

## 2단계. Render에서 서버 켜기

1. [render.com](https://render.com) 접속 → **Get Started** → **GitHub 계정으로 가입/로그인**
2. 대시보드에서 **New +** → **Web Service** 클릭
3. 방금 만든 `coupang-video-app` 저장소 선택 → **Connect**
4. 설정 화면에서:
   - **Name**: 원하는 이름 (예: my-coupang-video)
   - **Instance Type**: **Free** 선택
   - (Dockerfile을 자동으로 인식해서 나머지는 그대로 두면 됩니다)
5. 아래로 스크롤 → **Environment Variables** 항목에서 **Add Environment Variable** 클릭
   - Key: `TYPECAST_API_KEY`
   - Value: 발급받은 본인의 타입캐스트 API 키
6. **Create Web Service** 클릭

5~10분 정도 기다리면 (화면에 로그가 주르륵 올라감) 상단에
`https://my-coupang-video.onrender.com` 같은 주소가 생겨요.

**이 주소가 이제 내 웹사이트예요.** 북마크해두고 언제든 접속하면 됩니다.

---

## 알아두면 좋은 것 (무료 요금제 특성)

- 아무도 안 쓰다가 오랜만에 접속하면, 서버가 "잠들어" 있어서 첫 화면이 뜨는 데 30초~1분 정도 걸릴 수 있어요. (그다음부터는 빠름)
- 영상 생성은 몇 분 걸릴 수 있는 작업이라, 이미지 개수/대본 길이가 너무 길면 무료 서버 사양상 시간이 걸리거나 실패할 수 있어요. 이 경우 유료 플랜(월 몇천 원대)으로 올리면 훨씬 안정적이에요.
- 코드를 수정하고 싶으면: GitHub 저장소에서 파일을 다시 업로드(덮어쓰기)하면 Render가 자동으로 재배포해줘요.

---

## 막히면

이 과정 중 어느 화면에서든 캡처해서 보여주시면, 그 화면 기준으로 바로 다음에 뭘 눌러야 하는지 알려드릴게요.
