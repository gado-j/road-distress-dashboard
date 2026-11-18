"""Run with: .venv/bin/python tests/check_zip_upload.py

Uses mocked storage and queue; no inspection records are written.
"""
import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


image = io.BytesIO()
Image.new('RGB', (16, 16), 'gray').save(image, format='JPEG')
archive = io.BytesIO()
with __import__('zipfile').ZipFile(archive, 'w', __import__('zipfile').ZIP_DEFLATED) as zipped:
    for number in range(15):
        zipped.writestr(f'images/road_{number:02d}.jpg', image.getvalue())
    zipped.writestr('manifest.csv', 'file,sha256\n')
    zipped.writestr('fake.jpg', 'not an image')
    zipped.writestr('../outside.jpg', image.getvalue())

saved_names = []
def save_image(content, name, mime, width, height, suffix):
    saved_names.append(name)
    return {'id': f'00000000-0000-0000-0000-{len(saved_names):012d}', 'name': name}

with patch.object(app.storage, 'save_image', side_effect=save_image), \
     patch.object(app.storage, 'media_record', side_effect=lambda key: {'id': key, 'upload_status': 'ready'}), \
     patch('analysis_jobs.enqueue', side_effect=lambda record: {'analysis_run_id': record['id']}):
    api = TestClient(app.app)
    result = api.post('/api/upload-zip', files={'file': ('sample.zip', archive.getvalue(), 'application/zip')})
    assert result.status_code == 201, result.text
    assert result.json()['count'] == 16
    assert result.json()['skipped_count'] == 2
    assert len(saved_names) == 16 and 'outside.jpg' in saved_names and '../outside.jpg' not in saved_names
    assert api.post('/api/upload-zip', files={'file': ('broken.zip', b'not a ZIP', 'application/zip')}).status_code == 422
    assert api.post('/api/upload-zip', files={'file': ('wrong.txt', archive.getvalue(), 'text/plain')}).status_code == 422

print('ZIP upload accepted images, skipped other files, and rejected invalid archives')
