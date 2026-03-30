import uuid
from pathlib import Path
from typing import Optional
from loguru import logger

from app.models.job import Job, get_job
from app.utils.file_utils import (
    get_upload_path, get_audio_path, get_transcript_path, get_output_path
)
from app.services.video_processor import extract_audio, cut_video_to_short, get_video_info
from app.services.transcription import transcribe_audio
from app.services.analyzer import analyze_transcript


def run_pipeline(
    job_id: str,
    max_shorts: int = 5,
    min_duration: int = 15,
    max_duration: int = 58,
):
    """Run the full processing pipeline for a job."""
    job = get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    try:
        source_path = _find_source(job)
        if not source_path:
            job.fail("소스 영상 파일을 찾을 수 없습니다.")
            return

        # Step 1: Get video info
        info = get_video_info(source_path)
        job.source_duration = info["duration"]
        logger.info(f"Video: {info['width']}x{info['height']}, {info['duration']:.1f}s")

        # Step 2: Extract audio
        job.update_status("extracting_audio", "오디오 추출 중...", 10)
        audio_path = get_audio_path(job_id)
        extract_audio(source_path, audio_path)

        # Step 3: Transcribe
        job.update_status("transcribing", "음성 인식 중 (Whisper)...", 30)
        transcript_path = get_transcript_path(job_id)
        transcript = transcribe_audio(audio_path, transcript_path)
        job.transcript = transcript

        if not transcript:
            job.fail("음성 인식 결과가 비어있습니다. 영상에 음성이 있는지 확인해주세요.")
            return

        # Step 4: Analyze with Claude
        job.update_status("analyzing", "AI 분석 중 (Claude)...", 55)
        segments = analyze_transcript(
            transcript=transcript,
            filename=job.filename,
            duration=job.source_duration,
            max_shorts=max_shorts,
            min_duration=min_duration,
            max_duration=max_duration,
        )
        job.segments = segments

        if not segments:
            job.fail("바이럴 가능성이 높은 구간을 찾지 못했습니다.")
            return

        # Step 5: Cut videos
        job.update_status("cutting", "영상 자르는 중...", 70)
        shorts = []
        total = len(segments)
        for i, seg in enumerate(segments):
            progress = 70 + int((i / total) * 25)
            job.update_status("cutting", f"영상 자르는 중... ({i+1}/{total})", progress)

            output_path = get_output_path(job_id, i)
            cut_video_to_short(
                source_path=source_path,
                output_path=output_path,
                start_time=seg["start_time"],
                end_time=seg["end_time"],
            )

            short_id = str(uuid.uuid4())[:8]
            shorts.append({
                "short_id": short_id,
                "title": seg["title"],
                "start_time": seg["start_time"],
                "end_time": seg["end_time"],
                "duration": round(seg["end_time"] - seg["start_time"], 1),
                "virality_score": seg["virality_score"],
                "reasoning": seg["reasoning"],
                "hook_text": seg["hook_text"],
                "filename": output_path.name,
                "download_url": f"/api/jobs/{job_id}/download/{short_id}",
            })

        job.shorts = shorts
        job.update_status("completed", "완료!", 100)
        logger.info(f"Pipeline complete: {len(shorts)} shorts created for job {job_id}")

    except Exception as e:
        logger.exception(f"Pipeline error for job {job_id}")
        job.fail(f"처리 중 오류가 발생했습니다: {str(e)}")


def _find_source(job: Job) -> Optional[Path]:
    """Find the uploaded source video file."""
    from app.utils.file_utils import get_job_dir
    upload_dir = get_job_dir(job.job_id) / "uploads"
    if not upload_dir.exists():
        return None
    for f in upload_dir.iterdir():
        if f.is_file():
            return f
    return None
