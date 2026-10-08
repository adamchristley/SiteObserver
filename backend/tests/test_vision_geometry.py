import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.vision_geometry import overlap_cues, parse_calibration

client = TestClient(app)


def test_uncalibrated_does_not_infer_metric_distance():
    assert parse_calibration(None) is None
    a = {"id": "w-1", "label": "person", "bbox": [0, 0, 20, 20]}
    b = {"id": "v-1", "label": "truck", "bbox": [10, 10, 30, 30]}
    cues = overlap_cues([a, b])
    assert cues[0]["category"] == "image_overlap"
    assert "physical proximity is unknown" in cues[0]["description"]


def test_distant_boxes_produce_no_visual_cue():
    assert not overlap_cues([
        {"id": "w-1", "label": "person", "bbox": [0, 0, 10, 10]},
        {"id": "v-1", "label": "truck", "bbox": [50, 50, 60, 60]},
    ])


def test_four_point_calibration_accepted():
    data = {
        "pixel_points": [[0, 0], [640, 0], [640, 480], [0, 480]],
        "world_points": [[0, 0], [20, 0], [20, 15], [0, 15]],
    }
    assert parse_calibration(json.dumps(data))["world_points"][2] == [20, 15]


@pytest.mark.parametrize("calibration", [
    "{invalid", "[]", '{"pixel_points":[]}', json.dumps({
        "pixel_points": [[0,0]] * 4,
        "world_points": [[0,0],[20,0],[20,15],[0,15]],
    }),
])
def test_invalid_calibration_rejected(calibration):
    with pytest.raises(ValueError):
        parse_calibration(calibration)


def test_vision_status_is_accessible_without_optional_dependencies():
    response = client.get("/api/vision/status")
    assert response.status_code == 200
    assert response.json()["requires_calibration_for_metric_hazards"] is True


def test_upload_invalid_file_type(monkeypatch):
    monkeypatch.setattr("app.vision_api.vision_available", lambda: True)
    response = client.post(
        "/api/vision/jobs",
        files={"file": ("unsafe.txt", b"not a video", "text/plain")},
    )
    assert response.status_code == 415


def test_job_not_found():
    assert client.get("/api/vision/jobs/nonexistent").status_code == 404
