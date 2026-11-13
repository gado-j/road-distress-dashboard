from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import re
import io
import warnings
from uuid import UUID

from PIL import Image, ImageDraw, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
import storage_backend as storage

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent
HAZARDS = ["Alligator Crack", "Longitudinal Crack", "Transverse Crack", "Pothole"]
RISKS = ["Low Risk", "Moderate Risk", "High Risk"]
@asynccontextmanager
async def lifespan(app):
    import analysis_jobs
    try:
        await run_in_threadpool(analysis_jobs.recover)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Analysis recovery unavailable; check database connection.")
    yield
    await run_in_threadpool(analysis_jobs.shutdown)

app = FastAPI(title="Road distress dashboard", version="1.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.middleware("http")
async def local_development_only(request: Request, call_next):
    # Privileged backend credentials must not power unauthenticated network APIs.
    # This interim integration is loopback-only until team auth is implemented.
    host = request.url.hostname
    origin = request.headers.get("origin")
    if host not in {"127.0.0.1", "localhost", "::1", "testserver"} or (request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}):
        return JSONResponse({"detail": "Local development only; team authentication is not configured."}, status_code=403)
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

class PredictionRequest(BaseModel):
    vehicle_id: str = Field(examples=["V-204"])
    speed_kph: float = Field(ge=0, le=160)
    delay_minutes: float = Field(ge=0)
    vehicle_age_years: float = Field(ge=0)
    weather_risk: float = Field(ge=0, le=1)

class PredictionResponse(BaseModel):
    vehicle_id: str
    risk_score: float
    risk_band: Literal["low", "watch", "high"]
    model_name: str
    evaluated_at: datetime

class RiskModel:
    """Replace predict() with a trained sklearn, PyTorch, or TensorFlow model."""
    name = "baseline-operational-risk-v1"
    def predict(self, payload: PredictionRequest) -> float:
        risk = (0.035 * payload.delay_minutes + 0.050 * payload.vehicle_age_years +
                0.45 * payload.weather_risk + (0.12 if payload.speed_kph < 18 else 0))
        return round(min(1.0, max(0.0, risk)), 2)

model = RiskModel()
DATA_FILE = BASE_DIR / "data.csv"
FLEET = [
    {"id":"V-204","route":"Riverside → Central","status":"Delayed","eta":"+11 min","risk":.82,"left":52,"top":34},
    {"id":"V-118","route":"North Loop","status":"On time","eta":"2 min","risk":.21,"left":28,"top":58},
    {"id":"V-307","route":"Airport Express","status":"Weather watch","eta":"+6 min","risk":.63,"left":72,"top":54},
    {"id":"V-091","route":"Harbor Line","status":"On time","eta":"4 min","risk":.14,"left":44,"top":76},
]
ALERTS = [
    {"id":"A-719","severity":"High","title":"V-204 likely to miss Central transfer","detail":"Delay trend crossed the 15-minute intervention threshold.","action":"Dispatch spare from Depot 3","risk":.82},
    {"id":"A-720","severity":"Watch","title":"Airport Express exposure to storm cell","detail":"Rain intensity is rising along the east corridor.","action":"Notify route supervisor","risk":.63},
    {"id":"A-721","severity":"Watch","title":"North Loop headway widening","detail":"Two departures are 7 minutes apart during peak demand.","action":"Hold next departure","risk":.47},
]

@app.get("/", include_in_schema=False)
def dashboard(): return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/api/overview")
def overview():
    return {"updated_at":datetime.now(timezone.utc).isoformat(), "metrics":{"active_vehicles":48,"on_time_rate":91.4,"open_alerts":len(ALERTS),"estimated_impacts":126}, "fleet":FLEET, "alerts":ALERTS, "demand":[42,46,55,68,79,88,92,84,71,63,52,47], "demand_labels":["06","07","08","09","10","11","12","13","14","15","16","17"]}

