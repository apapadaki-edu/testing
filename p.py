# #!/usr/bin/env python3
“””
JP2 Book Page Auto Border Detection Cropper

Automatically detects and crops the dark scanner border from JP2 book page scans.

Supports:

- JPEG 2000 (.jp2, .jpx, .j2k) via Pillow + OpenJPEG
- Grayscale, RGB, RGBA images
- Multiple detection strategies (threshold, gradient, contour, histogram)
- Batch processing of entire directories
- Preview mode (saves annotated debug images)
- Configurable padding, min/max crop ratios, output format

Usage:
python jp2_book_cropper.py input.jp2                      # single file
python jp2_book_cropper.py input.jp2 -o output.jp2        # specify output
python jp2_book_cropper.py ./scans/ -o ./cropped/         # batch directory
python jp2_book_cropper.py input.jp2 –preview            # save debug preview
python jp2_book_cropper.py input.jp2 –method contour     # choose algorithm
python jp2_book_cropper.py input.jp2 –padding 20         # extra padding (px)
“””

import argparse
import sys
import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

import numpy as np
import cv2
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────

# Data structures

# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CropBox:
x1: int
y1: int
x2: int
y2: int

```
@property
def width(self) -> int:
    return self.x2 - self.x1

@property
def height(self) -> int:
    return self.y2 - self.y1

@property
def area(self) -> int:
    return self.width * self.height

def pad(self, px: int, img_w: int, img_h: int) -> "CropBox":
    return CropBox(
        max(0, self.x1 - px),
        max(0, self.y1 - px),
        min(img_w, self.x2 + px),
        min(img_h, self.y2 + px),
    )

def __str__(self):
    return f"CropBox(x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2}, {self.width}×{self.height})"
```

@dataclass
class CropResult:
success: bool
crop_box: Optional[CropBox]
method_used: str
message: str = “”
crop_ratio: float = 1.0       # fraction of original area kept

# ──────────────────────────────────────────────────────────────────────────────

# JP2 I/O

# ──────────────────────────────────────────────────────────────────────────────

JP2_EXTENSIONS = {”.jp2”, “.jpx”, “.j2k”, “.j2c”, “.jpc”, “.jpf”}

def load_jp2(path: Path) -> np.ndarray:
“”“Load a JP2/JPEG2000 image as a NumPy array (BGR for colour, or gray).”””
try:
pil_img = Image.open(path)
# Normalise mode
if pil_img.mode in (“1”, “P”):
pil_img = pil_img.convert(“L”)
elif pil_img.mode == “RGBA”:
pil_img = pil_img.convert(“RGB”)
elif pil_img.mode not in (“RGB”, “L”):
pil_img = pil_img.convert(“RGB”)

```
    arr = np.array(pil_img)

    # Convert RGB → BGR for OpenCV
    if arr.ndim == 3 and arr.shape[2] == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    return arr

except Exception as exc:
    raise IOError(f"Cannot read '{path}': {exc}") from exc
```

def save_jp2(arr: np.ndarray, path: Path, lossless: bool = True) -> None:
“”“Save a NumPy array to a JP2 file via Pillow.”””
# Convert BGR → RGB for Pillow
if arr.ndim == 3 and arr.shape[2] == 3:
arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
pil_img = Image.fromarray(arr)

```
# Pillow JP2 kwargs
save_kwargs: dict = {}
if lossless:
    save_kwargs["irreversible"] = False   # use reversible (lossless) DWT
else:
    save_kwargs["irreversible"] = True
    save_kwargs["quality_mode"] = "dB"
    save_kwargs["quality_layers"] = [45]

try:
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_img.save(str(path), **save_kwargs)
except Exception as exc:
    raise IOError(f"Cannot save '{path}': {exc}") from exc
```

def save_image(arr: np.ndarray, path: Path) -> None:
“”“Save array to any format (dispatches to save_jp2 or cv2).”””
ext = path.suffix.lower()
if ext in JP2_EXTENSIONS:
save_jp2(arr, path)
else:
path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(path), arr)

# ──────────────────────────────────────────────────────────────────────────────

# Preprocessing helpers

# ──────────────────────────────────────────────────────────────────────────────

def to_gray(img: np.ndarray) -> np.ndarray:
if img.ndim == 2:
return img
return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def downsample(img: np.ndarray, max_dim: int = 1500) -> Tuple[np.ndarray, float]:
“”“Downsample large images for faster processing. Returns (resized, scale).”””
h, w = img.shape[:2]
scale = min(max_dim / max(h, w), 1.0)
if scale < 1.0:
new_w, new_h = int(w * scale), int(h * scale)
resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
return resized, scale
return img, 1.0

def scale_box(box: CropBox, scale: float, img_w: int, img_h: int) -> CropBox:
return CropBox(
int(box.x1 / scale),
int(box.y1 / scale),
min(img_w, int(box.x2 / scale)),
min(img_h, int(box.y2 / scale)),
)

