# Road Distress Dashboard

A local FastAPI web application for uploading pavement images, running an Attain
SegFormer-B0 segmentation model, and reviewing saved distress predictions. The
responsive interface supports laptops and phones. This repository distributes
source code; it is not a hosted web service.

## Features

- Private image storage and inspection records in Supabase.
- Automatic analysis after upload: queued → analyzing → completed or failed.
- Saved class labels, pixel counts and coverage, checkpoint fingerprint, and
  prediction timing. Failed analyses retain the original image and can be retried.
- Recent inspections, searchable records, original image previews and zoom.
- Upload activity by month, quarter, or year, including zero-count periods.
- TxDOT cracking distribution by period and label source. Upload dates are grouped
  in America/Chicago (Central Time).

The current model is experimental and has missed visible cracks in local smoke
tests. Successful execution is not evidence of predictive accuracy. Expert review
and user authentication are not implemented yet.

## What you need

1. Python **3.12**, Git, and an internet connection for initial dependencies and
   Supabase access. Python 3.12 was tested on macOS; Windows/Linux instructions are
   provided but have not been verified on those systems.
2. Your own Supabase project. No project credentials or existing research records
   are included.
3. The compatible trained checkpoint, placed at
   `Attain_SegFormer_Portable/best_model.pt`. **Weights are not included in this
   source release.** Obtain them from the project team; there is currently no
   public checkpoint download configured here. The trained weights must match the
   included configuration and class mapping. A full end-to-end run requires them.

The dashboard and model use separate Python environments. Two terminals are
needed, one per server. The default workflow does not require a GPU; it uses CUDA
when available and otherwise CPU. The provided code does not select Apple's MPS.

## 1. Get the source

```bash
git clone https://github.com/gado-j/road-distress-dashboard.git
cd road-distress-dashboard
```

## 2. Create the model environment

From the repository root:

```bash
cd Attain_SegFormer_Portable
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

On Windows PowerShell use `py -3.12 -m venv .venv` and
`.\.venv\Scripts\Activate.ps1` in place of the two environment commands.

`requirements-lock.txt` records the tested model/API environment. PyTorch wheel
availability depends on the operating system; if that lock cannot be installed,
use the supplied `requirements.txt` with a compatible PyTorch/torchvision build,
then install `fastapi`, `uvicorn`, and `python-multipart` for the HTTP service.
Record any alternative environment used for reproducing results.

Keep `best_model.pt`, `config.json`, and `class_mapping.json` beside `inference.py`.
Do not replace the architecture or label IDs with an unrelated checkpoint.

## 3. Create the dashboard environment

In another terminal, starting at the repository root:

```bash
cd transportation_dashboard
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
```

Windows uses the activation commands described above. Install model packages only
in the model environment, not in the dashboard environment.

## 4. Configure Supabase

1. Create a Supabase project.
2. On a **new, empty project**, run
   [`transportation_dashboard/supabase/schema.sql`](transportation_dashboard/supabase/schema.sql)
   in its SQL editor. Do not rerun this initial schema on an existing configured
   database. It creates the seven application tables and backend-only access.
3. Create two **private** Storage buckets named `inspection-media` and
   `analysis-artifacts`. Do not enable public access.
4. Copy the dashboard's environment example:

   ```bash
   cp .env.example .env.local
   ```

   On Windows PowerShell: `Copy-Item .env.example .env.local`.
5. Edit `.env.local` locally:

   ```ini
   SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
   SUPABASE_SECRET_KEY=YOUR_BACKEND_SECRET
   SUPABASE_MEDIA_BUCKET=inspection-media
   SUPABASE_ARTIFACTS_BUCKET=analysis-artifacts
   ```

Use a backend secret/service-role credential for your own project. Never put it in
browser JavaScript, commit it, or share it in screenshots. `.env.local` is ignored
by Git. See the [database notes](transportation_dashboard/supabase/README.md).

## 5. Run both servers

**Terminal 1 — model**, with the model environment activated:

```bash
cd Attain_SegFormer_Portable  # if starting from the repository root
python -m uvicorn practice_api:app --host 127.0.0.1 --port 8020
```

If the terminal is already inside that folder, omit the `cd`. Wait for
`Application startup complete`.

**Terminal 2 — dashboard**, with the dashboard environment activated:

```bash
cd transportation_dashboard  # if starting from the repository root
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Open:

| Address | Purpose |
|---|---|
| http://127.0.0.1:8010/ | Dashboard |
| http://127.0.0.1:8010/docs | Dashboard API docs |
| http://127.0.0.1:8010/api/health | Database and private-bucket connection check |
| http://127.0.0.1:8020/docs | Model API test page |

The model service has no page at `/`; use `/docs`. Keep both terminals running.
Stop each with **Ctrl+C**. Restart the model service after editing model/API code.
For dashboard development, `--reload` can be added to its startup command.
Refresh the browser after changing frontend files.

