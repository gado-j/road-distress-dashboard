# Quick start: road distress dashboard

Open the main project folder in VS Code, then open two terminals. These commands assume each terminal starts in that folder. Complete the [first-time setup](README.md) if either `.venv` is missing.

## Terminal 1: YOLO model API

```bash
cd YOLO11s_Pavement
source .venv/bin/activate
python -m uvicorn api:app --host 127.0.0.1 --port 8020
```

The supplied checkpoint belongs at `YOLO11s_Pavement/weights/best.pt`. Wait for **Application startup complete**. If an older SegFormer server already uses port 8020, stop it with Ctrl+C first. Use only one model server at a time.

## Terminal 2: dashboard

```bash
cd transportation_dashboard
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Wait for **Application startup complete**, then open http://127.0.0.1:8010/ in your browser. Leave both terminals running. To stop, press Ctrl+C in each.

If you start inside `transportation_dashboard`, use `cd ../YOLO11s_Pavement` to reach the model folder. `pwd` shows your current directory.

## Upload and inspect

1. Select **Upload images**, choose a JPEG, PNG, or WebP image, and click **Upload & analyze**.
2. Open **Overview → Recent inspections**. The dashboard saves the original and queues analysis automatically.
3. Wait for **Completed**, then open the image. Details show YOLO labels, detection counts, per-box confidence, and an image with saved boxes drawn over the original.
4. A failed run keeps the original. Fix the cause and click **Retry analysis**. Older records can be analyzed again with YOLO from their details.

## Export analyzed results

Open **Reports** in the sidebar, choose the dates when analysis completed, and select **Open report**. The new tab shows each image's latest saved completed run in that period, its original, annotated result, and model labels. Select **Print / Save as PDF** and choose **Save as PDF** in the browser print dialog. Dates use Central Time. The date range can span up to one year; if it contains more than 200 completed runs, choose a shorter range. The report excludes pending, failed, and unsaved preview results.

The dashboard accepts up to ten images per upload, at most 20 MiB each. Analysis accepts at most 4 million pixels per image. It processes one image at a time. An empty detection result does not prove the pavement is free of distress.

## What happens behind the scenes

```text
Browser upload
  → dashboard :8010 saves original in private Supabase Storage
  → dashboard saves queued analysis run in Supabase Postgres
  → one background worker sends original bytes to YOLO API :8020
  → YOLO detects boxes at 960-pixel inference size, with confidence 0.10 and NMS IoU 0.50
  → API returns labels, confidence, boxes in original-image pixel coordinates
  → dashboard saves each detection and completes the run
  → Recent inspections, image details, and crack chart update
```

The four TxDOT crack patterns remain separate from YOLO's broader **Crack**, **Patched crack**, and **Clay-patched crack** labels. YOLO does not classify severity or longitudinal/transverse direction. The ZIP's experimental index is not a validated PCI score and is not shown as road condition.

The older SegFormer model remains in the project for historical results. The new YOLO API is the model used for new uploads and reanalysis.

## If something fails

| Symptom | Check |
|---|---|
| Dashboard cannot open | Terminal 2 is listening on 8010. |
| Analysis fails or model cannot be reached | Terminal 1 is running `api:app` from `YOLO11s_Pavement` on 8020; then click Retry. |
| Database unavailable | Check the dashboard's ignored `.env.local`, internet connection, and http://127.0.0.1:8010/api/health. Do not share the secret key. |
| Address already in use | Stop the older server in its terminal before starting another on that port. |
| Model says Not Found at `/` | Expected. Open http://127.0.0.1:8020/docs. |
| No boxes on a visibly damaged image | Record the case for the model team; a completed run is not proof of model accuracy. |

For dependency installation and Supabase setup, see [README.md](README.md). The full integration details are in [MODEL_INTEGRATION.md](transportation_dashboard/MODEL_INTEGRATION.md).
