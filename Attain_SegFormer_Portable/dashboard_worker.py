"""Private JSON-lines worker used by the local dashboard; no web listener."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

start = perf_counter()
with contextlib.redirect_stdout(sys.stderr):
    import inference
import numpy as np
from PIL import Image
from visualize_mask import COLORS
startup = perf_counter() - start
version = hashlib.sha256(inference.CHECKPOINT.read_bytes()).hexdigest()
for line in sys.stdin:
    try:
        request = json.loads(line)
        with Image.open(request['image']) as source:
            image = source.convert('RGB')
        # Cap original-size logits memory in the existing inference implementation.
        if image.width * image.height > 4_000_000:
            raise ValueError('Use an image with at most 4 million pixels for this local model integration.')
        start = perf_counter()
        mask = inference.predict(image)
        seconds = perf_counter() - start
        folder = Path(request['output'])
        Image.fromarray(mask).save(folder / 'mask.png')
        original = np.array(image)
        foreground = mask != 0
        colors = np.array(COLORS, dtype=np.uint8)[mask]
        overlay = original.copy()
        overlay[foreground] = np.round(original[foreground] * .45 + colors[foreground] * .55).astype(np.uint8)
        Image.fromarray(overlay).save(folder / 'overlay.png')
        classes = []
        for value, count in zip(*np.unique(mask, return_counts=True)):
            classes.append({'class_id': int(value), 'label': inference.id2label[int(value)],
                            'pixel_count': int(count), 'pixel_fraction': float(count / mask.size)})
        result = {'model_name': 'Attain SegFormer-B0', 'model_version': version,
                  'device': str(inference.DEVICE), 'startup_seconds': startup,
                  'prediction_seconds': seconds, 'width': image.width, 'height': image.height,
                  'classes': classes, 'input_size': [640, 640]}
        print(json.dumps({'result': result}), flush=True)
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), flush=True)