@app.post("/api/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest):
    score=model.predict(payload)
    band: Literal["low","watch","high"] = "high" if score >= .70 else "watch" if score >= .40 else "low"
    return PredictionResponse(vehicle_id=payload.vehicle_id, risk_score=score, risk_band=band, model_name=model.name, evaluated_at=datetime.now(timezone.utc))

@app.get("/api/marks")
def marks_data() -> dict:
    """Read a local id/marks CSV or TSV placed beside app.py."""
    if not DATA_FILE.exists():
        return {"rows": [], "source": None}
    lines = [line.strip() for line in DATA_FILE.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    rows = []
    for line in lines:
        parts = re.split(r"[,;\t]", line)
        if len(parts) >= 2:
            try:
                if parts[0].strip().lower() == "id":
                    continue
                rows.append({"id": parts[0].strip(), "marks": float(parts[1].strip())})
            except ValueError:
                continue
    return {"rows": rows, "source": DATA_FILE.name}

@app.get("/api/health")
def health():
    try:
        return storage.check_connection()
    except Exception:
        raise HTTPException(503, "Supabase is unavailable or its tables/private buckets are not configured.")

@app.get("/api/assets")
def assets():
    try:
        rows = storage.list_assets()
        return {"assets": rows, "count": len(rows), "source": "supabase"}
    except Exception:
        raise HTTPException(503, "Could not load inspection records from Supabase.")

@app.post("/api/upload-images")
async def upload_images(files: list[UploadFile] = File(...)):
    if not 1 <= len(files) <= 10:
        raise HTTPException(422, "Select between 1 and 10 images per upload.")
    saved, errors, analysis_errors = [], [], []
    for upload in files:
        name = Path((upload.filename or "image").replace("\\", "/")).name
        try:
            content = await upload.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                errors.append({"name": name, "error": "Image exceeds the 20 MB upload limit."})
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(content)) as image:
                        fmt, (width, height) = image.format, image.size
                        image.verify()
                types = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"), "WEBP": ("image/webp", ".webp")}
                if fmt not in types:
                    raise ValueError("Unsupported image format")
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                errors.append({"name": name, "error": "Choose a valid JPEG, PNG, or WebP image."})
                continue
            mime, suffix = types[fmt]
            try:
                item = await run_in_threadpool(storage.save_image, content, name, mime, width, height, suffix)
                saved.append(item)
                try:
                    import analysis_jobs
                    record = await run_in_threadpool(storage.media_record, item['id'])
                    item.update(await run_in_threadpool(analysis_jobs.enqueue, record))
                    item['analysis_status'] = 'queued'
                except Exception:
                    analysis_errors.append({'id': item['id'], 'name': name, 'error': 'Original saved, but analysis could not be queued. Open its details and retry.'})
            except Exception:
                errors.append({"name": name, "error": "Could not save image to Supabase."})
        finally:
            await upload.close()
    return JSONResponse({"saved": saved, "count": len(saved), "errors": errors, "analysis_errors": analysis_errors}, status_code=201 if saved else 422)

@app.get("/api/assets/{asset_id}/preview")
def preview(asset_id: UUID):
    try:
        record = storage.media_record(asset_id)
        if not record or record['upload_status'] != 'ready':
            raise HTTPException(404, "Image not found")
        return RedirectResponse(storage.preview_url(record))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Could not retrieve image preview.")

@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: UUID):
    try:
        record = storage.media_record(asset_id)
        if not record:
            raise HTTPException(404, "Image not found")
        if not storage.delete_unanalyzed(record):
            raise HTTPException(409, "This image has analysis or review history and cannot be deleted here.")
        return {"deleted": record['original_filename']}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Image cleanup could not be completed. Retry to finish removal.")

@app.post("/api/assets/{asset_id}/annotate")
def annotate(asset_id: UUID):
    # Supabase reviews require a verified auth.users identity, never a typed name.
    raise HTTPException(503, "Expert annotations require reviewer authentication, which is not configured yet.")

