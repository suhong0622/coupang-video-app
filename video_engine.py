"""
영상 생성 핵심 엔진

흐름:
  1) split_script(script_text)          : 대본 -> 장면(scene) 리스트
  2) generate_narration(text, ...)       : 장면 텍스트 -> 음성 파일(mp3)
  3) build_scene_image(...)              : 상품 "사진" + 자막 -> 한 장면 이미지
     build_caption_overlay(...)          : 상품 "영상" 위에 얹을 투명 자막 오버레이
  4) render_scene_clip(...)              : 사진 + 음성 -> 짧은 영상 클립
     render_video_scene_clip(...)        : 완성된 영상 클립(제미나이 Veo 등) + 음성 -> 짧은 영상 클립
  5) concat_clips(...)                   : 클립들을 이어붙여 최종 영상 완성
  6) build_video(...)                    : 위 전체를 한 번에 실행하는 진입점
     (장면별 미디어가 사진인지 영상인지 자동으로 구분해서 처리)
"""
import os
import json
import mimetypes
import subprocess
import textwrap
import time
import re
import gc
from PIL import Image, ImageDraw, ImageFont

VIDEO_W, VIDEO_H = 1080, 1920
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv"}


# ---------------------------------------------------------------------------
# 1) 대본을 장면 단위로 나누기
# ---------------------------------------------------------------------------
AI_TAG_PATTERN = re.compile(r"^\[\s*AI\s*[:：]\s*(.+?)\s*\]$")


def split_script(script_text: str):
    """빈 줄(엔터 두 번)을 기준으로 장면을 나눈다.
    각 장면의 첫 줄이 '[AI: 프롬프트]' 형식이면, 그 장면은 사진/영상 업로드 대신
    Veo(제미나이) AI가 그 프롬프트로 새 영상을 생성하도록 표시한다.

    반환값: [{"caption": str, "ai_prompt": str|None}, ...]
    """
    raw_blocks = [b.strip() for b in script_text.strip().split("\n\n")]
    raw_blocks = [b for b in raw_blocks if b]
    if not raw_blocks:
        raw_blocks = [script_text.strip()]

    scenes = []
    for block in raw_blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        ai_prompt = None
        if lines:
            m = AI_TAG_PATTERN.match(lines[0])
            if m:
                ai_prompt = m.group(1)
                lines = lines[1:]
        caption = " ".join(lines) if lines else (ai_prompt or "")
        scenes.append({"caption": caption, "ai_prompt": ai_prompt})
    return scenes


def is_video_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return True
    guessed, _ = mimetypes.guess_type(path)
    return bool(guessed and guessed.startswith("video/"))


# ---------------------------------------------------------------------------
# 2) 나레이션 음성 생성
# ---------------------------------------------------------------------------
def generate_narration_typecast(text: str, out_path: str, api_key: str, voice_id: str):
    """타입캐스트 공식 Python SDK를 사용해 음성 생성.
    사전 준비: pip install typecast-python
    """
    from typecast import Typecast
    from typecast.models import TTSRequest

    client = Typecast(api_key=api_key)
    response = client.text_to_speech(TTSRequest(
        text=text,
        model="ssfm-v30",
        voice_id=voice_id,
        language="kor",
    ))
    with open(out_path, "wb") as f:
        f.write(response.audio_data)
    return out_path


def generate_narration_fallback(text: str, out_path: str):
    """타입캐스트 키가 없을 때를 위한 임시 대체 (오프라인 espeak-ng).
    품질은 낮지만 파이프라인 테스트/데모용으로 사용."""
    wav_path = out_path.replace(".mp3", ".wav")
    subprocess.run(
        ["espeak-ng", "-v", "ko", "-s", "150", text, "-w", wav_path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, out_path],
        check=True, capture_output=True,
    )
    return out_path


def generate_narration(text: str, out_path: str, api_key: str | None, voice_id: str | None):
    if api_key and voice_id:
        try:
            return generate_narration_typecast(text, out_path, api_key, voice_id)
        except Exception as e:
            print(f"[경고] 타입캐스트 호출 실패, 임시 음성으로 대체합니다: {e}")
    return generate_narration_fallback(text, out_path)


