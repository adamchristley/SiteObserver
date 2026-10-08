"""Optional local computer vision worker.

The Ultralytics and OpenCV packages are imported only when a user enables vision.
Model weights download from official Ultralytics resources on first use.
"""
from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .models import Actor
from .risk import evaluate
from .vision_geometry import overlap_cues

ALLOWED_CLASSES = [0, 2, 5, 7]  # COCO person, car, bus, truck
MAX_FRAMES = 150
FRAME_STRIDE = 4


def pixel_to_world(
    foot_x: float, foot_y: float, matrix: Any, cv2: Any, np: Any
) -> tuple[float, float]:
    pixel = np.array([[[foot_x, foot_y]]], dtype=np.float64)
    mapped = cv2.perspectiveTransform(pixel, matrix)[0][0]
    return float(mapped[0]), float(mapped[1])


def process_video(
    source: Path,
    output_dir: Path,
    calibration: dict[str, list[list[float]]] | None,
    on_frame: Callable[[dict[str, Any], float], None],
) -> dict[str, Any]:
    import cv2
    import numpy as np
    from ultralytics import YOLO

    output_dir.mkdir(parents=True, exist_ok=True)
    model_name = os.getenv("SITEOBSERVER_YOLO_MODEL", "yolo11n.pt")
    device = os.getenv("SITEOBSERVER_DEVICE", "cpu")
    model = YOLO(model_name)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        raise ValueError("OpenCV could not decode this video. Try an H.264 MP4 file.")

    matrix = None
    if calibration is not None:
        matrix = cv2.getPerspectiveTransform(
            np.array(calibration["pixel_points"], dtype=np.float32),
            np.array(calibration["world_points"], dtype=np.float32),
        )
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 1 <= fps <= 240:
        fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0 or width * height > 4096 * 2160:
        cap.release()
        raise ValueError("Unsupported video dimensions (maximum 4096 x 2160).")

    start = perf_counter()
    processed = 0
    decoded = 0
    previous: dict[str, tuple[float, float, float]] = {}
    all_ids: set[str] = set()
    observed_cues = 0
    observed_hazards = 0
    try:
        while processed < MAX_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            frame_index = decoded
            decoded += 1
            if frame_index % FRAME_STRIDE:
                continue

            result = model.track(
                frame, persist=True, tracker="bytetrack.yaml",
                classes=ALLOWED_CLASSES, conf=0.25, imgsz=640,
                verbose=False, device=device,
            )[0]
            boxes = result.boxes
            items: list[dict[str, Any]] = []
            actors: list[Actor] = []
            now = frame_index / fps
            if boxes is not None:
                # Track IDs can be absent for low-confidence/unassociated boxes.
                ids = boxes.id.int().cpu().tolist() if boxes.id is not None else []
                classes = boxes.cls.int().cpu().tolist()
                confs = boxes.conf.cpu().tolist()
                coords = boxes.xyxy.cpu().tolist()
                for index, (class_id, confidence, coords4) in enumerate(zip(classes, confs, coords)):
                    if class_id not in ALLOWED_CLASSES:
                        continue
                    label = str(model.names[class_id])
                    if label not in {"person", "car", "bus", "truck"}:
                        continue
                    x1, y1, x2, y2 = [round(float(v), 1) for v in coords4]
                    track_id = ids[index] if index < len(ids) else None
                    stable_id = f"{'w' if label == 'person' else 'v'}-{track_id}" if track_id is not None else f"untracked-{processed}-{index}"
                    item = {
                        "id": stable_id, "track_id": track_id, "label": label,
                        "confidence": round(float(confidence), 3),
                        "bbox": [x1, y1, x2, y2],
                    }
                    items.append(item)
                    if track_id is not None:
                        all_ids.add(stable_id)

                    if matrix is None:
                        continue
                    # Bottom center of the bounding box approximates contact
                    # with the ground plane for a fixed calibrated camera.
                    wx, wy = pixel_to_world((x1 + x2) / 2, y2, matrix, cv2, np)
                    if not np.isfinite([wx, wy]).all():
                        continue
                    vx = vy = 0.0
                    if stable_id in previous:
                        px, py, pt = previous[stable_id]
                        dt = now - pt
                        if dt > 0:
                            vx, vy = (wx - px) / dt, (wy - py) / dt
                    if track_id is not None:
                        previous[stable_id] = (wx, wy, now)
                    actors.append(Actor(
                        id=stable_id,
                        kind="worker" if label == "person" else "truck",
                        label=f"{label.title()} {stable_id}",
                        x=wx, y=wy, vx=vx, vy=vy,
                    ))

            hazards = [h.model_dump() for h in evaluate(actors, [])] if matrix is not None else []
            cues = overlap_cues(items) if matrix is None else []
            observed_hazards += len(hazards)
            observed_cues += len(cues)

            for item in items:
                x1, y1, x2, y2 = [int(v) for v in item["bbox"]]
                color = (140, 229, 170) if item["label"] == "person" else (105, 188, 240)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                caption = f"{item['label']} {item['id']} {item['confidence']:.0%}"
                cv2.putText(frame, caption, (x1, max(16, y1 - 7)),
                            cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2, cv2.LINE_AA)

            file_name = f"frame_{processed:04d}.jpg"
            # Bounded preview resolution keeps disk/memory usage manageable.
            preview = cv2.resize(frame, (960, round(height * 960 / width))) if width > 960 else frame
            if not cv2.imwrite(str(output_dir / file_name), preview, [cv2.IMWRITE_JPEG_QUALITY, 78]):
                raise RuntimeError("Could not write preview frame")
            data = {
                "index": processed,
                "source_frame": frame_index,
                "time_s": round(now, 2),
                "detections": items,
                "hazards": hazards,
                "cues": cues,
            }
            processed += 1
            on_frame(data, min(99.0, processed / MAX_FRAMES * 100))
    finally:
        cap.release()

    if not processed:
        raise ValueError("Video contained no decodable frames.")
    return {
        "model": model_name,
        "device": device,
        "fps_source": round(fps, 2),
        "width": width,
        "height": height,
        "frames_analyzed": processed,
        "source_frames_read": decoded,
        "duration_analyzed_s": round((decoded - 1) / fps, 2),
        "processing_s": round(perf_counter() - start, 2),
        "unique_tracked_objects": len(all_ids),
        "hazard_observations": observed_hazards,
        "visual_overlap_observations": observed_cues,
        "calibrated": calibration is not None,
        "disclaimer": (
            "Calibration supplied: rough geometric screening only, not validated safety alerts."
            if calibration is not None
            else "Image-only detections. Visual overlap does not imply physical proximity or collision."
        ),
    }
