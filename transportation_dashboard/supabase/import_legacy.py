"""Import existing SQLite images while preserving demo provenance.
Reruns skip already imported ready media. Never insert random values as genuine
model predictions. Original SQLite files remain unchanged.
"""
import io
import sqlite3
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage_backend as storage


def main():
    directory = storage.BASE_DIR / 'database'
    conn = sqlite3.connect(f'file:{directory / "road_assets.db"}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    records = conn.execute('select * from road_images order by upload_date desc').fetchall()
    if any(r['expert_annotated'] for r in records):
        raise ValueError('Expert-reviewed records require a reviewer identity mapping before import')
    for row in records:
        content = (directory / Path(row['image_path']).name).read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            fmt, (width, height) = image.format, image.size
            image.verify()
        mime, suffix = {'JPEG': ('image/jpeg', '.jpg'), 'PNG': ('image/png', '.png'), 'WEBP': ('image/webp', '.webp')}[fmt]
        result = storage.save_image(content, Path(row['image_path']).name, mime, width, height, suffix, legacy=dict(row))
        print('Skipped existing' if result.get('skipped') else 'Imported', row['id'], Path(row['image_path']).name)
    assets = storage.list_assets()
    imported = [a for a in assets if a.get('legacy_demo')]
    assert len(imported) == len(records), 'Imported record count mismatch'
    assert all(a['predicted_hazard_type'] is None for a in imported), 'Demo values must not be model predictions'
    print(f'Verified {len(imported)} legacy images available newest-first; demo provenance preserved.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Import failed:', type(exc).__name__, '(details suppressed to protect credentials)')
        raise SystemExit(1)
