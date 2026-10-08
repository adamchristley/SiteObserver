"""Webcam API contract tests without installing ML dependencies."""
import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_webcam_mode_requires_opt_in_dependencies(monkeypatch):
    monkeypatch.setattr("app.camera_api.vision_available", lambda: False)
    response = client.post(
        "/api/vision/camera/frame",
        files={"file": ("frame.jpg", b"jpeg-data", "image/jpeg")},
        data={"session_id": str(uuid.uuid4())},
    )
    assert response.status_code == 503


def test_camera_frame_validates_session_and_type(monkeypatch):
    monkeypatch.setattr("app.camera_api.vision_available", lambda: True)
    bad_id = client.post(
        "/api/vision/camera/frame",
        files={"file": ("frame.jpg", b"jpeg-data", "image/jpeg")},
        data={"session_id": "bad-id"},
    )
    assert bad_id.status_code == 422

    bad_type = client.post(
        "/api/vision/camera/frame",
        files={"file": ("frame.png", b"png-data", "image/png")},
        data={"session_id": str(uuid.uuid4())},
    )
    assert bad_type.status_code == 415


def test_camera_frame_bounded_upload(monkeypatch):
    monkeypatch.setattr("app.camera_api.vision_available", lambda: True)
    monkeypatch.setattr("app.camera_api.MAX_FRAME_BYTES", 2)
    response = client.post(
        "/api/vision/camera/frame",
        files={"file": ("frame.jpg", b"12345", "image/jpeg")},
        data={"session_id": str(uuid.uuid4())},
    )
    assert response.status_code == 413
