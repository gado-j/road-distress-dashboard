"""Single-worker local integration: serialize analyses and reuse the model process."""
import atexit
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import subprocess
from tempfile import TemporaryDirectory
import threading
import storage_backend as storage

MODEL_DIR = Path(__file__).resolve().parent.parent / 'Attain_SegFormer_Portable'
_lock = threading.Lock()
_worker = None


def stop_worker():
    global _worker
    if _worker is not None:
        _worker.kill() if _worker.poll() is None else None
        _worker.wait()
        _worker = None


atexit.register(stop_worker)


def infer(image_path, output):
    global _worker
    if _worker is None or _worker.poll() is not None:
        # The model subprocess does not need the dashboard's backend credentials.
        env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ('KEY', 'TOKEN', 'SECRET', 'SUPABASE'))}
        _worker = subprocess.Popen([str(MODEL_DIR / '.venv/bin/python'), str(MODEL_DIR / 'dashboard_worker.py')],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    try:
        _worker.stdin.write(json.dumps({'image': str(image_path), 'output': str(output)}) + '\n')
        _worker.stdin.flush()
        if not select.select([_worker.stdout], [], [], 120)[0]:
            raise TimeoutError('Model analysis timed out.')
        response = json.loads(_worker.stdout.readline())
    except Exception:
        stop_worker()
        raise
    if 'error' in response:
        raise ValueError(response['error'])
    return response['result']


def analyze(record):
    """Write completion only after all results and artifacts have persisted.

    A failed run remains as history; its partial results are not shown as valid.
    This prototype requires a single FastAPI worker and uses no durable job queue.
    """
    if not _lock.acquire(blocking=False):
        raise BlockingIOError('Another image is being analyzed. Try again shortly.')
    run_id = None
    c = None
    now = lambda: datetime.now(timezone.utc).isoformat()
    try:
        c = storage.client()
        if record.get('width', 0) * record.get('height', 0) > 4_000_000:
            raise ValueError('Use an image with at most 4 million pixels for local analysis.')
        run = c.table('analysis_runs').insert({'media_id': record['id'], 'model_name': 'Attain SegFormer-B0',
            'model_version': 'pending-checkpoint-fingerprint', 'task_type': 'segmentation', 'status': 'processing',
            'started_at': now(), 'preprocessing': {'resize': [640, 640], 'original_size_output': True}}).execute().data[0]
        run_id = run['id']
        with TemporaryDirectory(prefix='road-analysis-') as folder:
            folder = Path(folder)
            image_path = folder / 'original'
            image_path.write_bytes(c.storage.from_(record['bucket_id']).download(record['object_path']))
            result = infer(image_path, folder)
            predictions = [{'analysis_run_id': run_id, 'media_id': record['id'], 'hazard_type': item['label'],
                            'output': item} for item in result['classes'] if item['class_id'] != 0]
            if predictions:
                c.table('predictions').insert(predictions).execute()
            for kind in ('mask', 'overlay'):
                content = (folder / f'{kind}.png').read_bytes()
                path = f"{record['inspection_id']}/{record['id']}/{run_id}/{kind}.png"
                c.storage.from_(storage.ARTIFACTS_BUCKET).upload(path, content, {'content-type': 'image/png', 'upsert': 'false'})
                c.table('analysis_artifacts').insert({'analysis_run_id': run_id, 'artifact_type': kind,
                    'bucket_id': storage.ARTIFACTS_BUCKET, 'object_path': path, 'byte_size': len(content),
                    'metadata': {'width': result['width'], 'height': result['height'],
                                 'colors': 'Categorical model classes; not road risk'}}).execute()
            c.table('analysis_runs').update({'status': 'completed', 'completed_at': now(),
                'model_version': result['model_version'], 'raw_output': result}).eq('id', run_id).execute()
        return {'analysis_run_id': run_id, 'status': 'completed', 'result': result}
    except Exception:
        if run_id:
            c.table('analysis_runs').update({'status': 'failed', 'error_message': 'Analysis could not complete. Retry or check local server logs.',
                                           'completed_at': now()}).eq('id', run_id).execute()
        raise
    finally:
        _lock.release()
