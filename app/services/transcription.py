import json
import math
import subprocess
from pathlib import Path
from openai import OpenAI
from loguru import logger
from app.config import settings


def transcribe_audio(audio_path: Path, transcript_path: Path) -> list[dict]:
    """Transcribe audio using OpenAI Whisper API. Returns list of segments."""
    logger.info(f"Transcribing: {audio_path}")

    client = OpenAI(api_key=settings.openai_api_key, timeout=300.0)
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    if file_size_mb > 25:
        segments = _transcribe_large_audio(client, audio_path)
    else:
        segments = _transcribe_single(client, audio_path)

    # Save transcript
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

    logger.info(f"Transcription complete: {len(segments)} segments")
    return segments


def _transcribe_single(client: OpenAI, audio_path: Path) -> list[dict]:
    """Transcribe a single audio file under 25MB."""
    logger.info(f"Transcribing file: {audio_path} ({audio_path.stat().st_size / 1024:.0f}KB)")
    try:
        import httpx
        custom_http = httpx.Client(timeout=httpx.Timeout(300.0, connect=60.0))
        client_with_timeout = OpenAI(api_key=client.api_key, http_client=custom_http)
        with open(audio_path, "rb") as f:
            response = client_with_timeout.audio.transcriptions.create(
                model=settings.whisper_model,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                **({"language": settings.whisper_language} if settings.whisper_language else {}),
            )
    except Exception as e:
        logger.error(f"Whisper API error: {type(e).__name__}: {e}")
        raise

    segments = []
    for seg in response.segments:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
    return segments


def _transcribe_large_audio(client: OpenAI, audio_path: Path) -> list[dict]:
    """Split audio into chunks and transcribe each."""
    logger.info("Audio > 25MB, splitting into chunks...")

    # Get audio duration
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json", str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    duration = float(json.loads(result.stdout)["format"]["duration"])

    chunk_duration = 1200  # 20 minutes
    overlap = 30  # 30 seconds overlap
    all_segments = []
    chunk_dir = audio_path.parent / "chunks"
    chunk_dir.mkdir(exist_ok=True)

    num_chunks = math.ceil(duration / (chunk_duration - overlap))
    logger.info(f"Splitting into {num_chunks} chunks")

    for i in range(num_chunks):
        start = max(0, i * (chunk_duration - overlap))
        end = min(duration, start + chunk_duration)
        chunk_path = chunk_dir / f"chunk_{i}.mp3"

        # Extract chunk
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-to", str(end),
            "-i", str(audio_path),
            "-acodec", "libmp3lame",
            "-ar", "16000", "-ac", "1",
            str(chunk_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)

        # Transcribe chunk
        chunk_segments = _transcribe_single(client, chunk_path)

        # Offset timestamps and deduplicate
        for seg in chunk_segments:
            seg["start"] += start
            seg["end"] += start

            # Skip segments that overlap with already processed ones
            if all_segments and seg["start"] < all_segments[-1]["end"] - 1:
                continue
            all_segments.append(seg)

        # Cleanup chunk
        chunk_path.unlink(missing_ok=True)

    chunk_dir.rmdir()
    return all_segments
