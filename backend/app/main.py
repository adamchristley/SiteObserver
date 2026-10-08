"""FastAPI app. Runs offline with simulated data; no Azure credentials needed."""
from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import Incident, SiteSnapshot
from .simulator import SiteSimulator

app = FastAPI(title="SiteObserver API", version="0.1.0",
              description="Research-only simulated construction hazard monitoring.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
simulator = SiteSimulator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "simulation"}


@app.get("/api/site", response_model=SiteSnapshot)
def site() -> SiteSnapshot:
    return simulator.snapshot()


@app.get("/api/incidents", response_model=list[Incident])
def incidents(limit: int = Query(default=30, ge=1, le=250)) -> list[Incident]:
    return simulator.incidents(limit=limit)
