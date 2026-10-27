import json
from pathlib import Path

import numpy as np
from PIL import Image

# Read the model's class names.
folder = Path(__file__).resolve().parent
mapping = json.loads((folder / "class_mapping.json").read_text())

def summarize_mask(mask):
    """Return the classes present and their pixel coverage."""
    class_ids, pixel_counts = np.unique(mask, return_counts=True)

    results = []

    for class_id, count in zip(class_ids, pixel_counts):
        results.append({
            "class_id": int(class_id),
            "label": mapping[str(class_id)],
            "pixel_count": int(count),
            "pixel_fraction": float(count / mask.size),
        })

    return results


# Run this section only when this file is executed directly.
if __name__ == "__main__":
    with Image.open(folder / "road2_mask.png") as image:
        mask = np.array(image)

    results = summarize_mask(mask)
    print(json.dumps(results, indent=2))