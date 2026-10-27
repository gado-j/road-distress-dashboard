import json

import storage_backend as storage
from test_model_connection import request_analysis_bytes

# Show the ten most recent saved images.
rows = (
    storage.client()
    .table("media")
    .select("id, original_filename")
    .eq("upload_status", "ready")
    .order("created_at", desc=True)
    .limit(10)
    .execute()
    .data
)

if not rows:
    raise SystemExit("No saved images found. Upload one in the dashboard first.")

for number, row in enumerate(rows, start=1):
    print(f"{number}. {row['original_filename']}")

choice = input("Enter an image number: ")

if not choice.isdigit() or not 1 <= int(choice) <= len(rows):
    raise SystemExit("Invalid selection.")

# Find the selected image's storage location.
selected = rows[int(choice) - 1]
record = storage.media_record(selected["id"])

# Download its original bytes from private storage.
image_bytes = (
    storage.client()
    .storage.from_(record["bucket_id"])
    .download(record["object_path"])
)

# Send those bytes to the model API.
result = request_analysis_bytes(
    image_bytes,
    record["original_filename"],
)

print(json.dumps(result, indent=2))