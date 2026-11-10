"""Linhas -> texto CSV (e validação das linhas editadas na tela)."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from .money import format_money, parse_user_money

HEADER = ["Data", "Lançamento", "Categoria", "Tipo", "Valor"]
DELIMITERS = {"semicolon": ";", "comma": ",", "tab": "\t"}


def filename(year: int, month: int) -> str:
    return f"fatura-inter-{year:04d}-{month:02d}.csv"


def normalize_row(row: dict) -> dict:
    """Valida e padroniza uma linha vinda da tela. Levanta ValueError com mensagem em português."""
    raw_date = str(row.get("data", "")).strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_date)
    if not m:
        raise ValueError(f"Data inválida: {raw_date!r} (use DD/MM/AAAA)")
    try:
        d = datetime(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        raise ValueError(f"Data inexistente: {raw_date}") from None
    try:
        cents = parse_user_money(str(row.get("valor", "")))
    except ValueError:
        raise ValueError(f"Valor inválido: {row.get('valor')!r} (ex.: R$ 1.234,56)") from None
    out = dict(row)
    out.update(
        data=d.strftime("%d/%m/%Y"),
        lancamento=re.sub(r"\s+", " ", str(row.get("lancamento", ""))).strip(),
        categoria=str(row.get("categoria", "")).strip().upper(),
        tipo=re.sub(r"\s+", " ", str(row.get("tipo", ""))).strip() or "Compra à vista",
        valor=format_money(cents),
        valor_centavos=cents,
    )
    return out


def normalize_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Retorna (linhas padronizadas, erros [{index, message}]). Sem erro => todas as linhas válidas."""
    good, errors = [], []
    for i, row in enumerate(rows):
        try:
            good.append(normalize_row(row))
        except ValueError as e:
            errors.append({"index": i, "message": str(e)})
            good.append(row)
    return good, errors


def to_csv(rows: list[dict], delimiter: str = "semicolon", bom: bool = False) -> str:
    """Texto CSV com o cabeçalho Data, Lançamento, Categoria, Tipo, Valor.

    Valor no formato do app/planilha pt-BR ('R$ 1.234,56'); pagamentos/estornos com sinal '-'.
    """
    if delimiter not in DELIMITERS:
        raise ValueError(f"separador desconhecido: {delimiter}")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIMITERS[delimiter], lineterminator="\r\n")
    w.writerow(HEADER)
    for r in rows:
        w.writerow([r["data"], r["lancamento"], r["categoria"], r["tipo"], r["valor"]])
    return ("﻿" if bom else "") + buf.getvalue()