# ---------------------------------------------------------------------------
# 3-A) 장면 이미지 만들기 (실제 상품 "사진" + 자막 오버레이, 배경까지 포함)
# ---------------------------------------------------------------------------
def _draw_caption_layer(draw, caption: str, product_name: str, price_tag: str):
    """상품명/가격 상단바 + 하단 자막을 그리는 공통 로직 (사진/영상 공용)."""
    if product_name:
        draw.rectangle([0, 0, VIDEO_W, 160], fill=(0, 0, 0, 140))
        name_font = ImageFont.truetype(FONT_BOLD, 54)
        draw.text((40, 45), product_name, font=name_font, fill=(255, 255, 255, 255))
        if price_tag:
            price_font = ImageFont.truetype(FONT_BOLD, 44)
            draw.text((40, 105), price_tag, font=price_font, fill=(255, 210, 0, 255))

    caption_font = ImageFont.truetype(FONT_BOLD, 58)
    wrapped = textwrap.wrap(caption, width=16)
    line_h = 74
    block_h = line_h * len(wrapped) + 60
    y0 = VIDEO_H - block_h - 120
    draw.rectangle([0, y0, VIDEO_W, VIDEO_H - 120], fill=(0, 0, 0, 170))
    y = y0 + 30
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=caption_font)
        w = bbox[2] - bbox[0]
        x = (VIDEO_W - w) // 2
        draw.text((x, y), line, font=caption_font, fill=(255, 255, 255, 255))
        y += line_h


def build_scene_image(product_image_path: str, caption: str, out_path: str,
                       product_name: str = "", price_tag: str = ""):
    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), (18, 18, 18))

    product_img = Image.open(product_image_path).convert("RGB")
    canvas_ratio = VIDEO_W / VIDEO_H
    img_ratio = product_img.width / product_img.height
    if img_ratio > canvas_ratio:
        new_h = VIDEO_H
        new_w = int(new_h * img_ratio)
    else:
        new_w = VIDEO_W
        new_h = int(new_w / img_ratio)
    product_img = product_img.resize((new_w, new_h))
    left = (new_w - VIDEO_W) // 2
    top = (new_h - VIDEO_H) // 2
    product_img = product_img.crop((left, top, left + VIDEO_W, top + VIDEO_H))
    canvas.paste(product_img, (0, 0))

    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_caption_layer(draw, caption, product_name, price_tag)

    canvas.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 3-B) 완성된 "영상" 클립 위에 얹을 투명 자막 오버레이 (PNG, 알파 채널)
# ---------------------------------------------------------------------------
def build_caption_overlay(caption: str, out_path: str,
                           product_name: str = "", price_tag: str = ""):
    overlay = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    _draw_caption_layer(draw, caption, product_name, price_tag)
    overlay.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 3-C) AI로 새 영상 장면 생성 (Google Veo 3.1, Gemini API)
