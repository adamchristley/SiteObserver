# SiteObserver video-analysis design notes

## What is and is not inferred

1. YOLO11n gives `person`, `car`, `bus`, and `truck` detections from COCO.
2. ByteTrack associates supported detections between processed frames when IDs are available. Samples are every fourth frame.
3. Without a camera calibration, only **image-region overlaps** are displayed. This is not a collision or physical-distance estimate.
4. With optional manually measured pixel-to-world ground-plane correspondences, the bounding-box bottom-center is projected to approximate ground-plane coordinates (meters) using a four-point homography.
5. A constant-velocity closest-approach calculation can then apply the existing **research-only** distance thresholds. These outputs are not validated safety metrics. Perspective error, occlusions, ID switches, camera movement, and non-planar objects can all cause serious errors.

## Model, tracker, and limits

- Ultralytics `yolo11n.pt` pretrained model, `bytetrack.yaml`, confidence threshold 0.25, 640 px inference size.
- Model downloads on first analysis unless a local model path is specified using `SITEOBSERVER_YOLO_MODEL`.
- CPU inference by default via `SITEOBSERVER_DEVICE=cpu`; GPU builds require an independent PyTorch CUDA and container runtime setup.
- Upload limit: 80 MiB. Recognized extensions: MP4, MOV, AVI, MKV, WEBM. Decoder compatibility depends on OpenCV and FFmpeg support in the optional image.
- Job queue: one worker, maximum two queued/running jobs.
- Frame budget: maximum 150 processed frames, one per four decoded frames.
- Five stored jobs maximum. Original uploads are removed after processing. Annotation frames remain temporarily and are removed with discarded jobs or container deletion.
- Runs only on localhost. The API lacks production authentication and deployment hardening.

## Reproduce locally

From repository root, stop the default Docker Compose stack with Ctrl+C and run:

```bash
git pull
docker compose -f compose.yaml -f compose.vision.yaml up --build
```

Visit http://localhost:5173, open **Video analysis**, choose a video file, and click **Analyze video**. The first model download and CPU inference may take a while.

## Tests and next steps

Run unit tests without the heavy computer vision packages:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The test suite exercises upload restrictions, job state, camera calibration JSON validation, overlap cues, and the original simulator/risk engine. It mocks the optional heavy inference process; actual YOLO accuracy and end-to-end performance must be evaluated on real labeled construction data.

Suggested research evaluation: choose a license-compatible construction dataset, establish a held-out split by *video/site*, fine-tune construction-specific categories, compare AP/mAP against pretrained baselines, then report IDF1, HOTA, temporal event detection recall, false alarms/hour, and system throughput. No such benchmark results are claimed yet.

## Licensing

The optional Ultralytics YOLO implementation and pretrained weights carry AGPL-3.0 obligations. Read the [Ultralytics license](https://www.ultralytics.com/license) before releasing the full app commercially or keeping derivative code closed-source.
