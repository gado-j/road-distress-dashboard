-- Initial schema for a NEW Road distress dashboard project.
-- Apply once through the Supabase SQL Editor or as a managed remote migration.
-- Existing SQLite records are not imported by this script.
-- Relationship overview:
-- roads -> inspections -> media -> analysis_runs -> predictions
--                           |           |              |
--                           |           -> analysis_artifacts
--                           -> expert_reviews <---------
-- Tables only store data: uploads, model execution, status transitions, and
-- reviewer permissions must be implemented in FastAPI/processing workers.
-- JSONB stores structured JSON; UUID keys uniquely identify linked records.
-- ON DELETE RESTRICT prevents accidental deletion of referenced history.
-- Deleting a database record never automatically deletes its Storage object.
begin;

-- ROADS: one physical road segment, not one uploaded image.
-- Input: an optional segment code, required name, optional coordinates, and
-- additional road attributes in metadata (for example pavement type).
-- Created from road registration/import; reused across repeat inspections.
-- Relationship: one road can have many inspections. Road assignment is optional
-- in inspections, so an unknown location does not block an image upload.
-- Coordinates represent a location point; segment geometry is not yet modeled.
create table public.roads (
  id uuid primary key default gen_random_uuid(),
  segment_code text unique,
  name text not null check (length(trim(name)) > 0),
  latitude double precision check (latitude between -90 and 90),
  longitude double precision check (longitude between -180 and 180),
  metadata jsonb not null default '{}' check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now()
);

-- INSPECTIONS: one observation/inspection event grouping related media.
-- Input: optional road_id, actual inspected_at time, source, notes, and optional
-- created_by identity from Supabase Auth. An event can contain multiple images.
-- inspected_at is when the road was observed; created_at is when this record
-- was saved. Leave inspected_at null when the capture time is unknown.
-- Relationship: belongs to zero or one road; has one or more media records once
-- uploads succeed. This table stores context, not image bytes or predictions.
create table public.inspections (
  id uuid primary key default gen_random_uuid(),
  road_id uuid references public.roads(id) on delete restrict,
  inspected_at timestamptz,
  source text not null default 'manual' check (source in ('manual', 'drone', 'sensor', 'citizen', 'import')),
  notes text,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

-- MEDIA: one original uploaded image or video and its storage reference.
-- Input: inspection_id, bucket/object path, original filename, detected MIME type,
-- byte size, dimensions, optional video duration, and optional SHA-256 hash.
-- The actual bytes live in Supabase Storage, NOT in this Postgres table.
-- Save stable paths; generate temporary signed viewing URLs when requested.
-- Lifecycle: pending before upload, ready after success, failed on upload error.
-- Storage upload and database insertion are separate operations; the backend
-- must coordinate failures and only analyze ready media.
-- Video fields reserve future support; they do not implement video processing.
create table public.media (
  id uuid primary key default gen_random_uuid(),
  inspection_id uuid not null references public.inspections(id) on delete restrict,
  bucket_id text not null default 'inspection-media',
  object_path text not null check (length(trim(object_path)) > 0),
  original_filename text not null,
  media_type text not null check (media_type in ('image', 'video')),
  mime_type text not null,
  byte_size bigint not null check (byte_size > 0),
  width integer check (width > 0),
  height integer check (height > 0),
  duration_seconds double precision check (duration_seconds >= 0),
  sha256 text check (sha256 ~ '^[0-9a-f]{64}$'),
  upload_status text not null default 'pending' check (upload_status in ('pending', 'ready', 'failed')),
  created_at timestamptz not null default now(),
  unique (bucket_id, object_path)
);

-- ANALYSIS_RUNS: one attempt to process one original media file with a model.
-- Input: media_id, model name/version, task type, preprocessing settings, and
-- execution timestamps. Store resizing/padding/tiling settings in preprocessing.
-- Lifecycle: queued -> processing -> completed or failed. Save errors on failure.
-- raw_output optionally preserves the structured model response; large masks
-- or other generated files belong in Storage and analysis_artifacts instead.
-- Every rerun creates a NEW row, preserving earlier model versions/results.
-- A queued row alone does not execute a model; a backend worker must process it.
-- This initial schema links a run to one media file, not a multimodal input set.
create table public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null references public.media(id) on delete restrict,
  model_name text not null,
  model_version text not null,
  task_type text not null check (task_type in ('classification', 'multilabel_classification', 'detection', 'segmentation', 'forecast')),
  status text not null default 'queued' check (status in ('queued', 'processing', 'completed', 'failed')),
  preprocessing jsonb not null default '{}' check (jsonb_typeof(preprocessing) = 'object'),
  raw_output jsonb,
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (id, media_id),
  check (completed_at is null or started_at is null or completed_at >= started_at),
  check (status <> 'completed' or completed_at is not null),
  check (status <> 'failed' or error_message is not null)
);

