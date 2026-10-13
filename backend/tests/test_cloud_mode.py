"""The public Azure simulation configuration should expose no upload endpoints."""
import os
import subprocess
import sys
from pathlib import Path


def test_simulation_only_mode_hides_video_routes():
    backend_dir = Path(__file__).resolve().parents[1]
    env = dict(os.environ, SITEOBSERVER_SIMULATION_ONLY="1")
    script = """
from app.main import app
paths = {route.path for route in app.routes}
assert "/health" in paths
assert "/api/site" in paths
assert "/api/incidents" in paths
assert not any(path.startswith("/api/vision/") for path in paths)
assert "/api/vision/camera/frame" not in paths
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
