"""
영상 생성 핵심 엔진

흐름:
  1) split_script(script_text)          : 대본 -> 장면(scene) 리스트
  2) generate_narration(text, ...)       : 장면 텍스트 -> 음성 파일(mp3)
  3) build_scene_image(...)              : 상품 이미지 + 자막 -> 한 장면 이미지
  4) render_scene_clip(...)              : 이미지 + 음성 -> 짧은 영상 클립
  5) concat_clips(...)                   : 클립들을 이어붙여 최종 영상 완성
  6) build_video(...)                    : 위 전체를 한 번에 실행하는 진입점
"""
import os
import json
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont

VIDEO_W, VIDEO_H = 1080, 1920
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


# ---------------------------------------------------------------------------
# 1) 대본을 장면 단위로 나누기
# ---------------------------------------------------------------------------
def split_script(script_text: str):
    """빈 줄(엔터 두 번)을 기준으로 장면을 나눈다.
    사용자가 화면 전환을 원하는 곳에 빈 줄을 넣는 방식 (직관적이고 오작동 없음)."""
    raw_scenes = [s.strip() for s in script_text.strip().split("\n\n")]
    scenes = [s for s in raw_scenes if s]
    if not scenes:
        scenes = [script_text.strip()]
    return scenes


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
# 3) 장면 이미지 만들기 (실제 상품 사진 + 자막 오버레이)
# ---------------------------------------------------------------------------
def build_scene_image(product_image_path: str, caption: str, out_path: str,
                       product_name: str = "", price_tag: str = ""):
    canvas = Image.new("RGB", (VIDEO_W, VIDEO_H), (18, 18, 18))

    # 상품 사진을 캔버스 중앙에 맞춰 배치 (비율 유지, 꽉 채우기)
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

    # 상단: 상품명 + 가격 (반투명 바)
    if product_name:
        draw.rectangle([0, 0, VIDEO_W, 160], fill=(0, 0, 0, 140))
        name_font = ImageFont.truetype(FONT_BOLD, 54)
        draw.text((40, 45), product_name, font=name_font, fill=(255, 255, 255, 255))
        if price_tag:
            price_font = ImageFont.truetype(FONT_BOLD, 44)
            draw.text((40, 105), price_tag, font=price_font, fill=(255, 210, 0, 255))

    # 하단: 자막 (자동 줄바꿈)
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

    canvas.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 4) 이미지 + 음성 -> 영상 클립
# ---------------------------------------------------------------------------
def get_duration(media_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", media_path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def render_scene_clip(image_path: str, audio_path: str, out_path: str):
    duration = get_duration(audio_path)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_path,
            "-t", str(duration + 0.3),
            "-r", "30",
            "-vf", f"scale={VIDEO_W}:{VIDEO_H}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
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
            "-c:v", "libx264", "-profile:v", "main", "-level", "3.1",
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
                 api_key: str | None = None, voice_id: str | None = None):
    os.makedirs(work_dir, exist_ok=True)
    scenes = split_script(script_text)

    if not product_images:
        raise ValueError("최소 1장의 상품 이미지가 필요합니다.")

    clip_paths = []
    for idx, caption in enumerate(scenes):
        image_source = product_images[idx % len(product_images)]

        scene_image = os.path.join(work_dir, f"scene_{idx}.png")
        build_scene_image(image_source, caption, scene_image, product_name, price_tag)

        narration_audio = os.path.join(work_dir, f"narration_{idx}.mp3")
        generate_narration(caption, narration_audio, api_key, voice_id)

        clip_path = os.path.join(work_dir, f"clip_{idx}.mp4")
        render_scene_clip(scene_image, narration_audio, clip_path)
        clip_paths.append(clip_path)

    list_file = os.path.join(work_dir, "concat_list.txt")
    concat_clips(clip_paths, list_file, output_path)
    return output_path
