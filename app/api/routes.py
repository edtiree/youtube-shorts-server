import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.api.schemas import (
    JobUploadResponse, ProcessRequest, JobStatusResponse, JobResultsResponse, ShortClip
)
from app.models.job import create_job, get_job, delete_job
from app.utils.file_utils import get_upload_path, get_output_dir, delete_job_files
from app.services.pipeline import run_pipeline
from app.services.video_processor import check_ffmpeg
from app.config import settings

router = APIRouter(prefix="/api")

# Thread pool for background pipeline execution
executor = ThreadPoolExecutor(max_workers=2)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "ffmpeg": check_ffmpeg(),
        "openai_key_set": bool(settings.openai_api_key),
        "anthropic_key_set": bool(settings.anthropic_api_key),
    }


@router.post("/jobs/upload", response_model=JobUploadResponse)
async def upload_video(file: UploadFile = File(...)):
    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식입니다. 지원: {', '.join(ALLOWED_EXTENSIONS)}")

    # Create job
    job = create_job(file.filename)

    # Save file to disk using streaming (supports large files up to 5GB)
    save_path = get_upload_path(job.job_id, file.filename)
    total_bytes = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_bytes += len(chunk)
            # Check size limit during upload
            if total_bytes > settings.max_upload_size_mb * 1024 * 1024:
                f.close()
                save_path.unlink(missing_ok=True)
                delete_job(job.job_id)
                raise HTTPException(400, f"파일 크기가 {settings.max_upload_size_mb}MB를 초과합니다.")
            f.write(chunk)

    file_size_mb = total_bytes / (1024 * 1024)
    job.file_size_mb = round(file_size_mb, 1)

    return JobUploadResponse(
        job_id=job.job_id,
        filename=file.filename,
        status=job.status,
        file_size_mb=job.file_size_mb,
    )


@router.post("/jobs/{job_id}/process")
async def process_video(job_id: str, req: ProcessRequest = ProcessRequest()):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    if job.status not in ("uploaded", "failed"):
        raise HTTPException(400, f"현재 상태에서 처리를 시작할 수 없습니다: {job.status}")

    # Validate API keys
    if not settings.openai_api_key:
        raise HTTPException(400, "OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
    # Anthropic 키는 선택사항 (현재 사용하지 않음)

    job.update_status("processing", "처리 시작...", 5)

    # Run pipeline in background thread
    executor.submit(
        run_pipeline,
        job_id=job_id,
        max_shorts=req.max_shorts,
        min_duration=req.min_duration_sec,
        max_duration=req.max_duration_sec,
    )

    return {"job_id": job_id, "status": "processing"}


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_step=job.current_step,
        error=job.error,
    )


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_results(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    if job.status != "completed":
        raise HTTPException(400, "아직 처리가 완료되지 않았습니다.")

    shorts = []
    for s in (job.shorts or []):
        shorts.append(ShortClip(
            short_id=s["short_id"],
            title=s["title"],
            start_time=s["start_time"],
            end_time=s["end_time"],
            duration=s["duration"],
            virality_score=s["virality_score"],
            reasoning=s["reasoning"],
            hook_text=s["hook_text"],
            download_url=s["download_url"],
        ))

    return JobResultsResponse(
        job_id=job.job_id,
        source_filename=job.filename,
        source_duration=job.source_duration,
        shorts=shorts,
    )


@router.get("/jobs/{job_id}/download/{short_id}")
async def download_short(job_id: str, short_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    if not job.shorts:
        raise HTTPException(404, "생성된 쇼츠가 없습니다.")

    # Find the short by ID
    short_info = None
    for s in job.shorts:
        if s["short_id"] == short_id:
            short_info = s
            break

    if not short_info:
        raise HTTPException(404, "해당 쇼츠를 찾을 수 없습니다.")

    output_dir = get_output_dir(job_id)
    file_path = output_dir / short_info["filename"]

    if not file_path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=f"{short_info['title']}.mp4",
    )


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    delete_job_files(job_id)
    delete_job(job_id)
    return {"ok": True}
