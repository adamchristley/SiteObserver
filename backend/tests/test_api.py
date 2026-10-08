from fastapi.testclient import TestClient

from app.main import app
from app.simulator import SiteSimulator, make_actors

client = TestClient(app)


def test_health():
    result = client.get("/health")
    assert result.status_code == 200
    assert result.json() == {"status": "ok", "mode": "simulation"}


def test_site_contract():
    response = client.get("/api/site")
    assert response.status_code == 200
    site = response.json()
    assert site["mode"] == "simulation"
    assert site["people_on_site"] == 4
    assert site["equipment_active"] == 2
    assert len(site["zones"]) == 2
    assert all(h["actor_ids"] for h in site["hazards"])


def test_invalid_incident_limit():
    assert client.get("/api/incidents?limit=0").status_code == 422


def test_incident_transition_deduplication():
    time = [0.0]
    sim = SiteSimulator(clock=lambda: time[0])
    first = sim.snapshot()
    second = sim.snapshot()
    assert first.incidents_total == second.incidents_total
    assert second.incidents_total == len(sim.incidents())


def test_simulated_coordinates_within_site():
    for timestamp in (0, 10, 100, 400):
        for entity in make_actors(timestamp):
            assert 0 <= entity.x <= 80
            assert 0 <= entity.y <= 50
