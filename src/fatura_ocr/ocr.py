"""OCR (RapidOCR / ONNX, roda na CPU; os modelos vêm dentro do pacote, sem download)."""
from __future__ import annotations

import threading

from .parser import OcrLine, group_lines

TARGET_WIDTH = 1400  # a leitura foi calibrada com capturas de ~740px redimensionadas para ~2x

# Captura "rolada" (o celular junta a tela inteira numa imagem bem alta): o OCR reduziria a imagem
# toda e o texto ficaria ilegível, então ela é lida em pedaços do tamanho de uma tela, sobrepostos.
TALL_RATIO = 2.6   # altura/largura acima disso = captura rolada
TILE_RATIO = 2.0   # pedaço com proporção de tela de celular
TILE_STEP = 0.6    # passo entre pedaços: 40% de sobreposição, toda transação aparece inteira em algum
EDGE = 0.012       # texto encostado numa borda interna do pedaço foi cortado ao meio: ignorado
MIN_WIDTH = 500    # abaixo disso o texto fica pequeno demais (imagem reduzida por app de mensagem)

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # import tardio: deixa o app abrir rápido
        _engine = RapidOCR()
    return _engine


def _decode(image_bytes: bytes):
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("arquivo não é uma imagem legível (use PNG, JPG ou WEBP)")
    return img


def _ocr(img, drop_top: bool = False, drop_bottom: bool = False) -> list[OcrLine]:
    """OCR de uma tela (ou pedaço). Coordenadas em pixels da imagem recebida."""
    import cv2

    h, w = img.shape[:2]
    k = TARGET_WIDTH / w
    img2 = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    with _lock:
        result, _ = _get_engine()(img2)
    boxes = []
    for box, text, conf in result or []:
        top, bottom = min(p[1] for p in box) / k, max(p[1] for p in box) / k
        if (drop_top and top < EDGE * h) or (drop_bottom and bottom > (1 - EDGE) * h):
            continue  # linha cortada pela borda do pedaço; o pedaço vizinho a lê inteira
        boxes.append((float(box[0][1]) / k, float(box[0][0]) / k, text, float(conf)))
    return group_lines(boxes, h)


def tile_tops(h: int, w: int) -> list[int]:
    """Topo de cada pedaço de uma imagem alta (último pedaço encostado no fim)."""
    tile = int(w * TILE_RATIO)
    if h <= w * TALL_RATIO or tile >= h:
        return [0]
    step = int(tile * TILE_STEP)
    return list(range(0, h - tile, step)) + [h - tile]


def image_width(image_bytes: bytes) -> int:
    return _decode(image_bytes).shape[1]


def read_screens(image_bytes: bytes, on_part=None) -> list[tuple[list[OcrLine], int, bool, bool, int]]:
    """Lê uma imagem. Retorna uma "tela" por pedaço:
    (linhas, altura, tem barra no topo, tem barra embaixo, topo do pedaço na imagem inteira).

    Captura normal = um pedaço. `on_part(feitos, total)` é chamado antes do primeiro e depois de cada
    pedaço de uma captura rolada (para a barra de progresso).
    """
    img = _decode(image_bytes)
    h, w = img.shape[:2]
    tops = tile_tops(h, w)
    if len(tops) == 1:
        return [(_ocr(img), h, True, True, 0)]
    tile = int(w * TILE_RATIO)
    out = []
    if on_part:
        on_part(0, len(tops))
    for j, y0 in enumerate(tops):
        first, last = j == 0, j == len(tops) - 1
        lines = _ocr(img[y0:y0 + tile], drop_top=not first, drop_bottom=not last)
        # barra de status só no topo do primeiro pedaço; no fim da captura rolada pode nem haver
        # barra de navegação, então o último pedaço não corta a margem de baixo
        out.append((lines, tile, first, False, y0))
        if on_part:
            on_part(j + 1, len(tops))
    return out


def read_lines(image_bytes: bytes) -> tuple[list[OcrLine], int]:
    """Uma captura normal (compatibilidade): (linhas, altura)."""
    lines, h, _, _, _ = read_screens(image_bytes)[0]
    return lines, h