@app.get("/api/assets/{asset_id}/history")
def history(asset_id: UUID):
    try:
        if not storage.media_record(asset_id):
            raise HTTPException(404, "Image not found")
        rows = storage.client().table('expert_reviews').select('*').eq('media_id', str(asset_id)).order('created_at', desc=True).execute().data
        return {"history": rows}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Could not load review history.")


@app.post("/api/assets/{asset_id}/analyze", status_code=202)
def analyze_asset(asset_id: UUID):
    import analysis_jobs
    try:
        record = storage.media_record(asset_id)
        if not record or record['upload_status'] != 'ready':
            raise HTTPException(404, "Image not found")
        return analysis_jobs.enqueue(record)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Could not queue analysis. Original image is safe; retry shortly.")


@app.get('/api/analysis/{run_id}/detections-preview')
def detections_preview(run_id: UUID):
    """Draw saved YOLO boxes over the original; this never reruns inference."""
    try:
        c = storage.client()
        rows = c.table('analysis_runs').select('media_id,status,raw_output').eq('id', str(run_id)).limit(1).execute().data
        if not rows or rows[0]['status'] != 'completed':
            raise HTTPException(404, 'Completed analysis not found')
        result = rows[0].get('raw_output') or {}
        if result.get('task_type') != 'detection' or result.get('model_name') != 'YOLO11s Pavement':
            raise HTTPException(404, 'Detection preview not found')
        record = storage.media_record(rows[0]['media_id'])
        if not record or record['upload_status'] != 'ready':
            raise HTTPException(404, 'Original image not found')
        original = c.storage.from_(record['bucket_id']).download(record['object_path'])
        with Image.open(io.BytesIO(original)) as source:
            canvas = source.convert('RGB')
        draw = ImageDraw.Draw(canvas)
        for item in result.get('detections', []):
            box = item['xyxy']
            color = '#db6b4f' if item['label'] == 'Manhole' else '#00a5aa'
            draw.rectangle(box, outline=color, width=max(2, canvas.width // 500))
            label = f"{item['label']} {item['confidence']:.2f}"
            x, y = int(box[0]), max(0, int(box[1])-17)
            draw.rectangle((x,y,min(canvas.width,x+len(label)*7+5),y+15), fill='#102b36')
            draw.text((x+2,y+1), label, fill='white')
        output = io.BytesIO()
        canvas.save(output, format='JPEG', quality=88)
        return Response(output.getvalue(), media_type='image/jpeg', headers={'Cache-Control':'no-store'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Could not render saved detections.')

@app.get("/api/analysis/{run_id}/{kind}")
def analysis_artifact(run_id: UUID, kind: Literal['mask', 'overlay']):
    try:
        c = storage.client()
        runs = c.table('analysis_runs').select('status').eq('id', str(run_id)).execute().data
        if not runs or runs[0]['status'] != 'completed':
            raise HTTPException(404, "Completed analysis not found")
        rows = c.table('analysis_artifacts').select('*').eq('analysis_run_id', str(run_id)).eq('artifact_type', kind).execute().data
        if not rows:
            raise HTTPException(404, "Artifact not found")
        return RedirectResponse(storage.preview_url(rows[0]))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Could not retrieve analysis artifact.")


@app.post("/api/assets/{asset_id}/analyze-preview")
def analyze_preview(asset_id: UUID):
    import httpx
    from test_model_connection import request_analysis_bytes

    # Find the saved image.
    record = storage.media_record(asset_id)

    if not record or record["upload_status"] != "ready":
        raise HTTPException(404, "Image not found.")

    # Retrieve its original bytes.
    try:
        image_bytes = (
            storage.client()
            .storage.from_(record["bucket_id"])
            .download(record["object_path"])
        )
    except Exception:
        raise HTTPException(503, "Could not download the saved image.")

    # Ask the separate model API to analyze it.
    try:
        return request_analysis_bytes(
            image_bytes,
            record["original_filename"],
        )
    except httpx.HTTPStatusError:
        raise HTTPException(502, "The model API rejected the image.")
    except httpx.RequestError:
        raise HTTPException(
            503,
            "Could not reach the model API. Check that port 8020 is running.",
        )
