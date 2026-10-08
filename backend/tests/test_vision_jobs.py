"""API upload limits and local processing behavior without downloading models."""
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_oversized_upload_is_rejected_without_creating_job(monkeypatch):
    import app.vision_api as vision
    monkeypatch.setattr(vision, "vision_available", lambda: True)
    monkeypatch.setattr(vision, "MAX_UPLOAD_BYTES", 4)
    with client:
        response = client.post(
            "/api/vision/jobs",
            files={"file": ("test.mp4", b"12345678", "video/mp4")},
        )
    assert response.status_code == 413


def test_queued_job_can_complete_with_stubbed_worker(monkeypatch):
    import app.vision_api as vision
    import app.vision_worker as worker

    monkeypatch.setattr(vision, "vision_available", lambda: True)

    def fake_process(source, output, calibration, on_frame):
        assert source.is_file()
        assert calibration is None
        (output / "frame_0000.jpg").write_bytes(b"fake-jpeg")
        on_frame({
            "index": 0, "source_frame": 0, "time_s": 0,
            "detections": [], "hazards": [], "cues": [],
        }, 50)
        return {"frames_analyzed": 1, "calibrated": False}

    monkeypatch.setattr(worker, "process_video", fake_process)
    response = client.post(
        "/api/vision/jobs",
        files={"file": ("test.mp4", b"fake sample", "video/mp4")},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        result = client.get(f"/api/vision/jobs/{job_id}").json()
        if result["status"] in {"complete", "failed"}:
            break
        time.sleep(.01)
    assert result["status"] == "complete", result.get("error")
    assert result["stats"]["frames_analyzed"] == 1
    assert result["frames"][0]["index"] == 0
    preview = client.get(f"/api/vision/jobs/{job_id}/frames/0")
    assert preview.status_code == 200
    assert preview.content == b"fake-jpeg"
    assert client.get(f"/api/vision/jobs/{job_id}/frames/1").status_code == 404