# ──────────────────────────────────────────────────────────────────────────────

# Detection strategies

# ──────────────────────────────────────────────────────────────────────────────

def detect_threshold(gray: np.ndarray, dark_threshold: int = 128) -> Optional[CropBox]:
“””
Strategy 1 – THRESHOLD
Otsu-binarise or use fixed threshold; find bounding box of bright pixels
(the page). Robust for high-contrast scanner borders.
“””
# Adaptive: try Otsu first, fall back to fixed
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
# If Otsu threshold is too high (very dark image), use fixed
otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0]
if otsu_thresh > 200:
_, binary = cv2.threshold(gray, dark_threshold, 255, cv2.THRESH_BINARY)

```
# Morphological clean-up
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

coords = cv2.findNonZero(binary)
if coords is None:
    return None

x, y, w, h = cv2.boundingRect(coords)
return CropBox(x, y, x + w, y + h)
```

def detect_gradient(gray: np.ndarray) -> Optional[CropBox]:
“””
Strategy 2 – GRADIENT / EDGE
Use Sobel edges to find the strong boundary between dark border and bright
page. Good when page and border have similar mid-gray tones.
“””
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
grad_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
grad_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)
magnitude = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

```
_, edge_mask = cv2.threshold(magnitude, 30, 255, cv2.THRESH_BINARY)
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
edge_mask = cv2.morphologyEx(edge_mask, cv2.MORPH_CLOSE, kernel)

coords = cv2.findNonZero(edge_mask)
if coords is None:
    return None

x, y, w, h = cv2.boundingRect(coords)
# Inset slightly (the strong edge is at the boundary, page is inside)
inset = 5
h_img, w_img = gray.shape
return CropBox(
    min(x + inset, w_img),
    min(y + inset, h_img),
    max(x + w - inset, 0),
    max(y + h - inset, 0),
)
```

def detect_contour(gray: np.ndarray) -> Optional[CropBox]:
“””
Strategy 3 – CONTOUR
Find the largest bright contour (the page rectangle). Handles slightly
rotated or trapezoidal pages gracefully.
“””
blurred = cv2.GaussianBlur(gray, (7, 7), 0)
_, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

```
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
if not contours:
    return None

# Pick the largest contour
largest = max(contours, key=cv2.contourArea)
x, y, w, h = cv2.boundingRect(largest)
return CropBox(x, y, x + w, y + h)
```

