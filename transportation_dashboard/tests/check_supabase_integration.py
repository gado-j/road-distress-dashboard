"""Explicit live smoke test: creates one tiny synthetic image and cleans it up.
Run from the dashboard folder: .venv/bin/python tests/check_supabase_integration.py
Never prints backend credentials or signed URLs.
"""
import io
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from fastapi.testclient import TestClient
from app import app
import storage_backend as storage


def main():
    asset_id = inspection_id = None
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get('/api/health').status_code == 200, 'Connection check failed'
        print('PASS: seven tables accessible and both buckets private')
        assert client.get('/database/road_assets.db').status_code == 404
        assert client.post('/api/upload-images', files={'files': ('fake.jpg', b'not an image', 'image/jpeg')}).status_code == 422
        assert client.post('/api/upload-images', headers={'Origin': 'https://untrusted.example'}, files={'files': ('fake.jpg', b'x', 'image/jpeg')}).status_code == 403
        assert client.get('/api/assets', headers={'Host': 'untrusted.example'}).status_code == 403
        print('PASS: invalid images, database exposure, and cross-origin access blocked')
        payload = io.BytesIO()
        Image.new('RGB', (32, 32), color=(100, 100, 100)).save(payload, format='PNG')
        try:
            # This storage-only test isolates automatic scheduling; the model test covers it.
            with patch('analysis_jobs.enqueue', return_value={'status':'queued'}):
                response = client.post('/api/upload-images', files={'files': ('integration-check.png', payload.getvalue(), 'image/png')})
            assert response.status_code == 201 and response.json()['count'] == 1, 'Upload failed'
            asset_id = response.json()['saved'][0]['id']
            record = storage.media_record(asset_id)
            inspection_id = record['inspection_id']
            assert record['width'] == 32 and record['height'] == 32 and record['upload_status'] == 'ready'
            rows = client.get('/api/assets').json()['assets']
            row = next(r for r in rows if r['id'] == asset_id)
            assert row['analysis_status'] == 'not_analyzed' and row['predicted_hazard_type'] is None and row['predicted_risk_score'] is None
            # Fresh record query proves persistence independently of the upload response.
            print('PASS: upload persisted with correct metadata and no fabricated predictions')
            response = client.get(row['url'], follow_redirects=False)
            assert response.status_code == 307, 'Preview redirect failed'
            import httpx
            with httpx.Client() as remote:
                image_response = remote.get(response.headers['location'])
                assert image_response.status_code == 200 and image_response.content == payload.getvalue(), 'Private preview failed'
                original_url = response.headers['location'].split('/object/sign/')[0] + '/object/public/' + record['bucket_id'] + '/' + record['object_path']
                assert remote.get(original_url).status_code != 200, 'Object unexpectedly public'
            print('PASS: signed preview retrieves exact bytes; public URL cannot access file')
            assert client.delete('/api/assets/road_assets.db').status_code == 422
            assert client.delete(f'/api/assets/{asset_id}').status_code == 200
            assert storage.media_record(asset_id) is None
            print('PASS: UUID-based deletion removes test file and media record')
        finally:
            if asset_id:
                record = storage.media_record(asset_id)
                if record:
                    storage.delete_unanalyzed(record)
            if inspection_id:
                storage.client().table('inspections').delete().eq('id', inspection_id).execute()
            print('Temporary test records cleaned up')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Upstream exceptions may embed request details; redact by default.
        print('FAIL:', type(exc).__name__, str(exc) if isinstance(exc, AssertionError) else '(upstream details suppressed)')
        raise SystemExit(1)
