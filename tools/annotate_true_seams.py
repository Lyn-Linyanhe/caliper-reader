"""Click the physical main/vernier seam on oriented ROI images."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caliper.config import config
from caliper.preprocess import preprocess
from caliper.roi_extract import locate_roi_lowres, orient_caliper


INPUT_DIR = ROOT / "tupian"
OUTPUT_PATH = ROOT / "debug_tupian_projection_samples" / "seam_annotations.json"
SAMPLES = [
    "11.00.jpg", "20.00.jpg", "60.50.jpg", "70.92.jpg",
    "80.70.jpg", "90.28.jpg", "100.74.jpg", "120.60.jpg", "140.00.jpg",
]


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Unable to read {path}")
    return image


def orient_image(path: Path) -> np.ndarray:
    image = read_image(path)
    roi = locate_roi_lowres(image)
    if roi.get("roi_color") is None:
        raise RuntimeError("ROI localization failed")
    params = {
        "clip_limit": config.preprocess.clahe_clip_limit,
        "bilateral_d": config.preprocess.bilateral_d,
        "bilateral_sigma": config.preprocess.bilateral_sigma,
        "gamma": config.preprocess.gamma,
        "median_ksize": config.preprocess.median_ksize,
    }
    processed = preprocess(roi["roi_color"], make_debug=False, **params)
    return orient_caliper(
        processed["color"], processed["enhanced"], processed["binary_adaptive"],
        make_debug=False,
    )["rotated_color"]


def load_annotations() -> dict:
    if not OUTPUT_PATH.exists():
        return {}
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


def save_annotations(annotations: dict) -> None:
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(annotations, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    annotations = load_annotations()
    index = 0
    selected_y = None
    current = None
    scale = 1.0
    window_name = "Click physical seam | Space: confirm | S: skip | R: clear | Q: save and quit"

    def redraw() -> None:
        display = current.copy()
        if selected_y is not None:
            cv2.line(display, (0, selected_y), (display.shape[1] - 1, selected_y),
                     (0, 0, 255), 2, cv2.LINE_AA)
        if scale != 1.0:
            display = cv2.resize(display, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imshow(window_name, display)

    def on_mouse(event, x, y, flags, param) -> None:
        nonlocal selected_y
        if event == cv2.EVENT_LBUTTONDOWN:
            selected_y = max(0, min(current.shape[0] - 1, int(round(y / scale))))
            annotations[SAMPLES[index]] = {
                "split_y": int(selected_y),
                "image_height": int(current.shape[0]),
            }
            save_annotations(annotations)
            print(f"{SAMPLES[index]}: y={selected_y}")
            redraw()

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)
    print("Click the physical seam. Space confirms; S skips; R clears; Q saves and exits.")

    while 0 <= index < len(SAMPLES):
        filename = SAMPLES[index]
        current = orient_image(INPUT_DIR / filename)
        selected_y = annotations.get(filename, {}).get("split_y")
        h, w = current.shape[:2]
        scale = min(1.0, 1500.0 / w, 900.0 / h)
        cv2.setWindowTitle(window_name, f"{filename} | click physical seam | {index + 1}/{len(SAMPLES)}")
        redraw()

        while True:
            key = cv2.waitKey(0) & 0xFF
            if key in (ord("q"), 27):
                save_annotations(annotations)
                cv2.destroyAllWindows()
                return
            if key in (ord("r"), ord("c")):
                selected_y = None
                redraw()
                continue
            if key in (32, 13):
                if selected_y is not None:
                    annotations[filename] = {
                        "split_y": int(selected_y),
                        "image_height": int(h),
                    }
                    save_annotations(annotations)
                    print(f"{filename}: y={selected_y}")
                    index += 1
                    break
                continue
            if key == ord("s"):
                annotations.pop(filename, None)
                print(f"{filename}: skipped")
                index += 1
                break
            if key == ord("a") and index > 0:
                index -= 1
                break

    save_annotations(annotations)
    cv2.destroyAllWindows()
    print(f"Saved {len(annotations)} annotations to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
