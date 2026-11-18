"""Run with: .venv/bin/python tests/check_analysis_report.py"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analysis_report as report


class Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_): return self
    def eq(self, *_): return self
    def gte(self, *_): return self
    def lt(self, *_): return self
    def order(self, *_ , **__): return self
    def range(self, *_): return self
    def execute(self): return type('Result', (), {'data': self.rows})()


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name):
        assert name == 'analysis_runs'
        return Query(self.rows)


assert report.date_bounds(date(2026, 11, 1), date(2026, 11, 1)) == (
    '2026-11-01T05:00:00+00:00', '2026-11-02T06:00:00+00:00')

try:
    report.date_bounds(date(2026, 11, 18), date(2026, 11, 17))
    raise AssertionError('Reversed dates were accepted')
except ValueError:
    pass

run = {'id': '22222222-2222-2222-2222-222222222222',
       'media_id': '11111111-1111-1111-1111-111111111111',
       'model_name': 'YOLO11s Pavement', 'task_type': 'detection',
       'completed_at': '2026-11-17T18:00:00+00:00',
       'raw_output': {'task_type': 'detection', 'model_name': 'YOLO11s Pavement',
                      'detections': [{'label': '<Crack>', 'confidence': .7}]}}
with patch.object(report.storage, 'client', return_value=Client([run, {**run, 'id': 'older'}])):
    assert len(report.completed_runs(date(2026, 11, 17), date(2026, 11, 17))) == 1
with patch.object(report.storage, 'media_record', return_value={
    'id': run['media_id'], 'original_filename': 'road<1>.jpg',
    'width': 512, 'height': 512, 'upload_status': 'ready'}):
    html = report.render(date(2026, 11, 17), date(2026, 11, 17), [run])
    assert 'road&lt;1&gt;.jpg' in html and 'road<1>.jpg' not in html
    assert '&lt;Crack&gt;' in html and '70.0%' in html
    assert 'detections-preview' in html and 'Print / Save as PDF' in html

print('Report date bounds, latest-run selection, and printable results passed')
