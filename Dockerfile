FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=10000
EXPOSE 10000

# 운영용 서버(gunicorn)로 실행:
# - workers 1개, threads 2개: 무료 서버 메모리(512MB)에 맞춰 최소한으로
# - timeout 600초: AI 영상 생성(Veo)이 몇 분 걸릴 수 있어서 넉넉하게
# - max-requests를 쓰지 않음: Render의 헬스체크(/healthz)가 몇 초마다 들어오는데,
#   이게 요청 수에 포함되면서 워커가 너무 자주 재시작되어 그 안에서 돌던
#   백그라운드 영상 생성 작업까지 중간에 강제 종료되는 문제가 있었음.
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 600"]
