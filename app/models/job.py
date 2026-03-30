import uuid
import time
from typing import Optional


class Job:
    def __init__(self, filename: str):
        self.job_id: str = str(uuid.uuid4())
        self.filename: str = filename
        self.status: str = "uploaded"
        self.current_step: str = "대기 중"
        self.progress_percent: int = 0
        self.error: Optional[str] = None
        self.created_at: float = time.time()
        self.source_duration: float = 0.0
        self.file_size_mb: float = 0.0
        self.transcript: Optional[list] = None
        self.segments: Optional[list] = None
        self.shorts: Optional[list] = None

    def update_status(self, status: str, step: str, progress: int):
        self.status = status
        self.current_step = step
        self.progress_percent = progress

    def fail(self, error: str):
        self.status = "failed"
        self.error = error

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "status": self.status,
            "current_step": self.current_step,
            "progress_percent": self.progress_percent,
            "error": self.error,
            "created_at": self.created_at,
            "source_duration": self.source_duration,
            "file_size_mb": self.file_size_mb,
        }


# In-memory job store
_jobs: dict[str, Job] = {}


def create_job(filename: str) -> Job:
    job = Job(filename)
    _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def delete_job(job_id: str) -> bool:
    if job_id in _jobs:
        del _jobs[job_id]
        return True
    return False


def list_jobs() -> list[Job]:
    return list(_jobs.values())
