import io
import warnings

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from test_prediction import analyze_image

app = FastAPI()

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_PIXELS = 4_000_000        # Limits memory used during prediction


@app.post("/analyze")
def analyze(file: UploadFile = File(...)):
    try:
        # Read only enough to detect an oversized upload.
        content = file.file.read(MAX_BYTES + 1)

        if len(content) > MAX_BYTES:
            raise HTTPException(413, "Image must be 20 MB or smaller.")

        # Inspect the actual image, not just its filename.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)

                with Image.open(io.BytesIO(content)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"}:
                        raise HTTPException(
                            415, "Choose a JPEG, PNG, or WebP image."
                        )

                    if image.width * image.height > MAX_PIXELS:
                        raise HTTPException(
                            413, "Image must contain at most 4 million pixels."
                        )

                    image.verify()

        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise HTTPException(422, "The file is not a valid supported image.")

        # Your function accepts a file-like object through Image.open().
        return analyze_image(io.BytesIO(content))

    finally:
        file.file.close()