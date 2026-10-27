# Automatic Attain SegFormer analysis

## Current workflow

Upload → save original → persist queued analysis run → single background worker calls the model HTTP API → save class predictions and raw response → mark completed → refresh Recent inspections, details and charts.

Run the dashboard on 127.0.0.1:8010 and `practice_api:app` from the model environment on 127.0.0.1:8020. Restart the model API after code changes: successful responses now include the checkpoint SHA-256, device and prediction timing. The model itself and preprocessing are unchanged.

The Upload & analyze button schedules work automatically; the response does not wait for inference. Existing uploads are not automatically backfilled. Their details offer Analyze and save. Failed runs offer Retry analysis. Completed runs offer Analyze again; each attempt preserves prior history. Duplicate requests while an image is active reuse that attempt. Only the latest run is shown in the main dashboard.

Background-only results are completed runs with zero prediction rows, displayed as No distress predicted. This is not a verified healthy-road assessment. Model Low/High class suffixes remain part of the original label, not overall risk. Confidence, overall risk and condition scores remain null. Pixel fractions represent the fraction of image pixels, not physical area or confidence. Linear crack is not guessed into longitudinal/transverse categories.

Originals are retained if analysis fails or exceeds the 4-million-pixel model limit. A stopped/unavailable model API produces an explicit failed run and a retry action. No authentication, RLS, or bucket policy changes are required. Secrets remain backend-only. Use loopback only until team authentication is added.

## Code map

- `app.py`: saves uploaded originals and schedules analysis; POST `/api/assets/{id}/analyze` schedules manual/retry work and returns 202.
- `analysis_jobs.py`: single-process queue, response validation, durable run/prediction persistence, recovery.
- `test_model_connection.py`: HTTP client used by the queue to call port 8020.
- `../Attain_SegFormer_Portable/practice_api.py`: validates uploaded image then calls the unchanged inference model.
- `../Attain_SegFormer_Portable/test_prediction.py`: model response, checkpoint fingerprint, pixel statistics and timing.
- `storage_backend.py`: reads latest saved results into the dashboard.
- `static/workspace.js`: upload feedback, 2-second polling during queued/processing work, saved results and retry controls.

The earlier `model_adapter.py` / `dashboard_worker.py` subprocess implementation is retained but is no longer used by the dashboard. The guided `/analyze-preview` endpoint remains available in API docs as an unsaved diagnostic; the UI now uses the persistent queue.

## Scope and limitations

Run exactly one dashboard Uvicorn worker. This is a local single-process executor with persisted job state, not a distributed worker queue. On startup its queued runs resume; interrupted processing runs become Failed so they can be retried. Graceful shutdown waits for scheduled work. If the database is unavailable during recovery, fix the connection and restart. A crash during multi-request persistence may leave partial prediction rows attached to a failed run; the dashboard does not display them as completed results.

Current HTTP results save labels, pixel counts/coverage, dimensions, checkpoint fingerprint, device and prediction seconds. The model API does not return mask/overlay files, so this automatic path does not save artifacts yet. It hides artifact links for those runs. Earlier runs with artifacts remain accessible. Adding mask/overlay transfer is separate work.

Predictions still require expert review. The model has missed visible cracks in smoke examples. No model-quality changes or validated accuracy/IoU/precision/recall claims were made.

## Observed local model timings

Earlier benchmark on this Mac CPU with road2.jpg (768 × 512): dependency/model loading 2.470 s, first prediction 0.594 s, median of five repeated predictions 0.444 s (0.425–0.461 s). Prediction includes preprocessing and original-size mask creation, excluding API transfer, storage and file saving. Timings depend on hardware and input.

## Verification

From the dashboard directory:

```bash
.venv/bin/python tests/check_model_integration.py
.venv/bin/python tests/check_supabase_integration.py
```

The first explicitly uploads temporary images and exercises the real model API, completed/background-only runs, saved outputs, protected deletion, simulated outage, retry and duplicate suppression. It removes its own records afterward. The storage test isolates scheduling to verify upload validation, private previews and deletion. Neither test modifies existing user images.
