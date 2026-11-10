"""Dados sintéticos para os testes (nada de dados reais: o repositório é público)."""
from __future__ import annotations

import glob

from fatura_ocr.parser import OcrLine

H = 1600  # altura da captura simulada (formato 738x1600, como as do app)


def screen(*items: str, start: float = 200, step: float = 40, conf: float = 0.9) -> list[OcrLine]:
    """Linhas de OCR de uma captura, de cima para baixo, já dentro da área útil."""
    return [OcrLine(start + i * step, t, conf) for i, t in enumerate(items)]


def tx(date: str, cat: str, amount: str, merchant: str, parcela: str = "") -> list[str]:
    out = [date] if date else []
    out += [cat, amount, merchant]
    if parcela:
        out.append(parcela)
    return out


def font_path() -> str | None:
    for pat in ("/usr/share/fonts/**/DejaVuSans.ttf", "/usr/share/fonts/**/LiberationSans-Regular.ttf",
                "C:/Windows/Fonts/segoeui.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return None


def render_screenshot(blocks: list[tuple[str, list[tuple[str, str, str, str]]]], width: int = 738) -> bytes:
    """Desenha uma captura no estilo do app (tema escuro). blocks = [(cabeçalho de data, [(categoria,
    valor, estabelecimento, parcela)])]. Retorna PNG em bytes."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    fp = font_path()
    big, small = ImageFont.truetype(fp, 24), ImageFont.truetype(fp, 20)
    im = Image.new("RGB", (width, H), (30, 30, 32))
    d = ImageDraw.Draw(im)
    d.text((40, 30), "16:18", font=small, fill=(240, 240, 240))
    d.text((300, 110), "Faturas", font=big, fill=(240, 240, 240))
    y = 220
    for header, rows in blocks:
        d.text((47, y), header, font=small, fill=(220, 220, 220))
        y += 80
        for cat, val, merch, parc in rows:
            d.text((186, y), cat, font=big, fill=(245, 245, 245))
            d.text((186, y + 36), val, font=big, fill=(80, 200, 120) if val.startswith("+") else (245, 245, 245))
            d.text((186, y + 72), merch, font=small, fill=(200, 200, 200))
            y += 108
            if parc:
                d.text((186, y), parc, font=small, fill=(200, 200, 200))
                y += 36
            y += 60
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
