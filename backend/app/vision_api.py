"""Local-only, bounded upload API and background video analysis jobs."""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .vision_geometry import parse_calibration

router = APIRouter(prefix="/api/vision", tags=["Computer Vision"])
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_STORED_JOBS = 5
_lock = Lock()
_jobs: dict[str, dict[str, Any]] = {}
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="siteobserver-vision")
_root = Path(tempfile.mkdtemp(prefix="siteobserver-vision-"))


def vision_available() -> bool:
    return all(importlib.util.find_spec(package) is not None for package in ("cv2", "ultralytics"))


@router.get("/status")
def status() -> dict[str, Any]:
    available = vision_available()
    return {
        "available": available,
        "mode": "local",
        "message": ("Vision dependencies installed" if available
                    else "Run with compose.vision.yaml to enable YOLO + ByteTrack."),
        "model": "yolo11n.pt",
        "max_upload_mb": 80,
        "max_frames": 150,
        "frame_stride": 4,
        "requires_calibration_for_metric_hazards": True,
    }


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k not in {"path", "directory", "calibration"}}


def _execute_job(job_id: str) -> None:
    from .vision_worker import process_video

    with _lock:
        job = _jobs[job_id]
        job["status"] = "processing"
    try:
        def on_frame(frame: dict[str, Any], percentage: float) -> None:
            with _lock:
                job["frames"].append(frame)
                job["progress_pct"] = percentage

        stats = process_video(job["path"], job["directory"], job["calibration"], on_frame)
        with _lock:
            job["stats"] = stats
            job["status"] = "complete"
            job["progress_pct"] = 100.0
    except Exception as exc:
        with _lock:
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        job["path"].unlink(missing_ok=True)


@router.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    calibration: str | None = Form(default=None),
) -> dict[str, Any]:
    if not vision_available():
        raise HTTPException(503, "Vision is disabled. Start the optional vision Docker configuration.")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Supported video formats: MP4, MOV, AVI, MKV, WEBM.")

    try:
        settings = parse_calibration(calibration)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    with _lock:
        active_count = sum(job["status"] in {"queued", "processing"} for job in _jobs.values())
        if active_count >= 2:
            raise HTTPException(429, "Two jobs are already queued or processing. Try again shortly.")
        finished = [key for key, value in _jobs.items() if value["status"] in {"complete", "failed"}]
        for key in finished[:max(0, len(_jobs) - MAX_STORED_JOBS + 1)]:
            old = _jobs.pop(key)
            shutil.rmtree(old["directory"], ignore_errors=True)
        job_id = uuid.uuid4().hex
        directory = _root / job_id
        directory.mkdir()
        path = directory / ("input" + extension)
        job = {
            "id": job_id, "filename": Path(file.filename or "video").name,
            "status": "queued", "progress_pct": 0.0,
            "error": None, "stats": None, "frames": [],
            "path": path, "directory": directory, "calibration": settings,
        }
        _jobs[job_id] = job

    byte_count = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                byte_count += len(chunk)
                if byte_count > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Video exceeds the 80 MB limit.")
                output.write(chunk)
        if byte_count == 0:
            raise HTTPException(422, "Video is empty.")
    except Exception:
        with _lock:
            _jobs.pop(job_id, None)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await file.close()

    _pool.submit(_execute_job, job_id)
    with _lock:
        return _public_job(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown or expired video analysis job")
        return _public_job(job)


@router.get("/jobs/{job_id}/frames/{frame_index}")
def frame_preview(job_id: str, frame_index: int) -> FileResponse:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown or expired video analysis job")
        if frame_index < 0 or frame_index >= len(job["frames"]):
            raise HTTPException(404, "Frame not available")
        path = job["directory"] / f"frame_{frame_index:04d}.jpg"
    if not path.is_file():
        raise HTTPException(404, "Frame not available")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
