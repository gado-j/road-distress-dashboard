# Quick start: run the dashboard

This is the short daily-use guide for the existing macOS setup. For a new machine,
complete the [first-time setup](README.md#what-you-need) first.

## Before starting

Open the **main project folder** in VS Code: the folder containing both
`Attain_SegFormer_Portable` and `transportation_dashboard`. Open two new terminals
with **Terminal → New Terminal**. Start each terminal at that main folder.

You need:

- Both folders' `.venv` environments already installed.
- `Attain_SegFormer_Portable/best_model.pt`, supplied separately by the team.
- The dashboard's ignored `.env.local` configured for your Supabase project, with
  its tables and private buckets already created.
- Internet access for the database and image storage.

Do not recreate the database, reinstall packages, or retrain the model each time.

## 1. Terminal 1 — start the model

From the main project folder, run:

```bash
cd Attain_SegFormer_Portable
source .venv/bin/activate
python -m uvicorn practice_api:app --host 127.0.0.1 --port 8020
```

Wait for **Application startup complete**. Keep this terminal running.

## 2. Terminal 2 — start the dashboard

In a separate terminal, starting again at the main project folder:

```bash
cd transportation_dashboard
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Wait for **Application startup complete**. Keep this terminal running too.

If you are already inside the named folder, omit its `cd` command. Use `pwd` to
check your current location.

## 3. Open and use the dashboard

Open **http://127.0.0.1:8010/** in your browser.

1. Select **Upload images**.
2. Choose a JPG, PNG, or WebP image.
3. Click **Upload & analyze**.
4. Open **Overview → Recent inspections**.
5. Wait for the image's status to change to **Completed**.
6. Open the image to see its saved labels and pixel coverage.

Analysis starts automatically; you do not need to click another analysis button.
Existing older images can be processed by opening their details and selecting
**Analyze and save**. Failed analyses offer **Retry analysis**.

Limits: ten images per upload; each image at most **20 MiB** and, for analysis,
**4 million pixels**. The model processes images one at a time. Larger originals
can be saved but their analysis is rejected with an explanation. Keep both
servers running until work finishes.

## How the project works

```text
Choose image and click Upload & analyze
                ↓
Dashboard backend saves the original in private storage
                ↓
Database records the image and a queued analysis run
                ↓
Background worker retrieves the image and calls model API :8020
                ↓
SegFormer resizes to 640 × 640, predicts pixel classes,
then produces an original-size class mask
                ↓
Model API returns the detected classes and pixel counts
                ↓
Dashboard backend saves results and marks the run Completed
                ↓
Recent inspections, image details, and chart totals update
```

| Part | Role |
|---|---|
| Browser interface | Uploads images and displays records/charts |
| Dashboard FastAPI server, port 8010 | Coordinates uploads, jobs and saved results |
| Model FastAPI server, port 8020 | Loads the trained model once and handles inference |
| Supabase Storage | Stores original image files privately |
| Supabase Postgres | Stores inspection records, analysis runs and predictions |

**Queued** means waiting; **Analyzing…** means processing; **Completed** means the
model finished and results were saved. **Failed** means the original remains but
analysis needs a retry. Refreshing the browser does not erase saved results.

A background-only result is **Completed / No distress predicted**. It does not
prove the road is distress-free. Pixel coverage is not confidence or road risk.
Expert review is still a future feature; current predictions are unverified.
The automatic workflow currently saves structured results, not mask/overlay files.

## Stop or restart

Press **Ctrl+C** in each server terminal. Run that terminal's startup command again
to restart it. Graceful shutdown may wait for queued work; avoid force-closing it
while jobs are active.

On a later day, repeat steps 1–3. You do not need to keep VS Code running after
stopping the servers. Start only one copy of each service.

## If something goes wrong

| Problem | Action |
|---|---|
| Browser cannot open the dashboard | Check that Terminal 2 is running on 8010. |
| Model API unavailable / analysis failed | Start Terminal 1 on 8020, then click Retry analysis. |
| `Address already in use` | A server is probably already running; use it or stop it in its original terminal. |
| `.venv/bin/activate` not found | Check `pwd`; use the correct folder. If the environment is missing, follow the full README. |
| Missing `best_model.pt` | Get the matching checkpoint from the team and place it in the model folder. |
| Database unavailable | Check `.env.local`, internet access and http://127.0.0.1:8010/api/health. Never share the secret key. |
| Model home page says Not Found | Expected at port 8020 `/`; its test page is http://127.0.0.1:8020/docs. |
| Visible crack, but no distress predicted | Record the example for the model team. Running successfully does not establish accuracy. |

For full setup, dependency installation and database creation, use [README.md](README.md).
