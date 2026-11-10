"""Das capturas ao conjunto final de linhas: OCR, remoção de sobreposição, ano, nomes canônicos."""
from __future__ import annotations

import calendar
import difflib
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from .aliases import AliasStore, key_of
from .money import format_money
from .parser import MONTH_NAMES, OcrLine, RawRow, parse_screen

LOW_CONF = 0.70  # abaixo disso a linha é marcada "revisar" na tela
# O fechamento real costuma cair alguns dias depois do padrão (fim do mês anterior ao vencimento).
# Aceitamos compras até esta folga depois do fechamento antes de jogá-las para o ano anterior.
SLACK_DAYS = 15


def default_closing(year: int, month: int) -> date:
    """Último dia de compras assumido para a fatura que VENCE em month/year.

    A fatura vence no mês seguinte ao fechamento (ex.: vence 07/09, fecha no fim de agosto),
    então o padrão é o último dia do mês anterior. Pode ser ajustado no formulário.
    """
    y, m = (year, month - 1) if month > 1 else (year - 1, 12)
    return date(y, m, calendar.monthrange(y, m)[1])


def infer_date(day: int, month: int, closing: date, installment: str = "") -> date | None:
    """O app mostra só 'dia de mês'; falta o ano.

    A data nunca passa do fechamento. Entre os anos possíveis, escolhe a data mais próxima de
    quando a compra deveria ter sido feita: no fechamento para compra à vista, e (k-1) meses antes
    para a parcela k (ex.: parcela 12 de 12 de "15 de ago" numa fatura de set/2026 é de 2025).
    """
    k = int(installment.split("/")[0]) if installment else 1
    expected = closing.toordinal() - round((k - 1) * 30.44)
    best = None
    for y in (closing.year, closing.year - 1, closing.year - 2, closing.year - 3):
        try:
            d = date(y, month, day)
        except ValueError:
            continue  # 29/fev em ano não bissexto
        if d.toordinal() <= closing.toordinal() + SLACK_DAYS and (
                best is None or abs(d.toordinal() - expected) < abs(best.toordinal() - expected)):
            best = d
    return best


def _same(a: RawRow, b: RawRow) -> bool:
    """Mesma transação lida em duas capturas diferentes.

    Tolera erros pequenos de OCR e linhas cortadas na borda da tela (estabelecimento truncado ou
    ausente, "Parcela x de y" fora da tela).
    """
    if (a.day, a.month, a.amount) != (b.day, b.month, b.amount):
        return False
    if a.installment and b.installment and a.installment != b.installment:
        return False
    ka, kb = key_of(a.merchant), key_of(b.merchant)
    if not ka or not kb or ka.startswith(kb) or kb.startswith(ka):
        return True
    return difflib.SequenceMatcher(None, ka, kb).ratio() >= 0.8


def _fuller(a: RawRow, b: RawRow) -> RawRow:
    """Das duas leituras da mesma transação, fica a mais completa (a da borda pode estar cortada)."""
    score = lambda r: (bool(r.installment), bool(r.category), len(key_of(r.merchant)), r.conf)  # noqa: E731
    return b if score(b) > score(a) else a


def overlap_len(prev: list[RawRow], nxt: list[RawRow]) -> int:
    """Quantas transações no fim de `prev` são as mesmas do começo de `nxt` (maior sobreposição).

    Comparar a sequência, e não linha a linha, mantém compras legítimas repetidas (duas corridas
    iguais no mesmo dia) quando elas não estão na região de sobreposição.
    """
    for n in range(min(len(prev), len(nxt)), 0, -1):
        if all(_same(a, b) for a, b in zip(prev[-n:], nxt[:n])):
            return n
    return 0


def merge_screens(screens: list[list[RawRow]]) -> tuple[list[RawRow], list[int]]:
    """Junta as capturas na ordem recebida. Retorna (linhas, sobreposição removida por emenda)."""
    out: list[RawRow] = []
    removed: list[int] = []
    for rows in screens:
        k = overlap_len(out, rows) if out else 0
        removed.append(k)
        for j in range(k):  # na emenda, mantém a leitura mais completa de cada transação
            out[len(out) - k + j] = _fuller(out[len(out) - k + j], rows[j])
        out.extend(rows[k:])
    return out, removed[1:]