-- One run can produce many defects, classes, tiles, or video-frame results.
-- Coordinates should refer to original-image pixels, documented in geometry.
-- PREDICTIONS: individual structured outputs produced by an analysis run.
-- Input from the backend/model adapter: hazard label, optional confidence (0-1),
-- optional risk category/score, geometry, tile offsets, video-frame timestamp,
-- forecast target time, and additional model-specific values in output JSON.
-- Confidence is not severity; any numerical score must have a score_definition
-- explaining its meaning/scale. Unsupported outputs stay null, never random.
-- One run can produce zero, one, or many results. Multiple rows permit multiple
-- crack types/locations without assuming the first model can detect them all.
-- The composite foreign key ensures the prediction references its run's media.
-- Keep original model results unchanged when an expert submits a correction.
create table public.predictions (
  id uuid primary key default gen_random_uuid(),
  analysis_run_id uuid not null,
  media_id uuid not null,
  hazard_type text,
  confidence double precision check (confidence between 0 and 1),
  risk_condition text check (risk_condition in ('low', 'moderate', 'high')),
  score double precision,
  score_definition text,
  geometry jsonb check (geometry is null or jsonb_typeof(geometry) = 'object'),
  tile_metadata jsonb check (tile_metadata is null or jsonb_typeof(tile_metadata) = 'object'),
  frame_timestamp_seconds double precision check (frame_timestamp_seconds >= 0),
  forecast_target_at timestamptz,
  output jsonb not null default '{}' check (jsonb_typeof(output) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (analysis_run_id, media_id) references public.analysis_runs(id, media_id) on delete restrict,
  unique (id, media_id),
  check (score is null or length(trim(score_definition)) > 0 and score_definition is not null)
);

-- Append a review for each correction; never overwrite the model output.
-- A null prediction_id permits expert annotation before a model is available.
-- EXPERT_REVIEWS: human assessments kept separately from model predictions.
-- Input from a validated reviewer: media_id, optional prediction_id, reviewer_id,
-- decision, corrected hazard/risk/score/geometry when relevant, and comments.
-- Decisions: confirmed = accepts a prediction; corrected = supplies a correction;
-- rejected = rejects a prediction; annotated = labels media independently.
-- Confirm/correct/reject requires prediction_id; standalone annotation does not.
-- reviewer_id must identify an existing Supabase Auth user, not a typed name.
-- The composite foreign key prevents reviewing another image's prediction.
-- Append a new review for each revision to preserve history. This is an app
-- convention; the current grants do not enforce immutability at database level.
-- The backend decides which review is displayed as current; no such view exists
-- yet. Creating a review does not automatically retrain the model.
create table public.expert_reviews (
  id uuid primary key default gen_random_uuid(),
  media_id uuid not null references public.media(id) on delete restrict,
  prediction_id uuid,
  reviewer_id uuid not null references auth.users(id) on delete restrict,
  decision text not null check (decision in ('confirmed', 'corrected', 'rejected', 'annotated')),
  hazard_type text,
  risk_condition text check (risk_condition in ('low', 'moderate', 'high')),
  score double precision,
  score_definition text,
  geometry jsonb check (geometry is null or jsonb_typeof(geometry) = 'object'),
  comments text,
  created_at timestamptz not null default now(),
  foreign key (prediction_id, media_id) references public.predictions(id, media_id) on delete restrict,
  check (score is null or length(trim(score_definition)) > 0 and score_definition is not null),
  check (decision = 'annotated' or prediction_id is not null)
);

-- ANALYSIS_ARTIFACTS: references to generated files belonging to a model run.
-- Input: analysis_run_id, artifact type, bucket/object path, byte size, and
-- metadata such as dimensions, frame time, tile offsets, or coordinate space.
-- Examples: annotated overlay, segmentation mask, evidence frame, saved input
-- tile, or a run-specific thumbnail. Actual bytes live in Supabase Storage.
-- Original uploads remain in media. Save only artifacts worth retaining;
-- do not save every extracted video frame by default.
-- These records support viewing evidence and tracing it back to a model run.
create table public.analysis_artifacts (
  id uuid primary key default gen_random_uuid(),
  analysis_run_id uuid not null references public.analysis_runs(id) on delete restrict,
  artifact_type text not null check (artifact_type in ('overlay', 'mask', 'evidence_frame', 'tile', 'thumbnail')),
  bucket_id text not null default 'analysis-artifacts',
  object_path text not null check (length(trim(object_path)) > 0),
  byte_size bigint not null check (byte_size > 0),
  metadata jsonb not null default '{}' check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  unique (bucket_id, object_path)
);

-- Indexes speed up common queries: inspection history, media lookup, pending
-- analysis jobs, model outputs, reviewer history, and generated-file lookup.
create index inspections_road_date_idx on public.inspections (road_id, inspected_at desc);
create index inspections_created_by_idx on public.inspections (created_by);
create index media_inspection_idx on public.media (inspection_id);
create index analysis_runs_media_date_idx on public.analysis_runs (media_id, created_at desc);
create index analysis_runs_pending_idx on public.analysis_runs (status, created_at) where status in ('queued', 'processing');
create index predictions_run_media_idx on public.predictions (analysis_run_id, media_id);
create index predictions_media_idx on public.predictions (media_id);
create index reviews_media_date_idx on public.expert_reviews (media_id, created_at desc);
create index reviews_prediction_media_idx on public.expert_reviews (prediction_id, media_id);
create index reviews_reviewer_idx on public.expert_reviews (reviewer_id);
create index artifacts_run_idx on public.analysis_artifacts (analysis_run_id);

-- Initial access is backend-only. No browser/anonymous access is granted.
-- Before sharing the app, implement server-validated authentication and team
-- authorization. A privileged backend key bypasses RLS; RLS does not secure
-- an unauthenticated FastAPI endpoint that uses that key.
alter table public.roads enable row level security;
alter table public.inspections enable row level security;
alter table public.media enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.predictions enable row level security;
alter table public.expert_reviews enable row level security;
alter table public.analysis_artifacts enable row level security;

revoke all on public.roads, public.inspections, public.media, public.analysis_runs,
  public.predictions, public.expert_reviews, public.analysis_artifacts from anon, authenticated;
grant select, insert, update, delete on public.roads, public.inspections, public.media,
  public.analysis_runs, public.predictions, public.expert_reviews, public.analysis_artifacts to service_role;

commit;
