# SiteObserver

**Construction-site safety intelligence research prototype** built with FastAPI, Python, React, TypeScript, and a local-first architecture designed for an eventual Azure deployment.

> **Status: v0.2, local video analysis.** The synthetic site simulator remains available. Optional YOLO11 + ByteTrack can now analyze recorded footage. The pretrained model is not construction-specific, and no cloud resources have been deployed. **This is not a certified workplace safety system.**

## Demo features

- Interactive overhead site map with selectable workers, excavator, and haul truck.
- Deterministic synthetic motion with real positions (meters), velocity estimates, and restricted-zone definitions.
- Baseline hazard detector for current unsafe proximity, projected close approaches over a four-second constant-velocity horizon, and restricted-zone entry.
- Incident history recorded on new hazards and severity transitions, with a bounded in-memory event log.
- Live metrics, risk trend, pause/resume dashboard polling, service status, and accessible incident table.
- A typed REST API with automatic OpenAPI documentation.
- Optional recorded-video analysis using YOLO11n object detection + ByteTrack object IDs.\n- Annotated frame review, confidence scores, detections, and optional calibrated ground-plane projections.\n- Automated Python tests, frontend type checking, Docker Compose, and GitHub Actions CI.

### System architecture

```text
          Local synthetic trajectories (meters, m/s)
                             |
                   FastAPI / Python engine
                        /           \
                Risk evaluation    Incident log
                        \           /
                        REST API endpoints
                      /api/site  /api/incidents
                             |
                     React / TypeScript UI
                 Live map · alerts · trend · events
```

**Important:** The four-second closest-approach calculation uses constant-velocity extrapolation, not a machine-learned accident predictor. Proximity thresholds are **illustrative research defaults**, not approved safety limits. Camera pixel coordinates must be calibrated to world units before this method can be used with footage.

## Start with Docker (easiest)

Requirements: Docker Desktop with Compose.

```bash
git clone https://github.com/adamchristley/SiteObserver.git
cd SiteObserver
docker compose up --build
```

Then open:

- Dashboard: http://localhost:5173
- API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Docker Compose runs entirely on your own machine. **No Azure account, cloud subscription, or payment method is necessary.** Stop with `Ctrl+C`. Run `docker compose down` to remove the application containers.

## Milestone 2: optional local video analysis

Default `docker compose up --build` remains lightweight and starts the
simulator/dashboard without ML packages. To enable video analysis:

1. Stop the running stack with `Ctrl+C`.
2. Run the **opt-in vision Docker configuration** from the repository root:

```bash
git pull
docker compose -f compose.yaml -f compose.vision.yaml up --build
```

3. Open http://localhost:5173 and select **Video analysis** in the sidebar.
4. Upload a video (MP4/H.264 recommended, maximum 80 MB). The first analysis
   automatically downloads the free `yolo11n.pt` weights. No cloud account,
   API key, credit card, or paid deployment is required.

**Performance:** The optional image runs inference on your **CPU** by default.
Its first Docker build installs PyTorch and other large dependencies, so allow
disk space and download time. Each job processes at most **150 sampled frames**
(every fourth source frame), approximately the first 20 seconds at 30 FPS.
Frames are intentionally downsampled to limit local processing cost.

**Privacy and persistence:** Uploaded video is processed on the local backend
and the original is deleted when its analysis finishes. Up to five recent jobs
and their preview JPEG frames are retained in a temporary server directory.
They are not automatically deleted until older jobs are purged or the Docker
container is removed. Never upload confidential or identifiable footage
without authorization. This endpoint has no authentication and is intended
for localhost, **not** a public deployment.

**Important limitations:**
- The bundled COCO YOLO11n model detects **person, car, bus, and truck**.
  It does not recognize excavators, forklifts, PPE, or construction-specific
  activity without additional training.
- Without calibration, the dashboard reports **image-plane overlap cues**
  only. It does **not** call them actual collision risk.
