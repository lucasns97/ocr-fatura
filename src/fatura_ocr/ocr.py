"""OCR (RapidOCR / ONNX, roda na CPU; os modelos vêm dentro do pacote, sem download)."""
from __future__ import annotations

import threading

from .parser import OcrLine, group_lines

TARGET_WIDTH = 1400  # a leitura foi calibrada com capturas de ~740px redimensionadas para ~2x

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # import tardio: deixa o app abrir rápido
        _engine = RapidOCR()
    return _engine


def read_lines(image_bytes: bytes) -> tuple[list[OcrLine], int]:
    """Lê uma captura. Retorna (linhas em coordenadas da imagem original, altura original)."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("arquivo não é uma imagem legível (use PNG ou JPG)")
    h, w = img.shape[:2]
    k = TARGET_WIDTH / w
    img2 = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    with _lock:
        result, _ = _get_engine()(img2)
    boxes = [(float(box[0][1]) / k, float(box[0][0]) / k, text, float(conf)) for box, text, conf in (result or [])]
    return group_lines(boxes, h), h
