from pathlib import Path
import json

import httpx

def request_analysis_bytes(image_bytes, filename="image"):
    """Send image bytes to the model API."""
    response = httpx.post(
        "http://127.0.0.1:8020/analyze",
        files={
            "file": (
                filename,
                image_bytes,
                "application/octet-stream",
            )
        },
        timeout=120.0,
    )

    response.raise_for_status()
    return response.json()


def request_analysis(image_path):
    """Read a local image and reuse the bytes-based function."""
    image_path = Path(image_path)

    return request_analysis_bytes(
        image_path.read_bytes(),
        image_path.name,
    )


if __name__ == "__main__":
    image_path = (
        Path(__file__).resolve().parent.parent
        / "Attain_SegFormer_Portable"
        / "road2.jpg"
    )

    result = request_analysis(image_path)
    print(json.dumps(result, indent=2))