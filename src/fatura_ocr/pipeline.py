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
                   total_cents: int | None, aliases: AliasStore, read_lines=None, progress=None) -> Result:
    """`read_lines` é injetável para testes (substitui o OCR).

    `progress(índice, estado, **kw)`, se dado, é chamado quando cada captura começa ("start") e termina
    ("done", ou "skipped" se for igual a uma anterior): a página mostra o andamento real. Captura
    rolada: também "part" a cada pedaço, com frac= (0..1) e parts= (nº de pedaços); o callback deve
    aceitar **kw.
    """
    progress = progress or (lambda i, state, **kw: None)
    small: list[int] = []
    if read_lines is None:
        from .ocr import EDGE, MIN_WIDTH, read_screens

        def read(data, on_part):
            return read_screens(data, on_part, on_width=lambda w: small.append(i) if w < MIN_WIDTH else None)
    else:  # testes: read_lines(data) -> (linhas, altura) de uma captura normal
        def read(data, on_part):
            lines, height = read_lines(data)
            return [(lines, height, True, True, None)]
    closing = closing or default_closing(year, month)
    res = Result()
    screens: list[list[RawRow]] = []
    prev_date = None
    seen: dict[str, int] = {}
    read_count, card_warned = 0, False
    screen_image: list[int] = []  # de qual imagem enviada veio cada "tela" (pedaços de uma rolada = mesma)
    for i, data in enumerate(images):
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:  # mesma captura enviada duas vezes: duplicaria todas as linhas dela
            res.warnings.append(f"A imagem {i + 1} é igual à imagem {seen[digest] + 1} e foi ignorada.")
            progress(i, "skipped")
            continue
        seen[digest] = i
        try:
            progress(i, "start")
            # captura rolada (bem alta) vem em vários pedaços sobrepostos; cada um vira uma "tela" e a
            # remoção de sobreposição junta tudo, como se fossem capturas separadas
            parts = read(data, lambda k, n, i=i: progress(i, "part", frac=k / n, parts=n))
        except ValueError as e:
            raise ValueError(f"Imagem {i + 1}: {e}") from e
        found, estimated, no_header = 0, 0, 0
        headers: list[tuple[float, tuple[int, int]]] = []  # cabeçalhos de data já vistos, em y da imagem inteira
        for lines, height, cut_top, cut_bottom, y0 in parts:
            known = False
            if y0:  # pedaço do meio de uma captura rolada: vale a data do último cabeçalho ACIMA dele
                # (o pedaço anterior foi além, por causa da sobreposição; a "última data" dele seria de baixo).
                # Um cabeçalho encostado no topo deste pedaço é descartado por ele (texto cortado), mas
                # vale para as linhas logo abaixo: por isso a margem.
                above = [d for y, d in headers if y < y0 + 2 * EDGE * height]
                start, known = (above[-1], True) if above else (prev_date, False)
            else:
                start = prev_date
            # data vinda de um cabeçalho da mesma imagem é certa: não marca "revisar"
            sr = parse_screen(lines, height, i, start, cut_top, cut_bottom, start_known=known)
            if y0 is not None:
                headers = sorted(set(headers) | {(y0 + y, d) for y, d in sr.headers})
            prev_date = (headers[-1][1] if headers else None) or sr.last_date or prev_date
            if sr.card_month and sr.card_month != month and not card_warned:
                card_warned = True
                res.warnings.append(
                    f"A imagem {i + 1} mostra a fatura de {MONTH_NAMES[sr.card_month - 1].capitalize()}, "
                    f"mas o mês escolhido é {MONTH_NAMES[month - 1].capitalize()}. Confira o formulário.")
            found += len(sr.rows)
            estimated += sr.estimated
            no_header += sr.no_header
            screens.append(sr.rows)
            screen_image.append(i)
        if estimated:
            n = "1 lançamento" if estimated == 1 else f"{estimated} lançamentos"
            res.warnings.append(
                f"Imagem {i + 1}: {n} no topo da captura sem o título do dia (ele ficou acima da tela). "
                f"Usamos a data do primeiro dia visível como estimativa (a data real é essa ou posterior) "
                f"e marcamos com ⚠ revisar: confira a data, ou envie também a captura de cima.")
        if not found and no_header:
            res.warnings.append(
                f"Imagem {i + 1}: há valores, mas nenhum título de dia (ex.: \"Quarta, 22 de jul\") aparece na captura, "
                f"então não dá para saber a data. Envie também a captura de cima, que mostra o dia.")
        elif not found:
            res.warnings.append(f"Nenhuma transação encontrada na imagem {i + 1}. É a tela 'Faturas' do app?")
        read_count += 1
        progress(i, "done")
    merged, removed = merge_screens(screens)
    for i in small:
        res.warnings.append(
            f"A imagem {i + 1} tem resolução baixa demais para ler bem (foi reduzida ao ser enviada?). "
            f"Use o arquivo original da captura.")
    rows, undated, late = build_rows(merged, closing, aliases)
    aliases.save()
    if undated:
        res.warnings.append(f"{undated} transação(ões) com data inválida foram ignoradas.")
    if late:
        res.warnings.append(
            f"{late} compra(s) com data depois do fechamento ({closing:%d/%m/%Y}). Se o ano estiver errado, "
            f"ajuste o fechamento em Avançado e leia de novo.")
    res.rows = rows
    res.stats["images"] = read_count                 # capturas lidas (uma rolada conta como uma)
    res.stats["ignored_images"] = len(images) - read_count
    res.stats["rows"] = len(rows)
    # repetidas entre capturas enviadas; a sobreposição entre pedaços de uma mesma captura rolada é
    # detalhe interno e não entra na conta mostrada ao usuário
    res.stats["duplicates_removed"] = sum(k for k, a, b in zip(removed, screen_image, screen_image[1:]) if a != b)
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
