# Road distress dashboard: database foundation

The dashboard stores originals privately and saves automatic model analyses in
Postgres. A new installation starts with empty tables and no demo records. Use a
separate Supabase project for each deployment.

## Apply to the dedicated project

1. Confirm the project name and reference. Do not use the ITS Scorecard database.
2. Apply `schema.sql` once to a new project through SQL Editor or a remote managed
   migration. It is transactional and deliberately fails if these tables already
   exist rather than silently accepting a different schema.
3. In Storage, create two **private** buckets:
   - `inspection-media`: originals. Initially accept JPEG, PNG and WebP images.
   - `analysis-artifacts`: overlays, masks, thumbnails and evidence frames.
   Set a 20 MB file limit for both as an initial development choice, adjustable
   after the model requirements are confirmed. This is a byte limit, not a pixel
   resolution limit. Video support is reserved in the schema, not implemented.
4. Run `verify.sql`. Expect seven tables with RLS enabled, no anonymous or
   authenticated table access, and two private buckets.

## Record relationships

`roads -> inspections -> media -> analysis_runs -> predictions`

Road assignment and actual inspection time may be unknown at upload. An upload
still belongs to an inspection. Upload timestamps are not inspection dates.
Each model invocation creates a fresh analysis run; repeated runs do not overwrite
earlier outputs. Multiple predictions per run support future detection/segmentation.
Reviews refer to an image and optionally a prediction and preserve corrections
separately. Reviewer identity must come from a validated Supabase Auth session.
Generated files link to the run through `analysis_artifacts`.

Store stable bucket/object paths, not expiring signed URLs. Use UUID-based paths,
for example `<inspection_id>/<media_id>/original.jpg`; preserve original filenames
only as metadata. Do not derive hazard labels from filenames.

## Storage and database coordination

Storage uploads and database writes are separate operations, not one transaction.
The backend creates a pending media record, upload the object, then
mark it ready. Failed uploads remain failed or are cleaned up; they must not be
scheduled for analysis. Original media remains unchanged. Preprocessing settings
and tile offsets are saved per analysis run/result; the current adapter records 640 × 640 preprocessing explicitly.

Object deletion is an explicit backend workflow. SQL deletion does not remove
Storage files. Foreign keys restrict destructive deletion so review and prediction
history cannot accidentally disappear. Storage originals need a separate backup
plan; database backups alone do not preserve their bytes.

## Access and next implementation step

All seven tables have RLS enabled and browser-role grants revoked. This is an
intentional **backend-only** foundation, not a completed user-access design.
Private buckets should have no permissive public upload/read policies. FastAPI
uses a server-only secret key and generates short-lived viewing URLs. User and
team authorization are not implemented yet. Auth and authorization must be implemented
before exposing those endpoints beyond local development.

Copy `.env.example` to `.env.local` only when connecting the backend. Never put
the secret key in frontend code, commit it, or paste it into chat. The app reads these variables through `storage_backend.py`. Uploads validate
JPEG/PNG/WebP contents, permit up to 10 images and 20 MB per image, preserve
original pixels, and automatically queue inference through the model API.

Until team authentication exists, middleware restricts the app to loopback and
rejects cross-origin requests. Run with `--host 127.0.0.1`. Expert review writes
return an explicit unavailable response instead of inventing a reviewer identity.
Deletion only permits media without analysis/review history. Each uploaded file
currently gets its own inspection; grouping is a future interface task.

Future work includes user authentication and expert review. Optional historical
imports must not be treated as genuine model predictions.

## Run and verify

From the dashboard folder:

```bash
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8010
```

Open `http://127.0.0.1:8010/#upload`. `/api/health` checks access to the seven
tables and confirms both configured buckets are private without exposing secrets.

The explicit live smoke test creates one tiny synthetic PNG, checks upload
metadata, signed preview, denied public access, invalid-file rejection, and
UUID deletion, then removes its own inspection/media records:

```bash
.venv/bin/python tests/check_supabase_integration.py
```

`requirements-lock.txt` records the tested environment. The interface now has
Overview, Inspections (Hazard records), and Upload images pages, with responsive
layouts for phones and laptops. Search, source/status filters, sorting, original
image previews, and upload progress use the Supabase-backed inspection records.
Historical demo labels are identified separately and excluded from model-result
summaries. Automatic model execution uses the separate API on port 8020. Authenticated expert review remains future work.
Legacy logistics API endpoints remain in the backend but are not used by this UI.

Legacy import: `supabase/import_legacy.py` uses deterministic media IDs to skip
already imported images on retry. Legacy values are preserved in inspection notes
and shown with Demo labels; no analysis/prediction rows are fabricated.
