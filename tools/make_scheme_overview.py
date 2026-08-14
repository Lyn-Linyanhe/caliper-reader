"""Create a contact sheet from an exported scheme diagnostics directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np


def main(directory: str) -> None:
    output_dir = Path(directory)
    rows = json.loads((output_dir / "diagnostics.json").read_text(encoding="utf-8"))
    panels = []
    for index, row in enumerate(rows, start=1):
        image_path = output_dir / f"{index:02d}_{Path(row['image']).stem}_reading.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise RuntimeError(f"Unable to read {image_path}")
        panel_w, image_h, header_h = 720, 330, 52
        h, w = image.shape[:2]
        scale = min(panel_w / w, image_h / h)
        resized = cv2.resize(
            image, (max(1, round(w * scale)), max(1, round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        panel = np.full((image_h + header_h, panel_w, 3), 245, dtype=np.uint8)
        x = (panel_w - resized.shape[1]) // 2
        y = header_h + (image_h - resized.shape[0]) // 2
        panel[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
        truth = 140.80 if row["image"] == "14.80.jpg" else float(Path(row["image"]).stem)
        color = (0, 120, 0) if abs(row["reading_mm"] - truth) <= 0.10 else (0, 0, 210)
        cv2.putText(
            panel,
            f"{row['image']}  truth={truth:.2f}  result={row['reading_mm']:.2f}",
            (12, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA,
        )
        panels.append(panel)

    if len(panels) % 2:
        panels.append(np.full_like(panels[0], 245))
    contact = np.vstack([
        np.hstack((panels[index], panels[index + 1]))
        for index in range(0, len(panels), 2)
    ])
    ok, encoded = cv2.imencode(".png", contact)
    if not ok:
        raise RuntimeError("Unable to encode overview")
    encoded.tofile(str(output_dir / "overview_readings.png"))


if __name__ == "__main__":
    main(sys.argv[1])
