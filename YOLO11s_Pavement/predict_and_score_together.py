#!/usr/bin/env python3
"""PaveTrack_OD detection-to-feature-to-experimental-index pipeline.

THIS DOES NOT ESTIMATE VALIDATED PCI. Requires installed ultralytics, PIL,
NumPy, Matplotlib (environment already present in Delta project may have these).
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CLASSES = ['Crack','Pothole','Patched crack','Patched pothole','Clay-patched crack','Manhole']
SUFFIXES = {'.jpg','.jpeg','.png','.bmp','.webp','.tif','.tiff'}


def rectangle_union_area(boxes):
    """Exact union of clipped axis-aligned rectangles (pixel coordinates)."""
    boxes = [tuple(map(float, b)) for b in boxes if b[2] > b[0] and b[3] > b[1]]
    if not boxes: return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    area = 0.0
    for left, right in zip(xs[:-1], xs[1:]):
        if right <= left: continue
        spans = sorted((b[1], b[3]) for b in boxes if b[0] < right and b[2] > left)
        if not spans: continue
        lo, hi = spans[0]
        covered_y = 0.0
        for y0,y1 in spans[1:]:
            if y0 <= hi:
                hi = max(hi,y1)
            else:
                covered_y += hi-lo
                lo,hi = y0,y1
        covered_y += hi-lo
        area += covered_y*(right-left)
    return area


def clip_box(b, width, height):
    x1,y1,x2,y2 = (float(v) for v in b)
    return (max(0.,min(float(width),x1)),max(0.,min(float(height),y1)),
            max(0.,min(float(width),x2)),max(0.,min(float(height),y2)))


def extract_one(path, model, outdir, conf, iou, imgsz, exclude_ids, class_names, save_annotated):
    with Image.open(path) as src:
        orig = src.convert('RGB')
    width,height = orig.size
    total_area = width*height
    if total_area <= 0: raise ValueError(f'Empty image: {path}')

    pred = model.predict(source=str(path),conf=conf,iou=iou,imgsz=imgsz,device='cpu',verbose=False)[0]
    boxes = []
    if pred.boxes is not None:
        for b in pred.boxes:
            cid = int(b.cls.item())
            if cid < 0 or cid >= len(class_names):
                raise ValueError(f'Unexpected class id {cid}: {path}')
            xyxy = clip_box(b.xyxy[0].cpu().tolist(),width,height)
            if xyxy[2] <= xyxy[0] or xyxy[3] <= xyxy[1]: continue
            boxes.append({'class_id':cid,'class_name':class_names[cid],
                          'confidence':float(b.conf.item()),'xyxy':xyxy})

    scoring_boxes = [b for b in boxes if b['class_id'] not in exclude_ids]
    uarea = rectangle_union_area([b['xyxy'] for b in scoring_boxes])
    coverage = 100.0*uarea/total_area
    coverage = min(100.,max(0.,coverage))
    # This is *only* the inverse image fraction covered by predicted boxes.
    score = max(0.,min(100.,100.0-coverage))

    feats = {
        'image':path.name,
        'original_image':str(path),
        'width_px':width,'height_px':height,
        'detections_all':len(boxes),
        'detections_scored':len(scoring_boxes),
        'box_union_coverage_pct':round(coverage,4),
        'demo_index_not_pci':round(score,4),
        'score_status':'UNVALIDATED_BOX_PROXY_NOT_PCI',
    }
    for cid,name in enumerate(class_names):
        key = 'class_'+str(cid)
        group = [b for b in boxes if b['class_id']==cid]
        rect_areas = [(b['xyxy'][2]-b['xyxy'][0])*(b['xyxy'][3]-b['xyxy'][1]) for b in group]
        aspect = [max(b['xyxy'][2]-b['xyxy'][0],b['xyxy'][3]-b['xyxy'][1]) /
                  max(1e-9,min(b['xyxy'][2]-b['xyxy'][0],b['xyxy'][3]-b['xyxy'][1])) for b in group]
        feats[key+'_name'] = name
        feats[key+'_count'] = len(group)
        feats[key+'_union_pct'] = round(100*rectangle_union_area([b['xyxy'] for b in group])/total_area,4)
        feats[key+'_mean_conf'] = round(mean(b['confidence'] for b in group),4) if group else ''
        feats[key+'_max_box_pct'] = round(100*max(rect_areas)/total_area,4) if group else 0.
        feats[key+'_mean_elongation'] = round(mean(aspect),4) if group else ''
    # For center-band and 3x3 zones, use box centers; quantities do not have a physical scale.
    centers = [((b['xyxy'][0]+b['xyxy'][2])/(2*width),
                (b['xyxy'][1]+b['xyxy'][3])/(2*height)) for b in scoring_boxes]
    feats['center_third_count'] = sum(1 for x,y in centers if 1/3 <= x < 2/3)
    for row in range(3):
        for col in range(3):
            feats[f'grid_r{row+1}_c{col+1}_count'] = sum(
                1 for x,y in centers
                if min(2,int(y*3)) == row and min(2,int(x*3)) == col
            )
    # Persist each box separately; all coords are image pixels, not meters.
    per_box = []
    for index,b in enumerate(boxes):
        x1,y1,x2,y2 = b['xyxy']
        bw,bh = x2-x1,y2-y1
        per_box.append({
            'image':path.name,'detection_id':index,
            'class_id':b['class_id'],'class_name':b['class_name'],
            'confidence':round(b['confidence'],6),
            'x1_px':round(x1,3),'y1_px':round(y1,3),
            'x2_px':round(x2,3),'y2_px':round(y2,3),
            'box_width_px':round(bw,3),'box_height_px':round(bh,3),
            'box_area_pct':round(100*bw*bh/total_area,5),
            'elongation':round(max(bw,bh)/max(1e-9,min(bw,bh)),4),
            'included_in_demo_score':int(b['class_id'] not in exclude_ids),
        })
    if save_annotated:
        canvas = orig.copy()
        draw=ImageDraw.Draw(canvas)
        for b in boxes:
            x1,y1,x2,y2=b['xyxy']
            color = '#F39C12' if b['class_id'] in exclude_ids else '#16B5E8'
            draw.rectangle((x1,y1,x2,y2),outline=color,width=3)
            text=f"{b['class_name']} {b['confidence']:.2f}"
            draw.text((max(0,x1),max(0,y1-13)),text,fill=color,stroke_width=1,stroke_fill='black')
        label=f"DEMO INDEX {score:.1f}/100 (NOT PCI) | box union {coverage:.1f}%"
        draw.rectangle((0,0,min(width,10+len(label)*9),26),fill='black')
        draw.text((6,5),label,fill='white')
        pathout = outdir/'annotated'/(path.stem+'_scored.jpg')
        canvas.save(pathout,quality=87)
        feats['annotated_image'] = str(pathout)
    else:
        feats['annotated_image'] = ''
    return feats,per_box


def write_csv(path,rows,header=None):
    if not rows and not header: raise ValueError('Cannot determine CSV header with no rows')
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=header or list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def figures(rows, outdir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    scores = np.array([r['demo_index_not_pci'] for r in rows])
    cov = np.array([r['box_union_coverage_pct'] for r in rows])
    fig,ax=plt.subplots(figsize=(8,4.6))
    ax.hist(scores,bins=np.linspace(0,100,21),edgecolor='black',linewidth=.4)
    ax.set(xlabel='Experimental inverse-box index (NOT PCI)',ylabel='Image count',title='PaveTrack_OD validation: experimental scoring distribution')
    fig.tight_layout(); fig.savefig(outdir/'demo_score_histogram.png',dpi=170); plt.close(fig)
    ids=np.argsort(cov)[-10:][::-1]
    fig,ax=plt.subplots(figsize=(9,5.5))
    ax.barh([rows[int(i)]['image'] for i in ids[::-1]],cov[ids[::-1]])
    ax.set(xlabel='Union coverage of predicted boxes (%)',title='Highest-coverage predictions: quality-control review')
    fig.tight_layout(); fig.savefig(outdir/'top10_coverage.png',dpi=170); plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--weights',required=True)
    ap.add_argument('--source',required=True,help='Input image file or directory of images')
    ap.add_argument('--out',default='results/pavetrack_scoring_complete')
    ap.add_argument('--conf',type=float,default=.10)
    ap.add_argument('--iou',type=float,default=.50)
    ap.add_argument('--imgsz',type=int,default=960)
    ap.add_argument('--exclude-ids',default='5',help='Comma-separated ids, default 5=Manhole (provisional)')
    ap.add_argument('--no-annotated',action='store_true')
    args=ap.parse_args()
    if not 0<args.conf<=1 or not 0<args.iou<=1: raise ValueError('conf and iou must be in (0,1]')
    src=Path(args.source)
    out=Path(args.out)
    if not src.exists(): raise FileNotFoundError(src)
    if not Path(args.weights).is_file(): raise FileNotFoundError(args.weights)
    if src.is_file():
        if src.suffix.lower() not in SUFFIXES: raise ValueError(f'Not an image: {src}')
        paths = [src]
    else:
        paths = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)
    if not paths: raise RuntimeError(f'No images found in {src}')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_annotated: (out/'annotated').mkdir(exist_ok=True)
    exclude_ids={int(x.strip()) for x in args.exclude_ids.split(',') if x.strip()}
    if not exclude_ids.issubset(set(range(len(CLASSES)))): raise ValueError('invalid exclude IDs')
    from ultralytics import YOLO
    model=YOLO(args.weights)
    model_names = model.names
    actual = [str(model_names[i]) for i in range(len(CLASSES))]
    # Names from checkpoints may be class0/class1; do not claim these provisional labels are verified.
    print('Checkpoint class names:',actual,flush=True)
    print('Assumed provisional mapping:',CLASSES,flush=True)
    rows=[]; box_rows=[]
    for i,path in enumerate(paths,1):
        feat,boxes=extract_one(path,model,out,args.conf,args.iou,args.imgsz,exclude_ids,CLASSES,not args.no_annotated)
        rows.append(feat);box_rows.extend(boxes)
        if i%25==0 or i==len(paths): print(f'Processed {i}/{len(paths)}',flush=True)
    write_csv(out/'image_features_and_demo_scores.csv',rows)
    write_csv(out/'detections_per_box.csv',box_rows,header=[
        'image','detection_id','class_id','class_name','confidence',
        'x1_px','y1_px','x2_px','y2_px','box_width_px','box_height_px',
        'box_area_pct','elongation','included_in_demo_score'])
    figures(rows,out)
    covs=[r['box_union_coverage_pct'] for r in rows]
    scores=[r['demo_index_not_pci'] for r in rows]
    summary={
        'status':'UNVALIDATED_DEMONSTRATION_NOT_PCI',
        'source_dataset':'PaveTrack_OD/US; user-specified --source',
        'evaluation_split':'user-provided image(s); no ground-truth scoring labels',
        'images_processed':len(rows),
        'detections_total':len(box_rows),
        'images_without_detections':sum(r['detections_all']==0 for r in rows),
        'confidence_threshold':args.conf,'nms_iou_threshold':args.iou,
        'image_size_inference':args.imgsz,
        'class_mapping_status':'PROVISIONAL_NOT_AUTHOR_VERIFIED',
        'provisional_classes':CLASSES,
        'checkpoint_names':actual,
        'excluded_class_ids_in_coverage':sorted(exclude_ids),
        'coverage_mean_pct':round(mean(covs),4),
        'coverage_median_pct':round(median(covs),4),
        'demo_score_mean':round(mean(scores),4),
        'demo_score_median':round(median(scores),4),
        'demo_score_min':round(min(scores),4),
        'demo_score_max':round(max(scores),4),
        'formula':'demo_index_not_pci = 100 - union_area(predicted scoring boxes)/image_area * 100',
        'limitations':[
            'Not ground-truth PCI or validated pavement condition',
            'Box area is not crack area and is not physically calibrated',
            'Unverified class names; verify PaveTrack_OD source mapping',
            'Manhole excluded by assumed heuristic; may need review',
            'Detector errors propagate into this experimental index',
            'No severity or distress length/width in physical units',
        ],
        'created_utc':datetime.now(timezone.utc).isoformat()
    }
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    lines=[
        '# PaveTrack_OD — Experimental Scoring Report',
        '',
        '**Not PCI. Not calibrated against pavement-condition ground truth.**',
        '',
        f'- Images: {len(rows)}',
        f'- Predicted bounding boxes: {len(box_rows)}',
        f'- Confidence: {args.conf}; NMS IoU: {args.iou}; inference resolution: {args.imgsz}',
        f'- Mean inverse-box demo index: {mean(scores):.3f}/100',
        f'- Median inverse-box demo index: {median(scores):.3f}/100',
        f'- Mean box union coverage: {mean(covs):.3f}%',
        '',
        '## Interpretation',
        'Higher demo index means less predicted bounding-box coverage, **not a measured healthier pavement**.',
        'The index is not a PCI calculation; large crack rectangles can inflate coverage.',
        'Manhole is excluded from coverage by provisional rule, but counted in detections.',
        '',
        '## Files',
        '- `image_features_and_demo_scores.csv`: image-wise measurements and demo index.',
        '- `detections_per_box.csv`: class, confidence, pixel geometry for every predicted box.',
        '- `annotated/`: actual model predictions with DEMO INDEX / NOT PCI overlay.',
        '- `demo_score_histogram.png`: index distribution.',
        '- `top10_coverage.png`: suspect large box-coverage images.',
        '- `summary.json`: parameters and cautions.',
        '',
        '## Research next steps',
        'Verify class mapping and annotations; inspect false negatives and high coverage cases.',
        'Acquire independent PCI/condition labels or conduct a standards-based pavement survey.',
        'Train image + engineering-feature fusion against those labels using train/val/test separation.',
        'Report MAE/RMSE/R² on the untouched test set only after model selection.',
        '',
    ]
    (out/'README_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\nCOMPLETE: '+str(out.resolve()),flush=True)
    print(f'Images={len(rows)}, boxes={len(box_rows)}, mean demo index={mean(scores):.3f}',flush=True)
    print('WARNING: Demo index is NOT PCI.',flush=True)

if __name__=='__main__': main()
