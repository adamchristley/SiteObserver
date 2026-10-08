"""Camera calibration validation and image-only proximity cues.

Uncalibrated pixel overlap is never passed to the meter-based risk engine.
"""
from __future__ import annotations

import json
from math import isfinite
from typing import Any


def _area(points: list[list[float]]) -> float:
    return abs(sum(
        points[i][0] * points[(i + 1) % 4][1]
        - points[(i + 1) % 4][0] * points[i][1]
        for i in range(4)
    )) / 2


def parse_calibration(raw: str | None) -> dict[str, list[list[float]]] | None:
    """Validate ordered pixel to meter correspondences; cv2 computes the matrix later.

    Four points must appear in the SAME clockwise/counterclockwise order.
    """
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Calibration must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Calibration must be a JSON object")
    parsed: dict[str, list[list[float]]] = {}
    for field in ("pixel_points", "world_points"):
        points = data.get(field)
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError(f"{field} must contain exactly four ordered [x, y] points")
        clean = []
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"Invalid {field} coordinate")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in point):
                raise ValueError(f"{field} coordinates must be finite numbers")
            clean.append([float(point[0]), float(point[1])])
        if _area(clean) < 1:
            raise ValueError(f"{field} must define a non-degenerate quadrilateral with area >= 1")
        parsed[field] = clean
    return parsed


def overlap_cues(detections: list[dict[str, Any]], threshold: float = 0.08) -> list[dict[str, Any]]:
    """Flag visual overlap in an image, *not* a collision or physical distance."""
    workers = [d for d in detections if d["label"] == "person"]
    vehicles = [d for d in detections if d["label"] != "person"]
    cues = []
    for w in workers:
        ax1, ay1, ax2, ay2 = w["bbox"]
        for m in vehicles:
            bx1, by1, bx2, by2 = m["bbox"]
            intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(
                0, min(ay2, by2) - max(ay1, by1)
            )
            a_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
            b_area = max(0, bx2 - bx1) * max(0, by2 - by1)
            if min(a_area, b_area) and intersection / min(a_area, b_area) >= threshold:
                cues.append({
                    "category": "image_overlap",
                    "actor_ids": [w["id"], m["id"]],
                    "description": "Overlapping image regions; physical proximity is unknown",
                    "severity": "informational",
                })
    return cues
