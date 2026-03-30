from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from app.api.routes import router
from app.utils.file_utils import ensure_data_dirs, cleanup_old_jobs
from app.services.video_processor import check_ffmpeg


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("YouTube Shorts Maker 시작 중...")
    ensure_data_dirs()
    cleanup_old_jobs()

    if not check_ffmpeg():
        logger.warning("⚠️  FFmpeg가 설치되지 않았습니다! 'brew install ffmpeg'로 설치해주세요.")
    else:
        logger.info("FFmpeg 확인 완료")

    yield
    # Shutdown
    logger.info("서버 종료")


app = FastAPI(
    title="YouTube Shorts Maker",
    description="영상에서 자동으로 바이럴 쇼츠를 추출합니다",
    lifespan=lifespan,
)

# CORS (editree 프론트엔드 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")
