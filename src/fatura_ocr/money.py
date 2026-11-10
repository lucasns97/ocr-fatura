"""Valores em reais. Internamente sempre centavos inteiros (nunca float)."""
from __future__ import annotations

import re

_MINUS = "-−–"  # hífen, sinal de menos, travessão (o OCR troca entre eles)


def format_money(cents: int) -> str:
    """1234567 -> 'R$ 12.345,67'; -200000 -> '-R$ 2.000,00'."""
    sign = "-" if cents < 0 else ""
    reais, cent = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def ocr_money(text: str) -> int:
    """Valor lido pelo OCR, como '-R$129.90' ou '+R$2.000.00'.

    O OCR às vezes troca a vírgula decimal por ponto, ou a perde; como o app sempre
    mostra duas casas decimais, os dois últimos dígitos são os centavos.
    Sinal '+' = crédito/pagamento (negativo no CSV); '-' ou sem sinal = compra (positivo).
    """
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise ValueError(f"sem dígitos em {text!r}")
    cents = int(digits)
    plus = re.match(r"\s*\+", text) is not None
    return -cents if plus else cents


def parse_user_money(text: str) -> int:
    """Valor digitado pelo usuário: 'R$ 1.234,56', '-8530,63', '12', '12.5', '(12,50)'.

    Aceita vírgula ou ponto como decimal (o último separador, se seguido de 1-2 dígitos).
    Sinal negativo = pagamento/estorno.
    """
    s = text.strip()
    if not s:
        raise ValueError("valor vazio")
    neg = s.startswith("(") and s.endswith(")")
    neg = neg or any(s.lstrip().startswith(m) for m in _MINUS) or re.match(r"^R\$\s*[-−–]", s) is not None
    core = re.sub(r"[^\d.,]", "", s)
    if not re.search(r"\d", core):
        raise ValueError(f"valor inválido: {text!r}")
    m = re.search(r"[.,](\d{1,2})$", core)
    if m:
        whole = re.sub(r"\D", "", core[: m.start()]) or "0"
        frac = m.group(1).ljust(2, "0")
    else:
        whole, frac = re.sub(r"\D", "", core), "00"
    cents = int(whole) * 100 + int(frac)
    return -cents if neg else cents