- For an approximate metric screening experiment, expand the camera
  calibration section and supply four correspondences of image pixels to
  measured ground-plane meters (both ordered identically). The worker/vehicle
  bottom-center is projected through a homography; this assumes a fixed
  camera and an approximately flat ground plane. **Any** resulting proximity
  warnings are unvalidated research estimates, not safety-critical alerts.
- Videos are processed as bounded jobs with playback of sampled images.
  Live webcam streaming and construction-specific fine-tuning are future work.

**Licensing:** The optional Ultralytics package and associated YOLO models
are AGPL-3.0 licensed. Review its requirements before redistributing or
commercializing the complete project. Do not assume the open-source
dependencies permit use in a closed-source product without a license.

## Run without Docker

Requirements: Python 3.11+, Node.js 20+, npm.

**Terminal 1: API**

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2: Dashboard**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

To point the frontend to another API host, create `frontend/.env.local`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Keep the frontend and backend hosts aligned with the development CORS configuration in `backend/app/main.py`.

## Tests

```bash
cd backend
python -m pytest -q
```

```bash
cd frontend
npm run build
```

CI runs both on GitHub for pushes and pull requests.

## REST API

| Endpoint | Description |
| --- | --- |
| `GET /health` | API status and operating mode |
| `GET /api/site` | One timestamped site snapshot with positions, risk events and telemetry |
| `GET /api/incidents?limit=30` | Most recent incident transitions, up to 250 |

The server advances simulation time on snapshot requests. Incident history is per server process and resets when the API restarts. Data is **not persisted** in v0.1.

## Repository layout

```text
SiteObserver/
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI routes
│   │   ├── models.py       # Pydantic contracts
│   │   ├── risk.py         # Hazard rules and closest approach
│   │   ├── simulator.py    # Trajectories and incident transitions\n│   │   ├── vision_api.py   # Bounded upload job/preview API\n│   │   ├── vision_worker.py# YOLO + ByteTrack optional processing\n│   │   └── vision_geometry.py # Calibration and image-only cues
│   ├── tests/              # Risk and REST contract tests
│   └── Dockerfile
├── compose.vision.yaml     # Opt-in local CPU inference\n├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Dashboard and site map
│   │   ├── api.ts          # Typed API client
│   │   ├── types.ts        # Contracts
│   │   └── styles.css      # Responsive visual system
│   └── Dockerfile
├── compose.yaml
└── .github/workflows/ci.yml
```

## Roadmap

- [x] Repository foundation and Docker Compose
- [x] Synthetic site telemetry
- [x] Geometric risk engine with unit tests
- [x] Interactive operational dashboard
- [ ] Persist incident history in a local database
- [x] Local recorded-video object detection and ByteTrack review (general COCO classes)\n- [ ] Fine-tune on public construction datasets for PPE and equipment classes
- [x] Optional four-point homography input to approximate world positions\n- [ ] Evaluate and validate calibration on measured footage
- [ ] Benchmark alerts using held-out annotated near-miss scenarios
- [ ] Compare temporal prediction models against the geometric baseline
- [ ] Optional Azure Static Web Apps deployment and carefully controlled serverless services
- [ ] Performance benchmarks, demo recording, and reproducible experiment report

## Zero-dollar cloud policy

This repository does **not** create Azure infrastructure and contains no subscription credentials or cloud API keys. Future Azure deployments must be explicitly opt-in, target verified free tiers or a **credit-limited Azure for Students** account, and avoid any pay-as-you-go upgrade. A budget alert is not a spending cap.

## Research and ethical limitations

SiteObserver is an engineering and research demonstration. Synthetic risk events are **not** evidence of real accident-prediction accuracy. Do not claim validated incident prediction, deploy as a safety-critical alarm, or use identifiable construction-worker footage without authorization. Verify dataset licenses and publication rights with the REU supervisor before adding video, learned weights, or research data.

## License

No license has been granted yet. Repository contents remain under the default copyright terms until the owner chooses a license.
