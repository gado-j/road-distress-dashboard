# Road Distress Dashboard

A local FastAPI application for uploading road images, detecting pavement distress with a supplied YOLO11s checkpoint, and reviewing saved results. The responsive dashboard works on laptops and phones. This repository distributes source code; it is not a hosted service.

Already configured? Use the [short daily run guide](QUICK_START.md).

## Current workflow

Upload an image → save its original in private Supabase Storage → create a queued analysis run → send the image to the local YOLO API → save bounding boxes, labels and confidence in Supabase Postgres → show the result in Recent inspections, image details and charts. Failed analysis retains the original and can be retried. Older SegFormer results remain readable; reanalysis creates a new YOLO run.

The **Reports** page filters completed analyses by completion date in Central Time. It opens a printable report with each image's latest saved result, original, and annotated model output. Use the browser's **Save as PDF** print destination to export it.

Features include searchable inspections, original-image previews, a saved detection-box preview, upload counts by month/quarter/year, and a cracking-label donut with Central Time filters. Upload accepts multiple direct images or a ZIP archive; non-image and invalid entries are skipped, while valid images follow the usual analysis pipeline. The donut keeps TxDOT's four flexible-pavement patterns distinct from broader model labels such as **Crack** and **Linear crack**.

## Requirements

- Python 3.12, Git and internet access for dependencies and Supabase. The current environments were tested on macOS; Windows/Linux packages may differ.
- A Supabase project with the [seven application tables](transportation_dashboard/supabase/schema.sql) and two private Storage buckets.
- The supplied YOLO checkpoint at `YOLO11s_Pavement/weights/best.pt`. Weights are **not in this repository**; obtain them from the project team. The model API verifies that the checkpoint has the expected detection task and six class names.
- Two terminals: one for the model API on `127.0.0.1:8020`, one for the dashboard on `127.0.0.1:8010`. Both run in separate Python environments.

## First-time setup

Clone the repository:

```bash
git clone https://github.com/gado-j/road-distress-dashboard.git
cd road-distress-dashboard
```

Create the YOLO environment from the repository root:

```bash
cd YOLO11s_Pavement
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

The lockfile records the tested macOS environment. On another platform, use `requirements.txt` if locked wheels are unavailable. Place the compatible `best.pt` in `weights/`. On Windows PowerShell, create the environment with `py -3.12 -m venv .venv` and activate with `.\.venv\Scripts\Activate.ps1`.

Create the dashboard environment in a second terminal:

```bash
cd transportation_dashboard
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

Model packages belong in the YOLO environment; the dashboard environment only needs its own lockfile.

### Supabase setup

For a **new, empty** Supabase project, run [`transportation_dashboard/supabase/schema.sql`](transportation_dashboard/supabase/schema.sql) once in the SQL editor. Do not rerun it in an existing configured database. Create two **private** buckets named `inspection-media` and `analysis-artifacts`.

Inside `transportation_dashboard`, copy `.env.example` to `.env.local` and set your own project URL and backend secret:

```ini
SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_SECRET_KEY=YOUR_BACKEND_SECRET
SUPABASE_MEDIA_BUCKET=inspection-media
SUPABASE_ARTIFACTS_BUCKET=analysis-artifacts
```

Keep `.env.local` on the backend and out of Git and screenshots. See the [database notes](transportation_dashboard/supabase/README.md). The existing Supabase project requires **no new migration** for YOLO.

## Run

In the YOLO folder with its environment active:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8020
```

In the dashboard folder with its environment active:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/. The dashboard API is at `/docs`, its storage check at `/api/health`, and the YOLO API at http://127.0.0.1:8020/docs. The model API's `/` returning Not Found is expected. Keep both servers running; stop each with Ctrl+C. If an older SegFormer server occupies port 8020, stop it before starting YOLO. Run only one dashboard worker because its analysis queue is local to the process. Keep both services bound to `127.0.0.1` until authentication is added.

## Use and interpretation

Choose **Upload images**, select up to ten JPEG/PNG/WebP files, and click **Upload & analyze**. Each file can be at most 20 MiB; analysis accepts at most 4 million pixels. New images are queued automatically. Open **Recent inspections** to see status and the saved result. If analysis fails, click **Retry analysis** in the image details. Older records can be reanalyzed with YOLO from the same details.

YOLO uses a 960-pixel inference size, confidence threshold 0.10 and NMS IoU 0.50. It returns boxes in original-image pixel coordinates. Its checkpoint labels are:

| ID | Label |
|---:|---|
| 0 | Crack |
| 1 | Pothole |
| 2 | Patched crack |
| 3 | Patched pothole |
| 4 | Clay-patched crack |
| 5 | Manhole |

**Crack** has no longitudinal/transverse direction or severity. Bounding-box confidence is not road risk or crack severity. A completed run with zero detections does not establish healthy pavement. The supplied experimental inverse-box score is **not a validated PCI score** and is not used as road condition in the dashboard. Expert review and authenticated public hosting remain future work.

The team reported validation precision **58.32%**, recall **72.67%**, mAP@50 **63.45%**, and mAP@50:95 **50.21%**. These are reported values from the supplied package; the ZIP lacks the full evaluation data and script needed to reproduce them independently. See [model notes](YOLO11s_Pavement/README.md).

## Tests

With the YOLO server running and the dashboard's Supabase connection configured, run from `transportation_dashboard`:

```bash
.venv/bin/python tests/check_model_integration.py
.venv/bin/python tests/check_supabase_integration.py
```

The model integration test uses a local sample supplied in the ZIP at `YOLO11s_Pavement/samples/Roadimage1.jpg`; it creates and removes temporary test records. It checks detection results, empty results, saved geometry/confidence, previews, failure/retry and duplicate requests. See [integration details](transportation_dashboard/MODEL_INTEGRATION.md). Successful execution is not an accuracy benchmark.

## Repository contents

- `YOLO11s_Pavement/`: YOLO API, dependency files, original scoring script and recorded metric notes. Checkpoint and sample photos are local only.
- `transportation_dashboard/`: FastAPI backend, interface, schema and tests.
- `Attain_SegFormer_Portable/`: older segmentation model code for historical results and separate research use. Its checkpoint is also local only.
- `QUICK_START.md`: daily run commands and workflow.

Credentials, Python environments, datasets, original research documents, generated outputs, and model weights are excluded from Git. A software license and public model-weight distribution location have not yet been selected by the team; source availability does not imply permission to redistribute third-party data or checkpoints.
