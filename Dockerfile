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
# - max-requests: 일정 요청마다 워커를 자동으로 재시작해서 메모리 누적을 방지
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 2 --timeout 600 --max-requests 20 --max-requests-jitter 5"]
