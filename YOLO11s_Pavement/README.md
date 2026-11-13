# YOLO11s pavement detector

This folder hosts the supplied YOLO11s detection checkpoint for the local road distress dashboard. The checkpoint belongs at `weights/best.pt` and is excluded from the public source repository. The original `predict_and_score_together.py` is retained for research reference; the dashboard runs `api.py` so the model loads once and handles one image per request.

## Setup and run

From this folder:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8020
```

Use `requirements.txt` if the macOS-tested lockfile has incompatible wheels on another platform. Keep the dashboard in its own environment on port 8010. The model runs on CPU as in the supplied inference script.

The API accepts a JPEG, PNG, or WebP image at `POST /analyze` and returns class labels, bounding boxes in original-image pixels, per-box confidence, checkpoint SHA-256, image dimensions, timing, and inference settings. It uses confidence 0.10, NMS IoU 0.50, and input size 960. Uploaded images must be at most 20 MiB and 4 million pixels.

Checkpoint labels verified locally: `Crack`, `Pothole`, `Patched crack`, `Patched pothole`, `Clay-patched crack`, `Manhole`. Class ID 0 is **Crack**. No class distinguishes longitudinal from transverse cracking or gives severity. The checkpoint must have exactly this class mapping; the service refuses to start otherwise.

The original supplied ZIP also contains an experimental inverse bounding-box coverage index. It is **not a validated pavement condition index (PCI)** and the dashboard does not report it as road condition.

The project team reported validation precision 58.32%, recall 72.67%, mAP@50 63.45%, and mAP@50:95 50.21%. The ZIP does not include the full validation inputs and logs required to reproduce those metrics independently; see [ORIGINAL_REPORTED_METRICS.md](ORIGINAL_REPORTED_METRICS.md). No new accuracy claim follows from this integration test.
