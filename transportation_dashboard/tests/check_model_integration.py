"""Live automatic-analysis smoke test. Only temporary test uploads are removed."""
import io
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from PIL import Image
import analysis_jobs as jobs
from app import app
import storage_backend as storage

c = storage.client()
created = []
model_dir = Path(__file__).resolve().parents[2] / 'Attain_SegFormer_Portable'


def upload(api, content, name):
    response=api.post('/api/upload-images',files={'files':(name,content,'image/jpeg')})
    assert response.status_code==201, response.text
    saved=response.json()['saved'][0]
    assert saved['analysis_run_id'] and not response.json()['analysis_errors']
    record=storage.media_record(saved['id'])
    created.append(record)
    return saved,record


def wait_run(run_id,status):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        run=c.table('analysis_runs').select('*').eq('id',run_id).execute().data[0]
        if run['status'] in ('completed','failed'):
            assert run['status']==status, (run['status'],run.get('error_message'))
            return run
        time.sleep(.3)
    raise AssertionError('Analysis timed out')


def cleanup():
    jobs.shutdown()
    for record in created:
        for run in c.table('analysis_runs').select('id').eq('media_id',record['id']).execute().data:
            for a in c.table('analysis_artifacts').select('*').eq('analysis_run_id',run['id']).execute().data:
                c.storage.from_(a['bucket_id']).remove([a['object_path']])
            c.table('analysis_artifacts').delete().eq('analysis_run_id',run['id']).execute()
            c.table('predictions').delete().eq('analysis_run_id',run['id']).execute()
        c.table('analysis_runs').delete().eq('media_id',record['id']).execute()
        storage.delete_unanalyzed(record)
        c.table('inspections').delete().eq('id',record['inspection_id']).execute()


try:
    with TestClient(app) as api:
        saved,record=upload(api,(model_dir/'road2.jpg').read_bytes(),'auto-analysis-crack.jpg')
        run=wait_run(saved['analysis_run_id'],'completed')
        assert any(item['class_id']==5 for item in run['raw_output']['classes'])
        assert len(run['model_version'])==64
        rows=c.table('predictions').select('*').eq('analysis_run_id',run['id']).execute().data
        assert rows and all(r['risk_condition'] is None and r['confidence'] is None for r in rows)
        asset=next(a for a in api.get('/api/assets').json()['assets'] if a['id']==record['id'])
        assert asset['analysis_status']=='completed' and 'Linear crack' in asset['predicted_hazard_type']
        assert api.delete(f"/api/assets/{record['id']}").status_code==409
        print('PASS: upload automatically analyzed by real API; saved labels, fingerprint, timing; no invented risk/confidence')
        saved,record=upload(api,(model_dir/'road.jpg').read_bytes(),'auto-analysis-background.jpg')
        run=wait_run(saved['analysis_run_id'],'completed')
        assert run['raw_output']['classes']==[]
        assert c.table('predictions').select('id').eq('analysis_run_id',run['id']).execute().data==[]
        asset=next(a for a in api.get('/api/assets').json()['assets'] if a['id']==record['id'])
        assert asset['predicted_hazard_type']=='No distress predicted'
        print('PASS: real background-only result is completed and saved, with zero distress rows')
        with patch.object(jobs,'request_analysis_bytes',side_effect=httpx.ConnectError('simulated offline')):
            saved,record=upload(api,(model_dir/'road2.jpg').read_bytes(),'auto-analysis-retry.jpg')
            failed=wait_run(saved['analysis_run_id'],'failed')
            assert '8020' in failed['error_message']
            assert storage.media_record(record['id'])['upload_status']=='ready'
        # Ensure previous callback has released this image before retrying.
        deadline=time.monotonic()+5
        while record['id'] in jobs._active and time.monotonic()<deadline: time.sleep(.05)
        release=threading.Event()
        original=jobs.request_analysis_bytes
        def delayed(*args):
            assert release.wait(20)
            return original(*args)
        with patch.object(jobs,'request_analysis_bytes',side_effect=delayed):
            try:
                first=api.post(f"/api/assets/{record['id']}/analyze")
                second=api.post(f"/api/assets/{record['id']}/analyze")
                assert first.status_code==second.status_code==202
                assert first.json()['analysis_run_id']==second.json()['analysis_run_id']
            finally: release.set()
            wait_run(first.json()['analysis_run_id'],'completed')
        assert len(c.table('analysis_runs').select('id').eq('media_id',record['id']).execute().data)==2
        print('PASS: failed analysis retains original; retry succeeds; concurrent duplicate clicks share one run; failed history preserved')
finally:
    cleanup()
    print('Temporary test records cleaned up')
