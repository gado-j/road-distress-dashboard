"""Read-only, printable reports of saved model runs."""
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

import storage_backend as storage

CENTRAL = ZoneInfo('America/Chicago')
MAX_RUNS = 200


def date_bounds(from_date: date, to_date: date):
    if to_date < from_date:
        raise ValueError('End date must be on or after start date.')
    if (to_date - from_date).days > 366:
        raise ValueError('Choose a date range of at most one year.')
    start = datetime.combine(from_date, time.min, CENTRAL).astimezone(timezone.utc)
    end = datetime.combine(to_date + timedelta(days=1), time.min, CENTRAL).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


def completed_runs(from_date: date, to_date: date):
    start, end = date_bounds(from_date, to_date)
    rows = (storage.client().table('analysis_runs')
            .select('id,media_id,model_name,model_version,task_type,status,raw_output,completed_at')
            .eq('status', 'completed').gte('completed_at', start).lt('completed_at', end)
            .order('completed_at', desc=True).range(0, MAX_RUNS).execute().data)
    if len(rows) > MAX_RUNS:
        raise ValueError(f'This range contains more than {MAX_RUNS} analyses. Choose a shorter period.')
    # One image appears once in a report, using its latest completed run in range.
    latest = {}
    for row in rows:
        latest.setdefault(row['media_id'], row)
    return list(latest.values())


def local_time(value):
    if not value:
        return 'Not recorded'
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(CENTRAL).strftime('%b %d, %Y · %I:%M %p %Z')


def result_lines(result):
    if result.get('task_type') == 'detection':
        boxes = result.get('detections') or []
        if not boxes:
            return '<p>No detections above the configured threshold. This does not verify that the road is distress-free.</p>'
        return '<ul>' + ''.join(
            f'<li><strong>{escape(str(box.get("label", "Detection")))}</strong> · '
            f'{float(box.get("confidence", 0)) * 100:.1f}% detection confidence</li>'
            for box in boxes
        ) + '</ul>'
    classes = [item for item in result.get('classes', []) if item.get('label') != 'Background']
    if not classes:
        return '<p>No distress pixels predicted. This does not verify that the road is distress-free.</p>'
    return '<ul>' + ''.join(
        f'<li><strong>{escape(str(item.get("label", "Class")))}</strong> · '
        f'{float(item.get("pixel_fraction", 0)) * 100:.2f}% of image pixels</li>'
        for item in classes
    ) + '</ul>'


def render(from_date: date, to_date: date, runs):
    cards = []
    image_count = 0
    for run in runs:
        media = storage.media_record(run['media_id'])
        if not media or media.get('upload_status') != 'ready':
            continue
        image_count += 1
        result = run.get('raw_output') or {}
        run_id = escape(str(run['id']), quote=True)
        media_id = escape(str(media['id']), quote=True)
        original = f'/api/assets/{media_id}/preview'
        visual = (f'/api/analysis/{run_id}/detections-preview'
                  if result.get('task_type') == 'detection' and result.get('model_name') == 'YOLO11s Pavement'
                  else f'/api/analysis/{run_id}/overlay' if result.get('artifacts_available') else None)
        evidence = f'<figure><img src="{visual}" alt="Saved model result for {media_id}"><figcaption>Saved model result</figcaption></figure>' if visual else ''
        cards.append(f'''<article class="record">
          <header><div><h2>{escape(str(media['original_filename']))}</h2><p>Image ID: {media_id}</p></div>
          <span>{escape(local_time(run.get('completed_at')))}</span></header>
          <p><strong>Model:</strong> {escape(str(run.get('model_name') or 'Unknown'))} ·
          <strong>Task:</strong> {escape(str(run.get('task_type') or 'Unknown'))}</p>
          <p><strong>Image:</strong> {media.get('width') or '—'} × {media.get('height') or '—'} px ·
          <strong>Run ID:</strong> {run_id}</p>
          <div class="evidence"><figure><img src="{original}" alt="Original road image for {media_id}"><figcaption>Original image</figcaption></figure>{evidence}</div>
          <h3>Saved analysis</h3>{result_lines(result)}
        </article>''')
    heading = f'{from_date.isoformat()} through {to_date.isoformat()}'
    content = ''.join(cards) or '<p class="empty">No completed analyses with available originals were found in this period.</p>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>Analysis report · {heading}</title>
    <style>
      @page {{ size: letter; margin: 0.6in; }}
      * {{ box-sizing: border-box; }} body {{ font: 14px/1.45 system-ui, sans-serif; color:#102c34; margin:0 auto; max-width:980px; padding:24px; }}
      h1 {{ font-size:27px; margin:0 0 3px; }} h2 {{ font-size:18px; margin:0; }} h3 {{ font-size:14px; margin:12px 0 4px; }}
      p {{ margin:5px 0; }} .muted, figcaption, header span {{ color:#60736f; }}
      .toolbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:22px; }}
      button {{ border:0; border-radius:7px; padding:10px 16px; color:white; background:#007e80; cursor:pointer; }}
      .record {{ border:1px solid #d9e3df; border-radius:10px; padding:17px; margin:16px 0; break-inside:avoid; }}
      .record header {{ display:flex; justify-content:space-between; align-items:start; gap:12px; border-bottom:1px solid #e5ebe7; padding-bottom:9px; margin-bottom:9px; }}
      .record header p {{ font-size:11px; color:#60736f; }} .record header span {{ font-size:11px; white-space:nowrap; }}
      .evidence {{ display:flex; gap:12px; margin-top:12px; }} figure {{ margin:0; flex:1; min-width:0; }}
      figure img {{ display:block; width:100%; max-height:280px; object-fit:contain; background:#eef1ec; border-radius:6px; }}
      figcaption {{ font-size:11px; margin-top:4px; }} ul {{ margin:5px 0 0; padding-left:20px; }} li {{ margin:3px 0; }}
      .empty {{ padding:25px; background:#f2f6f3; }} .note {{ font-size:11px; color:#536661; margin:15px 0; }}
      @media print {{ body {{ padding:0; max-width:none; }} .toolbar button {{ display:none; }} .record {{ box-shadow:none; }} }}
      @media(max-width:600px) {{ .evidence {{ flex-direction:column; }} .record header {{ flex-direction:column; }} }}
    </style></head><body><div class="toolbar"><div><h1>Road distress analysis report</h1>
    <p class="muted">Completed analyses: {escape(heading)} · Central Time</p></div>
    <button type="button" onclick="window.print()">Print / Save as PDF</button></div>
    <p><strong>{image_count}</strong> analyzed images · Generated {escape(local_time(datetime.now(timezone.utc).isoformat()))}</p>
    <p class="note">Results are saved model outputs. Detection confidence and pixel coverage are not severity, road risk, or verified ground truth. This report shows the latest completed run per image within the chosen dates.</p>
    {content}<script>document.querySelectorAll('img').forEach(img => img.addEventListener('error', () => {{ img.alt = 'Image could not be loaded'; }}));</script>
    </body></html>'''