# ---------------------------------------------------------------------------
def generate_ai_scene_video(prompt: str, out_path: str, api_key: str,
                             reference_image_path: str | None = None,
                             model: str = "veo-3.1-fast-generate-preview",
                             aspect_ratio: str = "9:16"):
    """제미나이 API(Veo 3.1)로 텍스트/이미지 -> 영상을 생성한다.
    - api_key: Google AI Studio에서 발급받은 Gemini API 키 (구독과는 별개, 종량제 과금)
    - reference_image_path: 상품 일관성을 위해 함께 넣을 참고 이미지 (선택)
    - 생성에 최소 11초 ~ 최대 6분 정도 걸릴 수 있음 (Google 공식 문서 기준)
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    kwargs = {
        "model": model,
        "prompt": prompt,
        "config": types.GenerateVideosConfig(aspect_ratio=aspect_ratio),
    }

    if reference_image_path and not is_video_file(reference_image_path):
        with open(reference_image_path, "rb") as f:
            image_bytes = f.read()
        mime_type = mimetypes.guess_type(reference_image_path)[0] or "image/jpeg"
        kwargs["image"] = types.Image(image_bytes=image_bytes, mime_type=mime_type)

    operation = client.models.generate_videos(**kwargs)

    # 영상 생성은 시간이 오래 걸리는 비동기 작업이라, 완료될 때까지 주기적으로 확인한다.
    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)

    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    generated_video.video.save(out_path)
    return out_path



def get_duration(media_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", media_path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def render_scene_clip(image_path: str, audio_path: str, out_path: str):
    """정적 사진 한 장 + 음성 -> 클립."""
    duration = get_duration(audio_path)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-t", str(duration + 0.3),
            "-r", "30",
            "-vf", f"scale={VIDEO_W}:{VIDEO_H}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-shortest",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return out_path


def render_video_scene_clip(video_path: str, overlay_path: str, audio_path: str, out_path: str):
    """완성된 영상 클립(제미나이/Veo 등으로 만든 것) + 자막 오버레이 + 나레이션 음성 -> 클립.
    - 영상은 세로 캔버스(1080x1920)에 꽉 차도록 스케일/크롭
    - 나레이션 길이에 맞춰 영상을 반복 재생(짧으면) 또는 잘라냄(길면)
    - 원본 영상의 소리는 빼고, 우리가 만든 나레이션 음성으로 교체 (전체 영상의 목소리 톤을 통일하기 위함)
    """
    duration = get_duration(audio_path)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", video_path,
            "-i", overlay_path,
            "-i", audio_path,
            "-t", str(duration + 0.3),
            "-filter_complex",
            (
                f"[0:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_W}:{VIDEO_H}[bg];"
                f"[bg][1:v]overlay=0:0[outv]"
            ),
            "-map", "[outv]", "-map", "2:a",
            "-r", "30",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-shortest",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return out_path


# ---------------------------------------------------------------------------
# 5) 클립 합치기
# ---------------------------------------------------------------------------
def concat_clips(clip_paths, list_file_path, final_path):
    with open(list_file_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file_path,
            "-r", "30", "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-profile:v", "main", "-level", "3.1",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart",
            final_path,
        ],
        check=True, capture_output=True,
    )
    return final_path


# ---------------------------------------------------------------------------
# 6) 전체 파이프라인 진입점
# ---------------------------------------------------------------------------
def build_video(script_text: str, product_images: list[str], product_name: str,
                 price_tag: str, work_dir: str, output_path: str,
                 api_key: str | None = None, voice_id: str | None = None,
                 gemini_api_key: str | None = None):
    os.makedirs(work_dir, exist_ok=True)
    scenes = split_script(script_text)

    has_ai_scene = any(s["ai_prompt"] for s in scenes)
    has_uploaded_media = bool(product_images)
    if not has_uploaded_media and not has_ai_scene:
        raise ValueError("최소 1개의 상품 사진/영상을 올리거나, 대본에 [AI: ...] 장면을 넣어주세요.")
    if has_ai_scene and not gemini_api_key:
        raise ValueError("대본에 [AI: ...] 장면이 있는데, 제미나이(Gemini) API 키가 설정되어 있지 않습니다.")

    # AI로 생성할 장면에 참고 이미지로 쓸 상품 사진 (첫 번째 '사진' 하나를 기준으로 삼음)
    reference_image = next((p for p in product_images if not is_video_file(p)), None)

    clip_paths = []
    media_idx = 0  # 업로드된 사진/영상은 AI 장면을 건너뛰고 순서대로 배정됨
    for idx, scene in enumerate(scenes):
        caption = scene["caption"]
        ai_prompt = scene["ai_prompt"]

        narration_audio = os.path.join(work_dir, f"narration_{idx}.mp3")
        generate_narration(caption, narration_audio, api_key, voice_id)

        clip_path = os.path.join(work_dir, f"clip_{idx}.mp4")
        overlay_path = os.path.join(work_dir, f"overlay_{idx}.png")

        if ai_prompt:
            ai_video_path = os.path.join(work_dir, f"ai_scene_{idx}.mp4")
            generate_ai_scene_video(ai_prompt, ai_video_path, gemini_api_key,
                                     reference_image_path=reference_image)
            build_caption_overlay(caption, overlay_path, product_name, price_tag)
            render_video_scene_clip(ai_video_path, overlay_path, narration_audio, clip_path)
        else:
            if not has_uploaded_media:
                raise ValueError(f"{idx+1}번째 장면에 쓸 사진/영상이 없습니다.")
            media_source = product_images[media_idx % len(product_images)]
            media_idx += 1
            if is_video_file(media_source):
                build_caption_overlay(caption, overlay_path, product_name, price_tag)
                render_video_scene_clip(media_source, overlay_path, narration_audio, clip_path)
            else:
                scene_image = os.path.join(work_dir, f"scene_{idx}.png")
                build_scene_image(media_source, caption, scene_image, product_name, price_tag)
                render_scene_clip(scene_image, narration_audio, clip_path)

        clip_paths.append(clip_path)
        gc.collect()  # 장면마다 즉시 메모리 정리 (무료 서버 메모리 한도 대응)

    list_file = os.path.join(work_dir, "concat_list.txt")
    concat_clips(clip_paths, list_file, output_path)
    return output_path
