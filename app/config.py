from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Whisper settings
    whisper_model: str = "whisper-1"
    whisper_language: Optional[str] = None

    # Claude settings
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # Video processing
    max_upload_size_mb: int = 5120
    output_resolution_w: int = 1080
    output_resolution_h: int = 1920
    video_crf: int = 23
    video_preset: str = "medium"

    # Shorts parameters
    default_max_shorts: int = 5
    default_min_duration: int = 15
    default_max_duration: int = 58

    # Paths
    data_dir: str = "data"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
