"""OCR engine selection and single-digit patch recognition.

The production pipeline selects digit connected components in
``main_scale.find_digit_cc_candidates`` and passes each selected patch here.
The former full-scale scan entry points were removed after the call-graph audit:
they had no repository callers and were unrelated to vernier standardization.
"""

import warnings

import cv2
import numpy as np

from .config import config
from .result import DigitInfo
from .template_ocr import TemplateDigitRecognizer


_HAS_TESSERACT = False
try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    pass

_HAS_EASYOCR = False
try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    pass


class DigitReader:
    """Recognize one already-selected main-scale digit patch."""

    def __init__(self):
        self._easyocr = None
        self._template_ocr = TemplateDigitRecognizer()
        self._engine = None
        self._engine_status = ""

    def engine_name(self) -> str:
        self._ensure_engine()
        return self._engine

    def engine_status(self) -> str:
        """Return the selected OCR engine and its diagnostic status."""
        self._ensure_engine()
        return self._engine_status

    def _enhance_patch(self, gray_patch: np.ndarray) -> np.ndarray:
        """Upscale and binarize a selected digit patch."""
        ph, pw = gray_patch.shape[:2]
        if ph < 8 or pw < 8:
            return gray_patch
        resized = cv2.resize(
            gray_patch,
            (pw * config.ocr.patch_resize_factor,
             ph * config.ocr.patch_resize_factor),
            interpolation=cv2.INTER_CUBIC,
        )
        resized = cv2.createCLAHE(
            clipLimit=config.ocr.patch_clahe_clip,
            tileGridSize=(4, 4),
        ).apply(resized)
        # The block size follows the actual resized patch.  The old fixed
        # OCRConfig.patch_adaptive_block value was not read by this path.
        resized_min = min(resized.shape[:2])
        block = max(3, min(11, resized_min // 5)) | 1
        binary = cv2.adaptiveThreshold(
            resized,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block,
            config.ocr.patch_adaptive_C,
        )
        if np.sum(binary < 128) > np.sum(binary >= 128):
            binary = cv2.bitwise_not(binary)
        return binary

    def _ocr_single_patch(self, patch: np.ndarray) -> list[tuple[str, float]]:
        if self._engine == 'template':
            result = self._template_ocr.recognize(patch)
            return [result] if result else []
        if self._engine == 'tesseract':
            return self._ocr_tess(patch)
        if self._engine == 'easyocr' and self._easyocr:
            return self._ocr_easy(patch)
        return []

    def ocr_patch_to_digit(self, patch: np.ndarray,
                           bbox: tuple,
                           gray_region: np.ndarray = None) -> DigitInfo:
        """OCR a component crop selected by the upstream main-scale stage.

        ``bbox`` is kept in the main-scale image coordinate system and is used
        to place the returned ``DigitInfo``.  A gray crop is an optional second
        preprocessing variant; it does not select or relocate the component.
        """
        if patch is None or patch.size == 0 or bbox is None:
            return None
        self._ensure_engine()

        patch_variants = [patch.copy()]
        if len(patch.shape) == 2:
            patch_variants.append(cv2.bitwise_not(patch))
        if gray_region is not None:
            x1, y1, x2, y2 = bbox
            height, width = gray_region.shape[:2]
            x1 = max(0, min(int(x1), width - 1))
            x2 = max(0, min(int(x2), width))
            y1 = max(0, min(int(y1), height - 1))
            y2 = max(0, min(int(y2), height))
            gray_patch = gray_region[y1:y2, x1:x2]
            if gray_patch.size > 0:
                patch_variants.append(self._enhance_patch(gray_patch))

        results = []
        for candidate_patch in patch_variants:
            results = self._ocr_single_patch(candidate_patch)
            if results:
                break

        for text, confidence in results:
            if not text.isdigit():
                continue
            value = int(text)
            if value > 15:
                continue
            x1, y1, x2, y2 = bbox
            return DigitInfo(
                x=(x1 + x2) // 2,
                y=(y1 + y2) // 2,
                value=value,
                text=text,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
            )
        return None

    def _ocr_tess(self, patch: np.ndarray) -> list[tuple[str, float]]:
        """Run Tesseract in single-line numeric mode."""
        try:
            text = pytesseract.image_to_string(
                patch,
                config='--psm {psm} -c tessedit_char_whitelist={wl}'.format(
                    psm=config.ocr.tesseract_psm,
                    wl=config.ocr.tesseract_whitelist,
                ),
            ).strip()
        except Exception:
            return []
        return [(text, 0.7)] if text.isdigit() else []

    def _ocr_easy(self, patch: np.ndarray) -> list[tuple[str, float]]:
        inp = patch if len(patch.shape) == 3 else cv2.cvtColor(patch, cv2.COLOR_GRAY2BGR)
        try:
            results = self._easyocr.readtext(
                inp,
                allowlist=config.ocr.easyocr_allowlist,
                paragraph=False,
                min_size=config.ocr.easyocr_min_size,
                text_threshold=config.ocr.easyocr_text_threshold,
                low_text=config.ocr.easyocr_low_text,
            )
        except Exception:
            return []
        return [
            (text.strip(), confidence)
            for _, text, confidence in results
            if text.strip().isdigit() and confidence > config.ocr.easyocr_min_conf
        ]

    def _ensure_engine(self):
        """Initialize OCR lazily: template, Tesseract, EasyOCR, then fallback."""
        if self._engine is not None:
            return
        if self._template_ocr.available():
            self._engine = 'template'
            self._engine_status = f"Template OCR ({self._template_ocr.template_dir})"
            return

        if _HAS_TESSERACT:
            try:
                version = pytesseract.get_tesseract_version()
                self._engine = 'tesseract'
                self._engine_status = f"Tesseract {version}"
                return
            except Exception as exc:
                warnings.warn(
                    f"pytesseract is installed but the Tesseract binary is unavailable: {exc}"
                )

        if _HAS_EASYOCR:
            try:
                self._easyocr = easyocr.Reader(['en'], gpu=False, verbose=False)
                self._engine = 'easyocr'
                self._engine_status = "EasyOCR (CPU)"
                return
            except Exception as exc:
                warnings.warn(f"EasyOCR initialization failed: {exc}")

        self._engine = 'fallback'
        self._engine_status = "No OCR engine"
        warnings.warn(
            "No usable OCR engine was found. Install Tesseract or EasyOCR."
        )


_OCR_READER_SINGLETON = None


def get_ocr_reader_singleton() -> DigitReader:
    """Return the lazily initialized OCR reader used by ``merger``."""
    global _OCR_READER_SINGLETON
    if _OCR_READER_SINGLETON is None:
        _OCR_READER_SINGLETON = DigitReader()
    return _OCR_READER_SINGLETON
