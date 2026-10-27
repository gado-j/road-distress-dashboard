"""Server-only Supabase persistence for original inspection images."""
from functools import lru_cache
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL
import hashlib
import os
import json

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env.local', override=False)
MEDIA_BUCKET = os.getenv('SUPABASE_MEDIA_BUCKET', 'inspection-media')
ARTIFACTS_BUCKET = os.getenv('SUPABASE_ARTIFACTS_BUCKET', 'analysis-artifacts')


@lru_cache(maxsize=1)
def client():
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_SECRET_KEY', '').strip()
    if not url or not key:
        raise RuntimeError('Missing backend Supabase configuration')
    return create_client(url, key)


def check_connection():
    """Read-only checks; never return credentials or detailed upstream errors."""
    c = client()
    for table in ('roads', 'inspections', 'media', 'analysis_runs', 'predictions', 'expert_reviews', 'analysis_artifacts'):
        c.table(table).select('id').limit(1).execute()
    for name in (MEDIA_BUCKET, ARTIFACTS_BUCKET):
        bucket = c.storage.get_bucket(name)
        if bucket.public:
            raise RuntimeError('Inspection buckets must be private')
    return {'database': 'connected', 'storage': 'connected', 'buckets_private': True}


def save_image(content, filename, mime, width, height, suffix, legacy=None):
    """Create a pending record, upload original bytes, then mark ready.

    One request/file creates one inspection until grouping UI is introduced.
    Failed uploads keep a failed media record for diagnosis/retry. No predictions
    are inserted until a real model is connected.
    """
    c = client()
    inspection_id, media_id = str(uuid4()), str(uuid4())
    if legacy:
        media_id = str(uuid5(NAMESPACE_URL, f"road-dashboard-legacy/{legacy['id']}/{hashlib.sha256(content).hexdigest()}"))
        existing = media_record(media_id)
        if existing:
            if existing['upload_status'] == 'ready':
                return {'id': media_id, 'name': filename, 'skipped': True}
            delete_unanalyzed(existing)
    path = f'{inspection_id}/{media_id}/original{suffix}'
    inspection = {'id': inspection_id, 'source': 'import' if legacy else 'manual'}
    if legacy:
        inspection.update({'notes': json.dumps({'legacy_demo': legacy}), 'created_at': legacy['upload_date']})
    c.table('inspections').insert(inspection).execute()
    try:
        c.table('media').insert({
            'id': media_id, 'inspection_id': inspection_id,
            'bucket_id': MEDIA_BUCKET, 'object_path': path,
            'original_filename': filename, 'media_type': 'image',
            'mime_type': mime, 'byte_size': len(content), 'width': width,
            'height': height, 'sha256': hashlib.sha256(content).hexdigest(),
            'upload_status': 'pending',
            **({'created_at': legacy['upload_date']} if legacy else {}),
        }).execute()
    except Exception:
        c.table('inspections').delete().eq('id', inspection_id).execute()
        raise
    try:
        c.storage.from_(MEDIA_BUCKET).upload(path, content, {'content-type': mime, 'upsert': 'false'})
        c.table('media').update({'upload_status': 'ready'}).eq('id', media_id).execute()
    except Exception:
        # Removing our UUID-scoped object also handles an uncertain upload response.
        try:
            c.storage.from_(MEDIA_BUCKET).remove([path])
        finally:
            c.table('media').update({'upload_status': 'failed'}).eq('id', media_id).execute()
        raise
    return {'id': media_id, 'name': filename, 'analysis_status': 'not_analyzed'}


def media_record(media_id):
    rows = client().table('media').select('*').eq('id', str(media_id)).limit(1).execute().data
    return rows[0] if rows else None


def preview_url(record):
    result = client().storage.from_(record['bucket_id']).create_signed_url(record['object_path'], 300)
    return result['signedURL']


def list_assets():
    """Page original media and related results instead of silently truncating at 1000."""
    c = client()
    def rows(table, configure=lambda q: q):
        output = []
        while True:
            batch = configure(c.table(table).select('*')).order('created_at', desc=True).order('id').range(len(output), len(output) + 499).execute().data
            output.extend(batch)
            if len(batch) < 500:
                return output
    media = rows('media', lambda q: q.eq('upload_status', 'ready'))
    runs, predictions, reviews = rows('analysis_runs'), rows('predictions'), rows('expert_reviews')
    legacy_map = {}
    for inspection in rows('inspections'):
        if inspection['source'] == 'import':
            try:
                legacy_map[inspection['id']] = json.loads(inspection.get('notes') or '{}').get('legacy_demo', {})
            except (ValueError, AttributeError):
                pass
    run_map, pred_map, review_map = {}, {}, {}
    for run in runs:
        run_map.setdefault(run['media_id'], run)
    for prediction in predictions:
        pred_map.setdefault(prediction['analysis_run_id'], prediction)
    for review in reviews:
        review_map.setdefault(review['media_id'], review)
    assets = []
    for m in media:
        run = run_map.get(m['id'])
        prediction = pred_map.get(run['id'], {}) if run and run['status'] == 'completed' else {}
        result = (run.get('raw_output') or {}) if run and run['status'] == 'completed' else {}
        classes = [item for item in result.get('classes', []) if item['class_id'] != 0]
        review = review_map.get(m['id'], {})
        # This compatibility view shows one result; the schema retains all results.
        hazard = ', '.join(item['label'] for item in classes) or prediction.get('hazard_type')
        if result and not classes:
            hazard = 'No distress predicted'
        legacy = legacy_map.get(m['inspection_id'], {})
        def risk_label(value):
            return f'{value.title()} Risk' if value else None
        assets.append({
            'id': m['id'], 'inspection_id': m['inspection_id'],
            'name': m['original_filename'], 'image_path': m['original_filename'],
            'model_result': result or None, 'analysis_error': run.get('error_message') if run else None,
            'analysis_run_id': run['id'] if run else None,
            'width': m.get('width'), 'height': m.get('height'), 'byte_size': m.get('byte_size'),
            'mime_type': m.get('mime_type'), 'confidence': prediction.get('confidence'),
            'score_definition': prediction.get('score_definition'),
            'url': f"/api/assets/{m['id']}/preview", 'upload_date': m['created_at'],
            'class_name': hazard or (f"Demo: {legacy['predicted_hazard_type']}" if legacy else 'Not analyzed'),
            'legacy_demo': legacy or None, 'predicted_hazard_type': hazard,
            'predicted_risk_condition': risk_label(prediction.get('risk_condition')),
            'predicted_risk_score': prediction.get('score'),
            'expert_hazard_type': review.get('hazard_type'),
            'expert_risk_condition': risk_label(review.get('risk_condition')),
            'expert_risk_score': review.get('score'), 'expert_comments': review.get('comments'),
            'expert_annotated': bool(review), 'analysis_status': run['status'] if run else 'not_analyzed',
        })
    return assets


def delete_unanalyzed(record):
    """Delete only uploads without retained analysis/review history."""
    c = client()
    for table in ('analysis_runs', 'expert_reviews'):
        if c.table(table).select('id').eq('media_id', record['id']).limit(1).execute().data:
            return False
    # Failed status hides the record during removal. A retry can finish cleanup.
    c.table('media').update({'upload_status': 'failed'}).eq('id', record['id']).execute()
    c.storage.from_(record['bucket_id']).remove([record['object_path']])
    c.table('media').delete().eq('id', record['id']).execute()
    # Leave inspection context intact; grouped inspections may contain other media.
    return True
