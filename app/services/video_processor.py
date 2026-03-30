import json
import subprocess
from pathlib import Path
from loguru import logger


def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_video_info(video_path: Path) -> dict:
    """Get video duration, width, height using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(result.stdout)

    video_stream = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    duration = float(probe.get("format", {}).get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0

    return {"duration": duration, "width": width, "height": height}


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    """Extract audio from video as MP3 16kHz mono."""
    logger.info(f"Extracting audio: {video_path} -> {audio_path}")
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        "-q:a", "4",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr[:500]}")

    logger.info(f"Audio extracted: {audio_path} ({audio_path.stat().st_size / 1024 / 1024:.1f}MB)")
    return audio_path


def cut_video_to_short(
    source_path: Path,
    output_path: Path,
    start_time: float,
    end_time: float,
    target_w: int = 1080,
    target_h: int = 1920,
) -> Path:
    """Cut and crop a segment from source video to 9:16 vertical format."""
    logger.info(f"Cutting video: {start_time:.1f}s - {end_time:.1f}s -> {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get source dimensions
    info = get_video_info(source_path)
    src_w = info["width"]
    src_h = info["height"]

    # Calculate crop for 9:16 aspect ratio
    src_aspect = src_w / src_h if src_h > 0 else 16 / 9
    target_aspect = 9 / 16

    if src_aspect > target_aspect:
        # Source is wider → crop sides (most common: 16:9 → 9:16)
        crop_h = src_h
        crop_w = int(src_h * target_aspect)
        crop_w = crop_w - (crop_w % 2)  # Ensure even
        x_offset = (src_w - crop_w) // 2
        y_offset = 0
    else:
        # Source is taller or equal → crop top/bottom
        crop_w = src_w
        crop_h = int(src_w / target_aspect)
        crop_h = crop_h - (crop_h % 2)  # Ensure even
        x_offset = 0
        y_offset = (src_h - crop_h) // 2

    filter_str = f"crop={crop_w}:{crop_h}:{x_offset}:{y_offset},scale={target_w}:{target_h}"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-to", str(end_time),
        "-i", str(source_path),
        "-vf", filter_str,
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg cutting failed: {result.stderr[:500]}")

    logger.info(f"Short created: {output_path}")
    return output_path
