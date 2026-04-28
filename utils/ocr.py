from __future__ import annotations

import easyocr
import numpy as np
from PIL import Image

_reader = None


def get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    return _reader


def extract_text_from_image(image: Image.Image) -> list[dict]:
    """
    Returns list of {text, confidence, bbox} from a PIL Image.
    """
    reader = get_reader()
    img_array = np.array(image)
    results = reader.readtext(img_array)

    texts = []
    for bbox, text, confidence in results:
        if confidence > 0.3 and text.strip():
            texts.append({
                "text": text.strip(),
                "confidence": round(confidence * 100, 1),
                "bbox": bbox,
            })
    return texts


def deduplicate_texts(all_frame_texts: list[list[dict]]) -> list[str]:
    """
    Remove duplicate texts across frames, return unique Korean/text lines.
    """
    seen = set()
    unique = []
    for frame_texts in all_frame_texts:
        for item in frame_texts:
            t = item["text"]
            if t not in seen:
                seen.add(t)
                unique.append(t)
    return unique
