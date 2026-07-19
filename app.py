import os
import uuid
import json
import time
import threading
import traceback
from flask import Flask, request, render_template, send_from_directory, flash, redirect, url_for, Response
from PIL import Image

from video_engine import build_video, is_video_file

MAX_IMAGE_DIMENSION = 960  # 이보다 큰 사진은 자동으로 줄여서 메모리 사용량을 낮춘다 (무료 서버 512MB 대응)
JOB_STALE_SECONDS = 8 * 60  # 이 시간 넘게 "처리 중"이면 실패한 것으로 간주 (무한 대기 방지)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "local-dev-only"  # 개인 로컬 실행용이라 간단하게 둠
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024  # 요청 전체 최대 80MB (메모리 보호용)

# ---------------------------------------------------------------------------
# 작업 상태 저장: 메모리가 아니라 "디스크 파일"에 기록한다.
# 이유: 처리 도중 서버 프로세스가 재시작되면(메모리 부족 등) 메모리에 저장했던
# 진행 상태는 통째로 사라지지만, 디스크 파일은 프로세스가 바뀌어도 그대로 남아있다.
# ---------------------------------------------------------------------------
def job_status_path(job_id):
    return os.path.join(UPLOAD_DIR, job_id, "status.json")


def write_job_status(job_id, data):
    path = job_status_path(job_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)  # 원자적 교체 (쓰다가 중간에 깨지는 것 방지)


def read_job_status(job_id):
    path = job_status_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["_updated_at"] = os.path.getmtime(path)
        return data
    except Exception:
        return None

# .env 파일이 있으면 읽어서 환경변수로 등록 (python-dotenv 없이 직접 처리)
def load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

load_env_file()

# ---------------------------------------------------------------------------
# 접근 제한: 나 혼자만 쓸 수 있도록 아이디/비밀번호로 잠금
# .env 에 SITE_PASSWORD 를 설정하면 잠금이 켜짐 (설정 안 하면 잠금 없이 접근 가능)
# ---------------------------------------------------------------------------
SITE_USER = os.environ.get("SITE_USER", "admin")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD")


def check_auth(username, password):
    return username == SITE_USER and password == SITE_PASSWORD


def require_login():
    return Response(
        "로그인이 필요합니다.", 401,
        {"WWW-Authenticate": 'Basic realm="Scene Maker"'},
    )


@app.route("/healthz")
def healthz():
    # Render가 서버 생존 확인용으로 주기적으로 찌르는 경로. 비밀번호 없이 항상 200을 반환해야 함.
    return "OK", 200


@app.before_request
def restrict_access():
    if request.path == "/healthz":
        return  # 헬스체크는 잠금 예외
    if not SITE_PASSWORD:
        return  # 비밀번호 미설정 시 잠금 없음 (로컬 개인 실행 기본값)
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return require_login()


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


def process_job(job_id, script_text, saved_image_paths, product_name, price_tag,
                 api_key, voice_id, gemini_api_key):
    """백그라운드 스레드에서 실제 영상 생성을 수행하고 결과를 디스크에 기록."""
    work_dir = os.path.join(UPLOAD_DIR, job_id, "work")
    output_filename = f"video_{job_id}.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    try:
        build_video(
            script_text=script_text,
            product_images=saved_image_paths,
            product_name=product_name,
            price_tag=price_tag,
            work_dir=work_dir,
            output_path=output_path,
            api_key=api_key,
            voice_id=voice_id,
            gemini_api_key=gemini_api_key,
        )
        write_job_status(job_id, {"status": "done", "video_filename": output_filename})
    except Exception as e:
        traceback.print_exc()
        write_job_status(job_id, {"status": "error", "error": str(e)})


@app.route("/generate", methods=["POST"])
def generate():
    product_name = request.form.get("product_name", "").strip()
    price_tag = request.form.get("price_tag", "").strip()
    script_text = request.form.get("script", "").strip()
    voice_id = request.form.get("voice_id", "").strip() or None

    api_key = os.environ.get("TYPECAST_API_KEY") or None
    gemini_api_key = os.environ.get("GEMINI_API_KEY") or None

    if not script_text:
        flash("대본을 입력해주세요.")
        return redirect(url_for("index"))

    images = request.files.getlist("product_images")
    images = [img for img in images if img and img.filename]
    has_ai_scene = "[AI:" in script_text.upper() or "[ai:" in script_text

    if not images and not has_ai_scene:
        flash("상품 사진/영상을 최소 1개 업로드하거나, 대본에 [AI: ...] 장면을 넣어주세요.")
        return redirect(url_for("index"))

    job_id = uuid.uuid4().hex[:10]
    job_upload_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_upload_dir, exist_ok=True)

    saved_image_paths = []
    for i, img in enumerate(images):
        ext = os.path.splitext(img.filename)[1] or ".jpg"
        save_path = os.path.join(job_upload_dir, f"product_{i}{ext}")
        img.save(save_path)

        # 사진(영상 아님)이고, 너무 크면 메모리 절약을 위해 축소해서 다시 저장
        if not is_video_file(save_path):
            try:
                with Image.open(save_path) as im:
                    im = im.convert("RGB")
                    if max(im.size) > MAX_IMAGE_DIMENSION:
                        im.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
                    im.save(save_path, quality=88, optimize=True)
            except Exception as e:
                print(f"[경고] 이미지 축소 실패, 원본 그대로 사용: {e}")

        saved_image_paths.append(save_path)

    # 스레드를 시작하기 "전에" 먼저 디스크에 상태를 기록해둔다.
    # (스레드 시작 직후 프로세스가 죽더라도 최소한 "처리 시작함" 기록은 남게 하기 위함)
    write_job_status(job_id, {"status": "processing"})

    thread = threading.Thread(
        target=process_job,
        args=(job_id, script_text, saved_image_paths, product_name, price_tag,
              api_key, voice_id, gemini_api_key),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("job_status", job_id=job_id))


@app.route("/status/<job_id>")
def job_status(job_id):
    job = read_job_status(job_id)

    if job is None:
        flash("존재하지 않는 작업이에요. 다시 시도해주세요.")
        return redirect(url_for("index"))

    if job["status"] == "processing":
        elapsed = time.time() - job.get("_updated_at", time.time())
        if elapsed > JOB_STALE_SECONDS:
            flash("영상 생성이 예상보다 오래 걸리고 있어요. 서버가 재시작되었을 수 있으니 다시 시도해주세요.")
            return redirect(url_for("index"))
        return render_template("processing.html", job_id=job_id)
    elif job["status"] == "error":
        flash(f"영상 생성 중 오류가 발생했습니다: {job['error']}")
        return redirect(url_for("index"))
    else:
        return render_template("result.html", video_filename=job["video_filename"])


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    is_local = os.environ.get("PORT") is None
    if is_local:
        print(f"\n브라우저에서 http://localhost:{port} 으로 접속하세요.\n")
    app.run(host="0.0.0.0", port=port, debug=is_local)
