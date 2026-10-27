import json
import hashlib
from time import perf_counter
import inference
from pathlib import Path

from PIL import Image

from inference import predict
from inspect_mask import summarize_mask

MODEL_VERSION = hashlib.sha256((Path(__file__).resolve().parent / "best_model.pt").read_bytes()).hexdigest()

def analyze_image(image_path):
    """Run prediction and return structured results."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")

    start = perf_counter()
    mask = predict(image)
    prediction_seconds = perf_counter() - start
    results = summarize_mask(mask)

    distresses = [
        result
        for result in results
        if result["class_id"] != 0
    ]

    return {
        "status": "completed",
        "model_name": "Attain SegFormer-B0",
        "model_version": MODEL_VERSION,
        "prediction_seconds": prediction_seconds,
        "device": str(inference.DEVICE),
        "image_width": image.width,
        "image_height": image.height,
        "distresses": distresses,
    }


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    response = analyze_image(folder / "road2.jpg")
    print(json.dumps(response, indent=2))