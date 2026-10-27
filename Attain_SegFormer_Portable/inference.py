from pathlib import Path
import json
import argparse

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import (
    SegformerConfig,
    SegformerForSemanticSegmentation,
    SegformerImageProcessor,
)

BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT = BASE_DIR / "best_model.pt"
MAPPING_FILE = BASE_DIR / "class_mapping.json"

IMAGE_SIZE = 640

with open(MAPPING_FILE, "r") as f:
    mapping = json.load(f)

id2label = {int(k): v for k, v in mapping.items()}
label2id = {v: k for k, v in id2label.items()}

DEVICE = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

processor = SegformerImageProcessor(
    do_resize=True,
    size={"height": IMAGE_SIZE, "width": IMAGE_SIZE},
    do_reduce_labels=False,
    do_rescale=True,
    do_normalize=True,
)

config = SegformerConfig.from_pretrained(
    str(BASE_DIR),
    num_labels=len(id2label),
    id2label=id2label,
    label2id=label2id,
    local_files_only=True
)

model = SegformerForSemanticSegmentation(config)

# Only load checkpoints from a trusted source.
checkpoint = torch.load(
    CHECKPOINT,
    map_location="cpu",
    weights_only=True,
)

if "model_state_dict" in checkpoint:
    state_dict = checkpoint["model_state_dict"]
elif "state_dict" in checkpoint:
    state_dict = checkpoint["state_dict"]
else:
    state_dict = checkpoint

state_dict = {
    k.removeprefix("module."): v
    for k, v in state_dict.items()
}

model.load_state_dict(state_dict, strict=True)
model.to(DEVICE)
model.eval()


def predict(image):
    """Return an 8-class segmentation mask as a NumPy array."""

    if not isinstance(image, Image.Image):
        image = Image.open(image)

    image = image.convert("RGB")
    original_size = (image.height, image.width)

    inputs = processor(
        images=image,
        return_tensors="pt"
    ).to(DEVICE)

    with torch.no_grad():
        outputs = model(**inputs)

    logits = F.interpolate(
        outputs.logits,
        size=original_size,
        mode="bilinear",
        align_corners=False,
    )

    mask = logits.argmax(dim=1)[0]
    return mask.cpu().numpy().astype(np.uint8)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", default="prediction_mask.png")
    args = parser.parse_args()

    mask = predict(args.image)
    Image.fromarray(mask).save(args.output)

    print("Prediction saved:", args.output)
    print("Classes present:", np.unique(mask).tolist())
