# Small sample inputs

No third-party research dataset photographs are distributed in this repository.
Use your own road photographs or samples whose redistribution has been approved.

For a tiny synthetic upload to check the pipeline, run this from the model folder
with its environment activated:

```bash
python -c 'from PIL import Image; Image.new("RGB", (640, 640), (110, 110, 110)).save("../samples/synthetic-road.png")'
```

This is a plain gray image, not a realistic road benchmark. It can test upload and
inference execution, but cannot be used to assess accuracy. Results depend on the
supplied trained weights. Synthetic input generation does not download a dataset.