**Local use only:** keep `127.0.0.1` and use one dashboard Uvicorn worker. The
current app is not ready for public hosting or unauthenticated network access.

## 6. Upload and inspect

1. Select **Upload images**, choose an image, and click **Upload & analyze**.
2. Open **Overview → Recent inspections**. Processing starts automatically.
3. Open the image to see saved predictions and pixel coverage.
4. If processing fails, retain the original and use **Retry analysis** after
   correcting the issue (for example, starting port 8020).

Limits: up to ten JPEG/PNG/WebP files per upload, each at most **20 MiB**. Model
analysis additionally requires at most **4 million original pixels**. Larger
images can be saved but will receive a failed analysis with a clear explanation.
The model resizes to **640 × 640** internally and forms an original-size mask.
Automatic tiling/video inference is not included.

[Sample-input notes](samples/README.md) explain how to create a small synthetic
image for a smoke test. For actual distress tests, use approved road imagery.

## Interpretation and current limitations

| ID | Model class |
|---|---|
| 0 | Background |
| 1 | Alligator crack - Low |
| 2 | Block crack - Low |
| 3 | Faded marking - High |
| 4 | Faded marking - Low |
| 5 | Linear crack - High |
| 6 | Linear crack - Low |
| 7 | Pothole - Low |

- Background-only output is **Completed / No distress predicted**, not proof of
  healthy pavement.
- Pixel coverage is not confidence, calibrated physical area, severity validation,
  a condition score, or overall road risk. Low/High is preserved as part of the
  trained class name. Overall risk and confidence are not invented.
- The model does not distinguish longitudinal and transverse cracking. Its broader
  Linear crack label is left unmapped in the four-category TxDOT donut.
- Donut categories follow the flexible-pavement cracking terminology in the
  [TxDOT FY2024 PMIS Pavement Rater's Manual](https://ftp.txdot.gov/pub/txdot/mnt/crossroads/pmis/pmis-fy2024-visual-raters-manual.pdf).
  Multi-label images can contribute once to each type; percentages are shares of
  crack labels, not unique images or road area.
- The automatic HTTP path saves structured results, not mask/overlay artifacts.
  Standalone visualization scripts can produce those files locally.
- Authentication, expert annotation, video prediction, distributed workers, and
  hosted deployment are future work. Queued state is persisted, but execution uses
  one local worker. Restart recovery resumes queued work and marks interrupted
  processing runs failed for retry.
- Legacy logistics routes remain in the backend for compatibility; they are not
  used by the road-distress interface and are not predictive-maintenance models.

## Reproduction and tests

With the model environment active, and a local image `example.jpg`:

```bash
python inference.py --image example.jpg --output example_mask.png
python visualize_mask.py --image example.jpg --mask example_mask.png --output example_overlay.png
python benchmark_inference.py --image example.jpg --runs 5
```

These commands run from `Attain_SegFormer_Portable`. Use new output names to avoid
replacing earlier results. The raw mask contains class IDs and may appear black.

From the dashboard folder/environment:

```bash
python tests/check_supabase_integration.py
```

This explicitly creates and removes its own temporary test upload in your
configured Supabase project. Full model integration testing is documented in
[MODEL_INTEGRATION.md](transportation_dashboard/MODEL_INTEGRATION.md); its existing
smoke script also requires local `road.jpg` and `road2.jpg` fixtures not distributed
here. Do not interpret smoke tests as an accuracy benchmark.

## Troubleshooting

| Problem | Check |
|---|---|
| `python` or a module is missing | Activate the correct folder's `.venv`; install its requirements. |
| Missing `best_model.pt` | Obtain the matching checkpoint from the project team. |
| Model API unavailable | Start the model service on port 8020, then retry the image. |
| Database/storage unavailable | Check your `.env.local`, network access, schema and private buckets. |
| Address already in use | An earlier server may still be running; stop it before restarting. |
| File not found | Use the actual image filename/extension and correct working folder. |
| Analysis rejected | Check 20 MiB / 4-million-pixel limits and supported image format. |
| Empty donut | No saved mapped crack labels exist in the selected period/source. |
| Bad prediction | Record the image, checkpoint and output for the model team; do not relabel it as a correct result. |

## Repository contents

- `transportation_dashboard/`: backend, frontend, schema, environment example and tests.
- `Attain_SegFormer_Portable/`: model configuration, inference/API code and visualization tools.
- `samples/`: instructions for small, approved smoke-test inputs.

Credentials, Python environments, datasets, original research documents, reference
projects, generated outputs and model weights are excluded from Git.

## License and model availability

A software license and a public model-weight distribution location have not yet
been selected by the project team. No redistribution license for third-party data
or weights is implied. Before describing this as a freely reusable open-source
release, select and add the approved software license and state the checkpoint's
availability separately.
