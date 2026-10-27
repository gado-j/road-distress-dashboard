"""Color a saved class-ID mask over its original image, without rerunning the model."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

# Categorical colors identify model classes, not overall road risk.
COLORS = [(0, 0, 0), (0, 170, 160), (110, 170, 90), (240, 160, 40),
          (90, 140, 210), (230, 70, 160), (150, 100, 220), (225, 105, 55)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--mask', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    legend_path = output.with_name(output.stem + '_legend.png')
    if output.exists() or legend_path.exists():
        parser.error('Output already exists. Choose a new --output filename.')
    if output.suffix.lower() != '.png':
        parser.error('--output must end in .png')
    with Image.open(args.image) as image:
        original = np.array(image.convert('RGB'))
    with Image.open(args.mask) as image:
        mask = np.array(image)
    if mask.ndim != 2 or mask.shape != original.shape[:2]:
        parser.error('Use a single-channel class-ID mask matching the original dimensions.')
    ids = np.unique(mask)
    if not np.isin(ids, np.arange(len(COLORS))).all():
        parser.error('Mask contains class IDs outside 0-7.')
    mapping = json.loads((Path(__file__).parent / 'class_mapping.json').read_text())
    overlay = original.copy()
    foreground = mask != 0
    colors = np.array(COLORS, dtype=np.uint8)[mask]
    # Leave background pixels intact; blend only the predicted distress pixels.
    overlay[foreground] = np.round(original[foreground] * 0.45 + colors[foreground] * 0.55).astype(np.uint8)
    Image.fromarray(overlay).save(output)
    legend = Image.new('RGB', (600, 70 + len(ids) * 30), 'white')
    draw = ImageDraw.Draw(legend)
    draw.text((15, 12), 'Model predictions: colors identify classes, not road risk', fill='black')
    for row, class_id in enumerate(ids):
        class_id = int(class_id)
        count = int((mask == class_id).sum())
        label = mapping[str(class_id)]
        percent = count / mask.size * 100
        y = 45 + row * 30
        draw.rectangle((15, y, 32, y + 17), fill=COLORS[class_id])
        draw.text((44, y + 2), f'{class_id}: {label} ({percent:.2f}% of image pixels)', fill='black')
        print(f'{class_id}: {label} - {count} pixels ({percent:.2f}%)')
    legend.save(legend_path)
    print('Overlay saved:', output)
    print('Legend saved:', legend_path)


if __name__ == '__main__':
    main()