@dataclass
class Result:
    rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def build_rows(raw: list[RawRow], closing: date, aliases: AliasStore) -> tuple[list[dict], int, int]:
    """Retorna (linhas, sem data válida, depois do fechamento)."""
    names = aliases.canonicalise([(r.merchant, r.conf) for r in raw])
    rows, undated, late = [], 0, 0
    for i, (r, name) in enumerate(zip(raw, names)):
        d = infer_date(r.day, r.month, closing, r.installment)
        if d is None:
            undated += 1
            continue
        late += d > closing
        rows.append({
            "id": i,
            "data": d.strftime("%d/%m/%Y"),
            "lancamento": name,
            "lancamento_ocr": name,
            "categoria": r.category,
            "tipo": f"Parcela {int(r.installment.split('/')[0])} de {int(r.installment.split('/')[1])}" if r.installment else "Compra à vista",
            "valor": format_money(r.amount),
            "valor_centavos": r.amount,
            "conf": round(r.conf, 2),
            "revisar": r.conf < LOW_CONF,
            "chave": key_of(r.merchant),
            "screen": r.screen + 1,
        })
    rows.sort(key=lambda x: (x["data"][6:], x["data"][3:5], x["data"][:2]), reverse=True)
    return rows, undated, late


def process_images(images: list[bytes], year: int, month: int, closing: date | None,
                   total_cents: int | None, aliases: AliasStore, read_lines=None) -> Result:
    """`read_lines` é injetável para testes (substitui o OCR)."""
    if read_lines is None:
        from .ocr import read_lines
    closing = closing or default_closing(year, month)
    res = Result()
    screens: list[list[RawRow]] = []
    prev_date = None
    seen: dict[str, int] = {}
    for i, data in enumerate(images):
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:  # mesma captura enviada duas vezes: duplicaria todas as linhas dela
            res.warnings.append(f"A imagem {i + 1} é igual à imagem {seen[digest] + 1} e foi ignorada.")
            continue
        seen[digest] = i
        try:
            lines, height = read_lines(data)
        except ValueError as e:
            raise ValueError(f"Imagem {i + 1}: {e}") from e
        sr = parse_screen(lines, height, i, prev_date)
        prev_date = sr.last_date or prev_date
        if sr.card_month and sr.card_month != month:
            res.warnings.append(
                f"A imagem {i + 1} mostra a fatura de {MONTH_NAMES[sr.card_month - 1].capitalize()}, "
                f"mas o mês escolhido é {MONTH_NAMES[month - 1].capitalize()}. Confira o formulário.")
        if not sr.rows:
            res.warnings.append(f"Nenhuma transação encontrada na imagem {i + 1}. É a tela 'Faturas' do app?")
        screens.append(sr.rows)
    merged, removed = merge_screens(screens)
    rows, undated, late = build_rows(merged, closing, aliases)
    aliases.save()
    if undated:
        res.warnings.append(f"{undated} transação(ões) com data inválida foram ignoradas.")
    if late:
        res.warnings.append(
            f"{late} compra(s) com data depois do fechamento ({closing:%d/%m/%Y}). Se o ano estiver errado, "
            f"ajuste o fechamento em Avançado e leia de novo.")
    res.rows = rows
    res.stats["images"] = len(screens)               # capturas lidas
    res.stats["ignored_images"] = len(images) - len(screens)
    res.stats["rows"] = len(rows)
    res.stats["duplicates_removed"] = sum(removed)
    res.stats["closing"] = closing.isoformat()
    res.stats["reconciliation"] = reconcile(rows, total_cents)
    # a mensagem da conferência é montada na página, que a recalcula a cada edição salva
    return res


def reconcile(rows: list[dict], total_cents: int | None) -> dict | None:
    """Compara a soma com o total da fatura (opcional). Pagamentos/estornos (negativos) ficam de fora
    da soma de compras; se o total só bate com o líquido, também aceitamos."""
    if total_cents is None:
        return None
    charges = sum(r["valor_centavos"] for r in rows if r["valor_centavos"] > 0)
    net = sum(r["valor_centavos"] for r in rows)
    ok = total_cents in (charges, net)
    diff = total_cents - charges
    return {"total": total_cents, "charges": charges, "net": net, "diff": diff, "ok": ok}
