import os
import shutil
import time
from pathlib import Path
from app.config import settings


def get_data_dir() -> Path:
    return Path(settings.data_dir)


def get_job_dir(job_id: str) -> Path:
    return get_data_dir() / job_id


def get_upload_path(job_id: str, filename: str) -> Path:
    job_dir = get_job_dir(job_id)
    upload_dir = job_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / filename


def get_audio_path(job_id: str) -> Path:
    job_dir = get_job_dir(job_id)
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir / "audio.mp3"


def get_transcript_path(job_id: str) -> Path:
    job_dir = get_job_dir(job_id)
    transcript_dir = job_dir / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    return transcript_dir / "transcript.json"


def get_output_dir(job_id: str) -> Path:
    output_dir = get_job_dir(job_id) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_output_path(job_id: str, short_index: int) -> Path:
    return get_output_dir(job_id) / f"short_{short_index}.mp4"


def delete_job_files(job_id: str):
    job_dir = get_job_dir(job_id)
    if job_dir.exists():
        shutil.rmtree(job_dir)


def cleanup_old_jobs(max_age_hours: int = 24):
    data_dir = get_data_dir()
    if not data_dir.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    for item in data_dir.iterdir():
        if item.is_dir() and item.stat().st_mtime < cutoff:
            shutil.rmtree(item)


def ensure_data_dirs():
    get_data_dir().mkdir(parents=True, exist_ok=True)
