from typing import Optional
from pydantic import BaseModel


class JobUploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    file_size_mb: float


class ProcessRequest(BaseModel):
    max_shorts: int = 5
    min_duration_sec: int = 15
    max_duration_sec: int = 58


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress_percent: int
    current_step: str
    error: Optional[str] = None


class ShortClip(BaseModel):
    short_id: str
    title: str
    start_time: float
    end_time: float
    duration: float
    virality_score: int
    reasoning: str
    hook_text: str
    download_url: str


class JobResultsResponse(BaseModel):
    job_id: str
    source_filename: str
    source_duration: float
    shorts: list[ShortClip]
