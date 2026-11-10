"""Nome canônico por estabelecimento: o mesmo lugar sempre sai com o mesmo texto.

O OCR pode ler o mesmo estabelecimento com espaçamento diferente ("LOJAEXEMPLO" / "LOJA EXEMPLO").
Guardamos, por chave normalizada (só letras/dígitos, maiúsculas), o primeiro nome visto, e
reaproveitamos nas próximas capturas e nos próximos meses. Se o usuário corrigir um nome na
tela, o nome corrigido passa a valer para o futuro.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

# Letras que o OCR costuma trocar entre si. Só uma troca dessas (mesmo tamanho, uma posição) une
# duas grafias; "DROGASIL 1234" e "1235", ou "RESTAURANTE" e "RESTAURANTES", ficam separados.
CONFUSABLE = [set("IL1|"), set("O0DQ"), set("S5"), set("B8"), set("Z2"), set("G6")]


def _ocr_slip(a: str, b: str) -> bool:
    if len(a) != len(b) or len(a) < 8:
        return False
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return len(diffs) == 1 and any(diffs[0][0] in g and diffs[0][1] in g for g in CONFUSABLE)


def key_of(merchant: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", merchant.upper())


class AliasStore:
    def __init__(self, path: Path):
        self.path = path
        self.map: dict[str, str] = {}
        if path.exists():
            try:
                self.map = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.map = {}  # arquivo corrompido: recomeça, não derruba o app

    def lookup(self, merchant: str) -> tuple[str, str]:
        """(chave, nome canônico) se já conhecido; senão (chave, '')."""
        k = key_of(merchant)
        if k in self.map:
            return k, self.map[k]
        near = next((n for n in self.map if _ocr_slip(k, n)), None)
        return (near, self.map[near]) if near else (k, "")

    def canonicalise(self, spellings: list[tuple[str, float]]) -> list[str]:
        """Resolve cada grafia para o nome canônico, criando os que faltam (voto por maioria,
        desempate por confiança do OCR e por ter mais espaços)."""
        groups: dict[str, list[tuple[str, float]]] = collections.OrderedDict()
        for text, conf in spellings:
            groups.setdefault(key_of(text), []).append((re.sub(r"\s+", " ", text).strip(), conf))
        for k, votes in groups.items():
            if self.lookup(k)[1]:
                continue
            count = collections.Counter(t for t, _ in votes)
            self.map[k] = max(count, key=lambda t: (count[t], max(c for t2, c in votes if t2 == t), t.count(" "), t))
        return [self.lookup(text)[1] or re.sub(r"\s+", " ", text).strip() for text, _ in spellings]

    def remember(self, merchant_key: str, name: str) -> None:
        name = re.sub(r"\s+", " ", name).strip()
        if merchant_key and name:
            self.map[merchant_key] = name

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.map, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        except OSError:
            pass  # não conseguir salvar apelidos não deve impedir o uso
