# Attain SegFormer - Pavement Distress Detection

## Overview
This package contains a trained SegFormer-B0 semantic segmentation
model for detecting pavement distress in road images.

The model predicts 8 classes (IDs 0-7).

## Files
- best_model.pt: Required trained checkpoint, supplied separately by the project team
- config.json: Model architecture configuration
- class_mapping.json: Distress class labels
- inference.py: Inference and prediction function
- requirements.txt: Python dependencies

## Installation
The supplied package recommended Python 3.11; the integrated application has been
tested with Python 3.12. See the [repository README](../README.md) for the complete
two-service setup.

Create a virtual environment and install dependencies:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-lock.txt

Use a compatible PyTorch and torchvision build for your operating system.

## Run Prediction
Place a pavement image in this folder, then run:

    python inference.py --image road.jpg --output prediction_mask.png

## Direct Python Inference

    from inference import predict
    from PIL import Image

    image = Image.open("road.jpg")
    mask = predict(image)

The returned mask is a NumPy array with integer class IDs.

## Class Mapping
0: Background
1: Alligator crack - Low
2: Block crack - Low
3: Faded marking - High
4: Faded marking - Low
5: Linear crack - High
6: Linear crack - Low
7: Pothole - Low

## Notes
- The model uses 640 x 640 preprocessing.
- Output masks are resized to the original image dimensions.
- Configuration is included in the source release. Model weights must be obtained separately and placed beside inference.py.
- No Delta server connection is required for inference.
- This package does not include pavement condition scoring logic.
