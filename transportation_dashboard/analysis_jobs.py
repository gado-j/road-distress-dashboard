"""Local, single-process analysis queue using the model HTTP API on port 8020.

Queued runs are persisted before scheduling. A single executor serializes model
requests. On restart queued work resumes, while interrupted processing runs are
marked failed so the user can retry. Run one dashboard Uvicorn worker only.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import threading

import httpx
import storage_backend as storage
from test_model_connection import request_analysis_bytes

MODEL_NAME = 'Attain SegFormer-B0'
ENGINE = 'http-auto-v1'
_lock = threading.RLock()
_executor = None
_active = {}
log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def _submit(record, run_id):
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='road-analysis')
    future = _executor.submit(_process, record, run_id)
    _active[record['id']] = (run_id, future)
    def finished(_):
        with _lock:
            if _active.get(record['id'], (None,))[0] == run_id:
                _active.pop(record['id'], None)
    future.add_done_callback(finished)


def enqueue(record):
    """Create one durable queued run per active image; repeated clicks reuse it."""
    with _lock:
        existing = _active.get(record['id'])
        if existing:
            return {'analysis_run_id': existing[0], 'status': 'queued'}
        c = storage.client()
        # Work stranded by an earlier process must not remain processing forever.
        for old in c.table('analysis_runs').select('id,preprocessing').eq('media_id', record['id']).in_('status', ['queued', 'processing']).execute().data:
            if old.get('preprocessing', {}).get('engine') == ENGINE:
                c.table('analysis_runs').update({'status': 'failed', 'error_message': 'Analysis was interrupted. A new attempt has been queued.', 'completed_at': now()}).eq('id', old['id']).execute()
        run = c.table('analysis_runs').insert({
            'media_id': record['id'], 'model_name': MODEL_NAME,
            'model_version': 'pending-model-api', 'task_type': 'segmentation',
            'status': 'queued', 'preprocessing': {'engine': ENGINE, 'resize': [640, 640],
                'original_size_output': True, 'max_original_pixels': 4_000_000}
        }).execute().data[0]
        try:
            _submit(record, run['id'])
        except Exception:
            c.table('analysis_runs').update({'status':'failed','error_message':'Could not schedule analysis. Retry from image details.','completed_at':now()}).eq('id',run['id']).execute()
            raise
        return {'analysis_run_id': run['id'], 'status': 'queued'}


def normalize_result(response, record):
    """Validate the response before persisting it; never manufacture model data."""
    if response.get('status') != 'completed' or response.get('model_name') != MODEL_NAME:
        raise ValueError('Unexpected model status/name')
    width, height = response.get('image_width'), response.get('image_height')
    if (width, height) != (record['width'], record['height']):
        raise ValueError('Model output dimensions do not match original')
    classes = response.get('distresses')
    if not isinstance(classes, list):
        raise ValueError('Invalid model class output')
    mapping = json.loads((Path(__file__).resolve().parent.parent / 'Attain_SegFormer_Portable/class_mapping.json').read_text())
    seen = set()
    total = 0
    for item in classes:
        key, count, fraction = item.get('class_id'), item.get('pixel_count'), item.get('pixel_fraction')
        if type(key) is not int or key not in range(1,8) or key in seen or item.get('label') != mapping[str(key)]:
            raise ValueError('Unknown or duplicate class')
        if type(count) is not int or not 0 < count <= width * height:
            raise ValueError('Invalid pixel count')
        if not isinstance(fraction,(float,int)) or not math.isfinite(fraction) or not math.isclose(fraction,count/(width*height),rel_tol=1e-6,abs_tol=1e-9):
            raise ValueError('Invalid pixel coverage')
        seen.add(key)
        total += count
    if total > width * height:
        raise ValueError('Overlapping argmax classes')
    version = response.get('model_version')
    if not isinstance(version,str) or len(version) != 64 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('Model checkpoint fingerprint missing. Restart model API.')
    seconds = response.get('prediction_seconds')
    if not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Prediction timing missing. Restart model API.')
    return {'model_name': MODEL_NAME, 'model_version': version, 'classes': classes,
            'width':width, 'height':height, 'prediction_seconds':seconds,
            'device':response.get('device','unknown'), 'input_size':[640,640],
            'artifacts_available':False}


def _process(record, run_id):
    c = storage.client()
    try:
        c.table('analysis_runs').update({'status':'processing','started_at':now()}).eq('id',run_id).execute()
        if record['width'] * record['height'] > 4_000_000:
            raise OverflowError('Original exceeds local model pixel limit')
        original = c.storage.from_(record['bucket_id']).download(record['object_path'])
        result = normalize_result(request_analysis_bytes(original, record['original_filename']), record)
        predictions = [{'analysis_run_id':run_id, 'media_id':record['id'],
                        'hazard_type':item['label'], 'output':item} for item in result['classes']]
        if predictions:
            c.table('predictions').insert(predictions).execute()
        c.table('analysis_runs').update({'status':'completed','completed_at':now(),
            'model_version':result['model_version'],'raw_output':result,'error_message':None}).eq('id',run_id).execute()
    except Exception as exc:
        if isinstance(exc, httpx.RequestError):
            message = 'Model API unavailable or timed out. Start the model server on port 8020, then retry.'
        elif isinstance(exc, (OverflowError,)) or isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code == 413:
            message = 'Original saved, but analysis requires at most 4 million pixels and 20 MB. Use a smaller image copy.'
        elif isinstance(exc, ValueError):
            message = 'Unexpected model response. Restart the model API on port 8020 with the current code, then retry.'
        else:
            message = 'Analysis could not complete. Original image is safe. Check both servers and retry.'
        log.warning('Analysis run %s failed (%s)', run_id, type(exc).__name__)
        try:
            c.table('analysis_runs').update({'status':'failed','completed_at':now(),'error_message':message}).eq('id',run_id).execute()
        except Exception:
            log.error('Could not persist failure for run %s; restart recovery can repair it',run_id)


def recover():
    """Resume queued work; make interrupted runs explicitly retryable."""
    c = storage.client()
    pending = []
    offset = 0
    while True:
        batch = c.table('analysis_runs').select('*').in_('status',['queued','processing']).order('created_at').order('id').range(offset,offset+499).execute().data
        pending.extend(batch)
        if len(batch)<500: break
        offset += 500
    with _lock:
        for run in pending:
            if run.get('preprocessing',{}).get('engine') != ENGINE: continue
            if run['status']=='processing':
                c.table('analysis_runs').update({'status':'failed','error_message':'Dashboard restarted during analysis. Retry this image.','completed_at':now()}).eq('id',run['id']).execute()
            else:
                record=storage.media_record(run['media_id'])
                if record and record['upload_status']=='ready': _submit(record,run['id'])


def shutdown():
    global _executor
    if _executor:
        _executor.shutdown(wait=True)
        _executor=None
