"""Transforma as linhas de texto do OCR de UMA captura em transações.

Layout do app (Inter, pt-BR), de cima para baixo, por transação:

    Quinta, 20 de ago            <- cabeçalho de data (vale para as transações abaixo)
    Outros                       <- categoria (rótulo do app)
    -R$ 4,20                     <- valor ('-' compra, '+' pagamento/estorno)
    IOF INTERNACIONAL            <- estabelecimento (pode quebrar em 2+ linhas)
    Parcela 3 de 6               <- opcional

Este módulo não faz OCR: recebe linhas já lidas, o que o torna testável sem imagens.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from .money import ocr_money

MONTHS = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
          "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
MONTH_NAMES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
               "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Rótulos de categoria do app. O OCR perde acentos ("Serviços" -> "Servicos"); restauramos
# os que conhecemos. Rótulo desconhecido passa como foi lido.
KNOWN_CATEGORIES = [
    "Pagamentos", "Entretenimento", "Outros", "Compras", "Transporte", "Viagem", "Serviços",
    "Livrarias", "Ensino", "Alimentação", "Supermercado", "Restaurantes", "Saúde", "Educação",
    "Casa", "Lazer", "Vestuário", "Beleza", "Cloud", "Comida", "Assinaturas", "Farmácia",
    "Combustível",
]

# Margens (fração da altura da captura) com barra de status / de navegação do celular.
TOP_CUT, BOTTOM_CUT = 0.105, 0.9375

DATE_RE = re.compile(
    r"^(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)\s*,?\s*(\d{1,2})\s*de\s*([a-zç]{3})\b",
    re.I)
# Sinal opcional: se o OCR perder o '-', o 'R$' ainda ancora o valor (lido como compra).
AMOUNT_RE = re.compile(r"(?:([-+−–])\s*R[\$S5]?|\bR\$)\s*(\d[\d.,\s]*\d)")
INSTALL_RE = re.compile(r"Parcela\s*(\d+)\s*de\s*(\d+)", re.I)
# Cartão-resumo no topo da tela "Faturas" ("Setembro Paga", total, "Dia de vencimento 07/09",
# "Resumo da fatura", "Exportar fatura", "Despesas da fatura"). Não são transações: tudo até a
# última dessas linhas é ignorado. Aplicado a plain(texto).
CARD_RE = re.compile(r"dia de vencimento|resumo da fatura|exportar fatura|despesas da fatura|pagamento minimo")
# Botões fixos no rodapé da fatura em aberto ("Pagar com a Conta Inter", "Parcelar fatura"): não são
# texto de transação (sem isso, viravam parte do nome do último estabelecimento). Aplicado a plain(texto)
# SEM espaços: o OCR costuma ler esses botões grudados ("Pagarcoma ContaInter", "Parcelarfatura").
FOOTER_RE = re.compile(r"^(pagarcomaconta|pagarfatura|parcelarfatura|anteciparparcelas)")
CARD_MONTH_RE = re.compile(r"^(" + "|".join(MONTH_NAMES).replace("ç", "c") + r")\b")  # aplicado a plain(texto)


def plain(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


def restore_category(raw: str) -> str:
    raw = raw.strip()
    known = {plain(k): k for k in KNOWN_CATEGORIES}
    hit = difflib.get_close_matches(plain(raw), list(known), 1, 0.85)
    return (known[hit[0]] if hit else raw).upper()


@dataclass
class OcrLine:
    y: float
    text: str
    conf: float


@dataclass
class RawRow:
    day: int
    month: int
    category: str
    amount: int          # centavos; compra positiva, pagamento/estorno negativo
    merchant: str
    installment: str     # "3/6" ou ""
    conf: float
    screen: int = 0


UNSURE_CONF = 0.5  # rebaixa a confiança (a linha aparece como "revisar") quando algo foi deduzido


@dataclass
class ScreenResult:
    rows: list[RawRow] = field(default_factory=list)
    card_month: int | None = None   # mês do cartão "Setembro" no topo da 1ª captura, se visível
    last_date: tuple[int, int] | None = None  # última data vista; vale para o topo da próxima captura
    headers: list[tuple[float, tuple[int, int]]] = field(default_factory=list)  # (y, data) de cada cabeçalho
    estimated: int = 0              # linhas do topo sem cabeçalho acima: data estimada pelo primeiro abaixo
    no_header: int = 0              # valores encontrados sem nenhum cabeçalho de data na captura


def group_lines(boxes: list[tuple[float, float, str, float]], height: float) -> list[OcrLine]:
    """Une caixas de texto do mesmo nível vertical em linhas (ordenadas por x)."""
    tol = max(8.0, 14.0 * height / 1600.0)
    items = sorted(boxes)  # (y, x, text, conf)
    rows: list[list[tuple[float, str, float]]] = []
    ys: list[float] = []
    for y, x, text, conf in items:
        if rows and abs(ys[-1] - y) < tol:
            rows[-1].append((x, text, conf))
        else:
            rows.append([(x, text, conf)])
            ys.append(y)
    out = []
    for y, parts in zip(ys, rows):
        parts.sort()
        out.append(OcrLine(y, " ".join(t for _, t, _ in parts), min(c for *_, c in parts)))
    return out


def parse_screen(lines: list[OcrLine], height: float, screen: int = 0,
                 start_date: tuple[int, int] | None = None, cut_top: bool = True,
                 cut_bottom: bool = True, start_known: bool = False) -> ScreenResult:
    """`start_date`: última data da captura anterior. Linhas no topo desta captura, antes do primeiro
    cabeçalho de data, pertencem a ela (o cabeçalho rolou para fora da tela). A remoção de
    sobreposição descarta as que já estavam na captura anterior."""
    res = ScreenResult()
    for ln in lines:
        m = CARD_MONTH_RE.match(plain(ln.text.strip()))
        if m and ln.y < 0.5 * height:
            res.card_month = [plain(n) for n in MONTH_NAMES].index(m.group(1)) + 1
            break
    # margens com barra de status/navegação; pedaços do meio de uma captura rolada não têm
    lo, hi = (TOP_CUT * height if cut_top else -1), (BOTTOM_CUT * height if cut_bottom else height + 1)
    body = [ln for ln in lines if lo < ln.y < hi and not FOOTER_RE.match(re.sub(r"\s+", "", plain(ln.text)))]
    card = [i for i, ln in enumerate(body) if CARD_RE.search(plain(ln.text))]
    if card:
        # captura do topo da lista: o cartão-resumo não é transação, e nada aqui herda a data anterior
        body = body[card[-1] + 1:]
        start_date = None
    date = start_date
    saw_header = False
    guessing = False
    if date is None:
        # primeira captura começando no meio de um dia: o cabeçalho dele ficou acima da tela. A lista vai
        # da compra mais nova para a mais antiga, então a data real é a do primeiro cabeçalho visível
        # ou posterior: usamos esse dia como estimativa e a linha sai marcada "revisar" (sem cabeçalho visto)
        for ln in body:
            d = DATE_RE.match(ln.text.strip())
            if d and MONTHS.get(plain(d.group(3))):
                date, guessing = (int(d.group(2)), MONTHS[plain(d.group(3))]), True
                break
    for i, ln in enumerate(body):
        text = ln.text.strip()
        d = DATE_RE.match(text)
        if d:
            mon = MONTHS.get(plain(d.group(3)))
            date = (int(d.group(2)), mon) if mon else date
            if mon:
                res.headers.append((ln.y, date))
            saw_header = True
            continue
        a = AMOUNT_RE.search(text)
        if a and date is None and i > 0:
            res.no_header += 1
        if not (a and date and i > 0):
            continue
        try:
            amount = ocr_money((a.group(1) or "") + a.group(2))
        except ValueError:
            continue
        above = body[i - 1].text.strip()
        # categoria = linha logo acima do valor; se ali estiver a data ou outro valor, ela foi cortada
        category = "" if DATE_RE.match(above) or AMOUNT_RE.search(above) else restore_category(above)
        conf = min(ln.conf, body[i - 1].conf)
        if a.group(1) is None or not (saw_header or start_known):
            conf = min(conf, UNSURE_CONF)  # sinal não lido (pode ser pagamento) ou data herdada da captura anterior
        merchant, installment = [], ""
        for nxt_i in range(i + 1, len(body)):
            t = body[nxt_i].text.strip()
            following = body[nxt_i + 1].text if nxt_i + 1 < len(body) else ""
            if DATE_RE.match(t) or AMOUNT_RE.search(following):
                break  # começa a próxima transação (a linha atual é a categoria dela)
            inst = INSTALL_RE.search(t)
            if inst:
                installment = f"{int(inst.group(1))}/{int(inst.group(2))}"
            else:
                merchant.append(t)
                conf = min(conf, body[nxt_i].conf)
        if guessing and not saw_header:
            res.estimated += 1
        res.rows.append(RawRow(date[0], date[1], category, amount, re.sub(r"\s+", " ", " ".join(merchant)).strip(),
                               installment, conf, screen))
    res.last_date = date
    return res
