"""Measure startup and repeated predictions separately, without saving files."""
import argparse
from pathlib import Path
from statistics import median
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be at least 1')
    if not Path(args.image).is_file():
        parser.error(f'Image not found: {args.image}')

    # Importing inference builds the model and loads the weights once.
    start = perf_counter()
    import inference
    startup = perf_counter() - start
    from PIL import Image
    import numpy as np

    def synchronize():
        # CUDA execution is asynchronous, so wait for it before stopping timers.
        if inference.DEVICE.type == 'cuda':
            inference.torch.cuda.synchronize()

    start = perf_counter()
    with Image.open(args.image) as source:
        image = source.convert('RGB')
    decode = perf_counter() - start

    def timed_prediction():
        synchronize()
        start = perf_counter()
        mask = inference.predict(image)
        synchronize()
        return mask, perf_counter() - start

    mask, first = timed_prediction()
    times = []
    for _ in range(args.runs):
        mask, seconds = timed_prediction()
        times.append(seconds)

    print(f'Device: {inference.DEVICE}')
    print(f'Original: {image.width} x {image.height}; model input: {inference.IMAGE_SIZE} x {inference.IMAGE_SIZE}')
    print(f'Mask: {mask.shape[1]} x {mask.shape[0]}')
    print(f'Dependency import + model initialization/loading: {startup:.3f} s')
    print(f'Image decoding: {decode:.3f} s')
    print(f'First prediction: {first:.3f} s')
    print('Repeat predictions:', ', '.join(f'{s:.3f} s' for s in times))
    print(f'Repeat median: {median(times):.3f} s; range: {min(times):.3f}-{max(times):.3f} s')
    print('Classes:', ', '.join(f'{int(i)}: {inference.id2label[int(i)]}' for i in np.unique(mask)))
    print('Prediction includes preprocessing, model execution, and original-size mask creation.')
    print('Excludes network, storage, overlays, and saving. No output files changed.')


if __name__ == '__main__':
    main()
