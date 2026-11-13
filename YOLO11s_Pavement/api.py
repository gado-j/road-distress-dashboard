"""Local YOLO11s detection API for the road distress dashboard.

Uses the supplied checkpoint and the original inference settings (CPU,
confidence 0.10, NMS IoU 0.50, input size 960). No condition score is inferred.
"""
from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import perf_counter
import warnings

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
WEIGHTS = ROOT / 'weights' / 'best.pt'
CLASS_NAMES = ('Crack', 'Pothole', 'Patched crack', 'Patched pothole', 'Clay-patched crack', 'Manhole')
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 4_000_000
model = None
fingerprint = None


@asynccontextmanager
async def lifespan(app):
    global model, fingerprint
    if not WEIGHTS.is_file():
        raise RuntimeError('YOLO checkpoint missing: weights/best.pt')
    model = YOLO(str(WEIGHTS))
    names = tuple(str(model.names[i]) for i in range(len(CLASS_NAMES)))
    if model.task != 'detect' or names != CLASS_NAMES or len(model.names) != len(CLASS_NAMES):
        raise RuntimeError(f'Unexpected YOLO checkpoint task or class mapping: {model.task}, {names}')
    fingerprint = sha256(WEIGHTS.read_bytes()).hexdigest()
    yield
    model = None


app = FastAPI(title='YOLO11s pavement detection', lifespan=lifespan)


@app.post('/analyze')
async def analyze(file: UploadFile = File(...)):
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'Image exceeds 20 MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise HTTPException(415, 'Expected JPEG, PNG, or WebP')
                width, height = source.size
                if not width or not height or width * height > MAX_PIXELS:
                    raise HTTPException(413, 'Image exceeds 4 million pixels')
                image = source.convert('RGB')
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Invalid image')
    import numpy as np
    start = perf_counter()
    result = model.predict(source=np.asarray(image), conf=0.10, iou=0.50,
                           imgsz=960, device='cpu', verbose=False)[0]
    seconds = perf_counter() - start
    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        confidence = float(box.conf.item())
        xyxy = [max(0.0, min(float(limit), float(value))) for value, limit in
                zip(box.xyxy[0].cpu().tolist(), (width, height, width, height))]
        if class_id not in range(len(CLASS_NAMES)) or xyxy[2] <= xyxy[0] or xyxy[3] <= xyxy[1]:
            continue
        detections.append({'class_id': class_id, 'label': CLASS_NAMES[class_id],
                           'confidence': confidence, 'xyxy': xyxy})
    classes = [{'class_id': i, 'label': name,
                'detection_count': sum(d['class_id'] == i for d in detections)}
               for i, name in enumerate(CLASS_NAMES)
               if any(d['class_id'] == i for d in detections)]
    return {'status': 'completed', 'model_name': 'YOLO11s Pavement',
            'model_version': fingerprint, 'task_type': 'detection',
            'image_width': width, 'image_height': height, 'input_size': 960,
            'confidence_threshold': 0.10, 'nms_iou_threshold': 0.50,
            'prediction_seconds': seconds, 'device': 'cpu',
            'classes': classes, 'detections': detections}
