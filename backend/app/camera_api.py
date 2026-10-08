"""Experimental local webcam frame sampling via a single YOLO + ByteTrack tracker.

No images persist on disk. One active camera session is supported per process.
"""
from __future__ import annotations

import base64
import os
import uuid
from threading import Lock
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from .vision_api import vision_available
from .vision_geometry import overlap_cues

router = APIRouter(prefix="/api/vision/camera", tags=["Computer Vision"])
MAX_FRAME_BYTES = 2 * 1024 * 1024
_lock = Lock()
_model: Any = None
_active_session: str | None = None


def _infer_frame(image_bytes: bytes, session: str) -> dict[str, Any]:
    import cv2
    import numpy as np
    from ultralytics import YOLO

    global _model, _active_session

    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.ndim != 3:
        raise ValueError("Cannot decode JPEG image")
    height, width = frame.shape[:2]
    if min(width, height) < 16 or width > 1920 or height > 1080:
        raise ValueError("Camera frame dimensions out of range")

    with _lock:
        if _model is None or session != _active_session:
            _model = YOLO(os.getenv("SITEOBSERVER_YOLO_MODEL", "yolo11n.pt"))
            _active_session = session
        model = _model
        result = model.track(
            frame, persist=True, tracker="bytetrack.yaml",
            classes=[0, 2, 5, 7], conf=0.25, imgsz=640,
            verbose=False, device=os.getenv("SITEOBSERVER_DEVICE", "cpu"),
        )[0]
        detections = []
        boxes = result.boxes
        if boxes is not None:
            ids = boxes.id.int().cpu().tolist() if boxes.id is not None else []
            for index, (cls_id, conf, coords) in enumerate(zip(
                boxes.cls.int().cpu().tolist(),
                boxes.conf.cpu().tolist(),
                boxes.xyxy.cpu().tolist(),
            )):
                label = str(model.names[cls_id])
                if label not in {"person", "car", "bus", "truck"}:
                    continue
                box = [round(float(p), 1) for p in coords]
                track_id = ids[index] if index < len(ids) else None
                label_id = f"{label[0]}-{track_id}" if track_id is not None else f"untracked-{index}"
                detections.append({
                    "id": label_id,
                    "track_id": track_id,
                    "label": label,
                    "confidence": round(float(conf), 3),
                    "bbox": box,
                })
                x1, y1, x2, y2 = [int(p) for p in box]
                color = (140, 229, 170) if label == "person" else (105, 188, 240)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, f"{label} {label_id} {conf:.0%}",
                            (x1, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.56, color, 2, cv2.LINE_AA)
        ok, image = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if not ok:
            raise ValueError("Could not encode camera preview")
        return {
            "image_base64": base64.b64encode(image.tobytes()).decode("ascii"),
            "detections": detections,
            "cues": overlap_cues(detections),
            "calibrated": False,
            "width": width,
            "height": height,
        }


@router.post("/frame")
async def camera_frame(
    file: UploadFile = File(...),
    session_id: str = Form(...),
) -> dict[str, Any]:
    if not vision_available():
        raise HTTPException(503, "Vision is disabled. Enable the optional local vision image.")
    try:
        session_id = str(uuid.UUID(session_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, "Invalid camera session ID") from exc
    if file.content_type not in {"image/jpeg", "image/jpg"}:
        raise HTTPException(415, "Camera upload must be a JPEG image")
    try:
        frame = await file.read(MAX_FRAME_BYTES + 1)
    finally:
        await file.close()
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise HTTPException(413, "Frame must be a nonempty JPEG no larger than 2 MB")
    try:
        return await run_in_threadpool(_infer_frame, frame, session_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
