# YOLO11s detection integration

New uploads use the YOLO11s API on `127.0.0.1:8020`. The dashboard FastAPI service runs on `127.0.0.1:8010`. The older SegFormer checkpoint and historical results remain separate and readable; reanalysis creates a new YOLO run without rewriting past results.

## Request and saved data

1. `POST /api/upload-images` saves the original in private Supabase Storage and creates an inspection/media record.
2. `analysis_jobs.enqueue` inserts a queued `analysis_runs` row with `task_type=detection`, then submits one local background job.
3. The job downloads the original and `test_model_connection.request_analysis_bytes` sends it to the YOLO API.
4. `YOLO11s_Pavement/api.py` loads the checkpoint once at server startup. Its `POST /analyze` returns class summaries and per-box labels, confidence, coordinates, original image dimensions, timing, and checkpoint fingerprint. It runs on CPU with confidence 0.10, NMS IoU 0.50, and input size 960.
5. The dashboard validates the response before writing one `predictions` row per box, including `geometry.xyxy` in original-image pixels. It stores the complete structured response in `analysis_runs.raw_output` and marks the run completed. A no-detection result has zero prediction rows and is still completed.
6. `storage_backend.list_assets` gives Recent inspections and details the latest run. The box preview endpoint draws the saved coordinates on the private original on demand, without rerunning YOLO or storing a second image. The crack chart counts distinct labels once per image.

Failed runs retain originals and an error message. Retry starts a new run, preserving history. Duplicate clicks during an active run share its ID. On restart, queued YOLO work resumes and interrupted processing becomes failed for an explicit retry. Run only one dashboard Uvicorn worker.

No database migration is needed: the existing `analysis_runs.task_type='detection'`, `predictions.confidence`, `predictions.geometry`, and `raw_output` fields hold the YOLO result. The existing private buckets and backend-only secret remain unchanged.

## Interpretation

The current YOLO class 0 is **Crack**. The older SegFormer class 0 was **Background**; the dashboard handles them by model label, so Crack is never discarded. YOLO has no longitudinal/transverse or severity classes. Its detection confidence is not distress severity or road risk. The supplied experimental inverse-box score is not PCI and is not used in the dashboard. An empty result does not confirm healthy pavement. All predictions await expert review.

The four reported validation metrics in the supplied package have not been independently reproduced: precision 58.32%, recall 72.67%, mAP@50 63.45%, mAP@50:95 50.21%. The original validation images, labels, and full evaluation run are absent from the ZIP.

## Verification

From `transportation_dashboard`, with both services and configured Supabase available:

```bash
.venv/bin/python tests/check_model_integration.py
```

The test uploads its own sample and blank image, confirms saved YOLO detections, geometry, confidence, the generated box preview, a completed empty result, outage handling, retry, duplicate suppression, and cleanup. It needs the locally supplied checkpoint and sample image at `YOLO11s_Pavement/samples/Roadimage1.jpg`; neither is committed. `tests/check_supabase_integration.py` separately checks storage setup.
