from __future__ import annotations

import pytesseract
import numpy as np
from PIL import Image


def extract_text_from_image(image: Image.Image) -> list[dict]:
    """
    Returns list of {text, confidence} from a PIL Image.
    Uses Tesseract with Korean + English language pack.
    """
    config = "--oem 3 --psm 6 -l kor+eng"
    data = pytesseract.image_to_data(
        image, config=config, output_type=pytesseract.Output.DICT
    )

    texts = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = int(data["conf"][i])
        if text and conf > 30:
            texts.append({
                "text": text,
                "confidence": conf,
                "bbox": None,
            })
    return texts


def deduplicate_texts(all_frame_texts: list[list[dict]]) -> list[str]:
    seen = set()
    unique = []
    for frame_texts in all_frame_texts:
        for item in frame_texts:
            t = item["text"]
            if t not in seen:
                seen.add(t)
                unique.append(t)
    return unique