def detect_histogram(gray: np.ndarray, dark_band: int = 80) -> Optional[CropBox]:
“””
Strategy 4 – ROW/COLUMN HISTOGRAM
Project row and column mean intensities. The page shows up as a plateau
of high values; dark scanner borders as a drop. Find the transition points.
Robust even when the border is very thin or gradual.
“””
h, w = gray.shape
smooth_k = max(3, min(51, (h // 40) | 1))  # odd kernel sized to image

```
row_means = np.mean(gray, axis=1).astype(float)
col_means = np.mean(gray, axis=0).astype(float)

# Smooth to remove noise from text lines
row_means = np.convolve(row_means, np.ones(smooth_k) / smooth_k, mode="same")
col_means = np.convolve(col_means, np.ones(smooth_k) / smooth_k, mode="same")

def find_band(signal: np.ndarray, threshold: float) -> Tuple[int, int]:
    bright = signal > threshold
    if not bright.any():
        return 0, len(signal)
    start = int(np.argmax(bright))
    end = int(len(bright) - np.argmax(bright[::-1]) - 1)
    return start, end

threshold = dark_band
y1, y2 = find_band(row_means, threshold)
x1, x2 = find_band(col_means, threshold)

if x2 <= x1 or y2 <= y1:
    return None
return CropBox(x1, y1, x2, y2)
```

# ──────────────────────────────────────────────────────────────────────────────

# Ensemble / fallback logic

# ──────────────────────────────────────────────────────────────────────────────

METHODS = {
“threshold”: detect_threshold,
“gradient”:  detect_gradient,
“contour”:   detect_contour,
“histogram”: detect_histogram,
}

def validate_box(box: CropBox, img_w: int, img_h: int,
min_ratio: float = 0.10, max_ratio: float = 0.98) -> bool:
“”“Return True if box looks like a sensible crop (not too small, not entire image).”””
if box.x2 <= box.x1 or box.y2 <= box.y1:
return False
area_ratio = box.area / (img_w * img_h)
return min_ratio <= area_ratio <= max_ratio

def ensemble_crop(gray: np.ndarray, img_w: int, img_h: int,
preferred_method: str = “auto”,
min_ratio: float = 0.10,
max_ratio: float = 0.98) -> CropResult:
“””
Run detection strategies, validate results, and pick the best one.
If preferred_method is ‘auto’, tries all in order of reliability.
“””
order = [“contour”, “threshold”, “histogram”, “gradient”]
if preferred_method != “auto” and preferred_method in METHODS:
order = [preferred_method] + [m for m in order if m != preferred_method]

```
for method_name in order:
    try:
        fn = METHODS[method_name]
        box = fn(gray)
        if box and validate_box(box, img_w, img_h, min_ratio, max_ratio):
            ratio = box.area / (img_w * img_h)
            return CropResult(
                success=True,
                crop_box=box,
                method_used=method_name,
                crop_ratio=ratio,
                message=f"Detected with '{method_name}' method ({ratio*100:.1f}% of original)",
            )
    except Exception as exc:
        # This method failed – try the next
        continue

return CropResult(
    success=False,
    crop_box=None,
    method_used="none",
    message="All detection methods failed; returning original bounds.",
)
```

# ──────────────────────────────────────────────────────────────────────────────

# Preview / debug

# ──────────────────────────────────────────────────────────────────────────────

def save_preview(img: np.ndarray, result: CropResult, path: Path) -> None:
“”“Save annotated image showing the detected crop box.”””
preview = img.copy()
if preview.ndim == 2:
preview = cv2.cvtColor(preview, cv2.COLOR_GRAY2BGR)

```
if result.crop_box:
    b = result.crop_box
    cv2.rectangle(preview, (b.x1, b.y1), (b.x2, b.y2), (0, 255, 0), 4)
    label = f"Method: {result.method_used}  {b.width}x{b.height}"
    cv2.putText(preview, label, (b.x1, max(b.y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

# Downsample preview if huge
h, w = preview.shape[:2]
if max(h, w) > 2000:
    scale = 2000 / max(h, w)
    preview = cv2.resize(preview, (int(w * scale), int(h * scale)))

path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(path), preview)
```

# ──────────────────────────────────────────────────────────────────────────────

# Core crop function

# ──────────────────────────────────────────────────────────────────────────────

def crop_jp2(
input_path: Path,
output_path: Optional[Path] = None,
method: str = “auto”,
padding: int = 10,
min_ratio: float = 0.10,
max_ratio: float = 0.98,
preview: bool = False,
preview_dir: Optional[Path] = None,
lossless: bool = True,
verbose: bool = True,
) -> CropResult:
“””
Detect and crop border from a single JP2 file.

```
Parameters
----------
input_path  : Path to input JP2 file
output_path : Destination path (same format as input if None specified)
method      : 'auto' | 'threshold' | 'gradient' | 'contour' | 'histogram'
padding     : Extra pixels to keep around detected page (avoids clipping)
min_ratio   : Minimum crop area as fraction of original (rejects tiny crops)
max_ratio   : Maximum crop area as fraction of original (rejects no-ops)
preview     : Save annotated debug image
preview_dir : Directory for preview images (defaults to output dir)
lossless    : Use lossless JP2 compression when saving
verbose     : Print status messages

Returns
-------
CropResult
"""
t0 = time.perf_counter()

# ── Load ──────────────────────────────────────────────────────────────────
img = load_jp2(input_path)
img_h, img_w = img.shape[:2]

if verbose:
    print(f"  Loaded  : {input_path.name}  ({img_w}×{img_h})")

# ── Downsample for detection only ─────────────────────────────────────────
small, scale = downsample(img)
gray_small = to_gray(small)

# ── Detect ────────────────────────────────────────────────────────────────
result = ensemble_crop(gray_small, small.shape[1], small.shape[0],
                       preferred_method=method,
                       min_ratio=min_ratio, max_ratio=max_ratio)

# ── Scale box back to full resolution ────────────────────────────────────
if result.success and result.crop_box and scale < 1.0:
    result.crop_box = scale_box(result.crop_box, scale, img_w, img_h)

# ── Fallback: use full image ───────────────────────────────────────────────
if not result.success or result.crop_box is None:
    if verbose:
        print(f"  Warning : {result.message} Using full image.")
    result.crop_box = CropBox(0, 0, img_w, img_h)
    result.crop_ratio = 1.0

# ── Apply padding ─────────────────────────────────────────────────────────
box = result.crop_box.pad(padding, img_w, img_h)
result.crop_box = box

# ── Crop ──────────────────────────────────────────────────────────────────
cropped = img[box.y1:box.y2, box.x1:box.x2]

# ── Save ──────────────────────────────────────────────────────────────────
if output_path is None:
    output_path = input_path.parent / (input_path.stem + "_cropped" + input_path.suffix)

save_image(cropped, output_path)

elapsed = time.perf_counter() - t0
if verbose:
    print(f"  Result  : {result.message}")
    print(f"  Crop box: {result.crop_box}")
    print(f"  Saved   : {output_path}  ({elapsed:.2f}s)")

# ── Preview ───────────────────────────────────────────────────────────────
if preview:
    pdir = preview_dir or output_path.parent
    ppath = pdir / (input_path.stem + "_preview.jpg")
    save_preview(img, result, ppath)
    if verbose:
        print(f"  Preview : {ppath}")

return result
```

# ──────────────────────────────────────────────────────────────────────────────

# Batch processing

# ──────────────────────────────────────────────────────────────────────────────

def batch_crop(
input_dir: Path,
output_dir: Path,
method: str = “auto”,
padding: int = 10,
min_ratio: float = 0.10,
max_ratio: float = 0.98,
preview: bool = False,
lossless: bool = True,
verbose: bool = True,
) -> List[CropResult]:
“”“Crop all JP2 files in input_dir and save to output_dir.”””
jp2_files = sorted([p for p in input_dir.iterdir()
if p.suffix.lower() in JP2_EXTENSIONS])

```
if not jp2_files:
    print(f"No JP2 files found in '{input_dir}'.")
    return []

print(f"Found {len(jp2_files)} JP2 file(s) in '{input_dir}'")
output_dir.mkdir(parents=True, exist_ok=True)

results = []
for i, jp2_path in enumerate(jp2_files, 1):
    print(f"\n[{i}/{len(jp2_files)}] {jp2_path.name}")
    out_path = output_dir / jp2_path.name
    try:
        r = crop_jp2(
            jp2_path, out_path,
            method=method, padding=padding,
            min_ratio=min_ratio, max_ratio=max_ratio,
            preview=preview, preview_dir=output_dir / "previews",
            lossless=lossless, verbose=verbose,
        )
    except Exception as exc:
        print(f"  ERROR: {exc}")
        r = CropResult(success=False, crop_box=None,
                       method_used="none", message=str(exc))
    results.append(r)

success = sum(1 for r in results if r.success)
print(f"\n✓ Processed {len(results)} files — {success} successful, "
      f"{len(results) - success} failed.")
return results
```

# ──────────────────────────────────────────────────────────────────────────────

# CLI

# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
p = argparse.ArgumentParser(
description=“Auto border-detection cropper for JP2 book page scans.”,
formatter_class=argparse.RawDescriptionHelpFormatter,
epilog=**doc**,
)
p.add_argument(“input”, help=“JP2 file or directory containing JP2 files”)
p.add_argument(”-o”, “–output”, default=None,
help=“Output file (single) or directory (batch)”)
p.add_argument(”-m”, “–method”,
choices=[“auto”, “threshold”, “gradient”, “contour”, “histogram”],
default=“auto”,
help=“Border detection algorithm (default: auto)”)
p.add_argument(”-p”, “–padding”, type=int, default=10,
help=“Extra pixels kept around detected page (default: 10)”)
p.add_argument(”–min-ratio”, type=float, default=0.10,
help=“Min crop area fraction (default: 0.10)”)
p.add_argument(”–max-ratio”, type=float, default=0.98,
help=“Max crop area fraction (default: 0.98)”)
p.add_argument(”–preview”, action=“store_true”,
help=“Save annotated debug preview image (JPEG)”)
p.add_argument(”–lossy”, action=“store_true”,
help=“Use lossy JP2 compression (default: lossless)”)
p.add_argument(”-q”, “–quiet”, action=“store_true”,
help=“Suppress verbose output”)
return p

def main(argv: Optional[List[str]] = None) -> int:
parser = build_parser()
args = parser.parse_args(argv)

```
input_path = Path(args.input)
lossless = not args.lossy
verbose = not args.quiet

if input_path.is_dir():
    # ── Batch mode ────────────────────────────────────────────────────────
    out_dir = Path(args.output) if args.output else input_path / "cropped"
    results = batch_crop(
        input_path, out_dir,
        method=args.method,
        padding=args.padding,
        min_ratio=args.min_ratio,
        max_ratio=args.max_ratio,
        preview=args.preview,
        lossless=lossless,
        verbose=verbose,
    )
    return 0 if all(r.success for r in results) else 1

elif input_path.is_file():
    # ── Single file mode ──────────────────────────────────────────────────
    if input_path.suffix.lower() not in JP2_EXTENSIONS:
        # Allow non-JP2 input for testing (e.g. PNG)
        pass
    out_path = Path(args.output) if args.output else None
    result = crop_jp2(
        input_path, out_path,
        method=args.method,
        padding=args.padding,
        min_ratio=args.min_ratio,
        max_ratio=args.max_ratio,
        preview=args.preview,
        lossless=lossless,
        verbose=verbose,
    )
    return 0 if result.success else 1

else:
    print(f"Error: '{input_path}' is not a valid file or directory.", file=sys.stderr)
    return 2
```

if **name** == “**main**”:
sys.exit(main())