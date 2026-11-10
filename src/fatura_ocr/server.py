"""Servidor local (127.0.0.1). A página e a API são servidas por aqui; nada sai da máquina.

Proteções, porque o servidor pode gravar arquivos: só aceita requisições cujo Host seja local
(contra DNS rebinding) e exige um token aleatório, entregue só dentro da página, em toda
chamada /api (impede que outro site aberto no navegador use a API).
"""
from __future__ import annotations

import html
import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import csvio
from .aliases import AliasStore
from .money import parse_user_money
from .pipeline import default_closing, process_images

STATIC = Path(__file__).parent / "static"
MAX_FILES = 40
MAX_BYTES = 20 * 1024 * 1024


def app_home() -> Path:
    """Pasta onde ficam os apelidos de estabelecimentos (FATURA_OCR_HOME para trocar)."""
    return Path(os.environ.get("FATURA_OCR_HOME") or Path.home() / ".fatura-ocr")


def default_dir() -> Path:
    """Pasta sugerida para salvar: Documentos, se existir; senão a pasta do usuário."""
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


class Rows(BaseModel):
    rows: list[dict]
    delimiter: str = "semicolon"
    ano: int = 0
    mes: int = 0


class NormalizeBody(BaseModel):
    rows: list[dict]
    remember: bool = True


class SaveBody(Rows):
    path: str
    overwrite: bool = False


def create_app(token: str | None = None, home: Path | None = None, read_lines=None) -> FastAPI:
    token = token or secrets.token_urlsafe(24)
    home = home or app_home()
    aliases = AliasStore(home / "merchant_aliases.json")
    app = FastAPI(title="Fatura OCR", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return JSONResponse({"detail": "Host não permitido"}, status_code=403)
        if request.url.path.startswith("/api/") and request.headers.get("x-token") != token:
            return JSONResponse({"detail": "Token inválido. Recarregue a página."}, status_code=403)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        today = date.today()
        return (page.replace("__TOKEN__", token)
                    .replace("__DEFAULT_YEAR__", str(today.year))
                    .replace("__DEFAULT_MONTH__", str(today.month))
                    .replace("__DEFAULT_DIR__", html.escape(str(default_dir()))))

    @app.post("/api/process")
    async def process(ano: int = Form(...), mes: int = Form(...), fechamento: str = Form(""),
                      total: str = Form(""), files: list[UploadFile] = File(...)):
        if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
            raise HTTPException(422, "Mês ou ano inválido.")
        if not files or len(files) > MAX_FILES:
            raise HTTPException(422, f"Envie de 1 a {MAX_FILES} capturas.")
        images = []
        for f in files:
            data = await f.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise HTTPException(413, f"{f.filename}: arquivo grande demais (máx. 20 MB).")
            images.append(data)
        try:
            closing = date.fromisoformat(fechamento) if fechamento.strip() else default_closing(ano, mes)
        except ValueError:
            raise HTTPException(422, "Data de fechamento inválida.") from None
        try:
            total_cents = parse_user_money(total) if total.strip() else None
        except ValueError:
            raise HTTPException(422, "Total da fatura inválido (ex.: R$ 1.234,56).") from None
        try:
            res = await _run(process_images, images, ano, mes, closing, total_cents, aliases, read_lines)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        return {"rows": res.rows, "warnings": res.warnings, "stats": res.stats,
                "filename": csvio.filename(ano, mes)}

    @app.post("/api/normalize")
    def normalize(body: NormalizeBody):
        rows, errors = csvio.normalize_rows(body.rows)
        if not errors and body.remember:
            # O nome na tela passa a valer para os próximos meses, inclusive quando o usuário desfaz
            # uma correção. Linhas sem mudança primeiro e corrigidas por último: a correção vence.
            for r in sorted(rows, key=lambda r: r.get("lancamento") != r.get("lancamento_ocr")):
                if r.get("chave") and r.get("lancamento"):
                    aliases.remember(r["chave"], r["lancamento"])
            aliases.save()
        return {"rows": rows, "errors": errors}

    @app.post("/api/csv")
    def make_csv(body: Rows):
        rows, errors = csvio.normalize_rows(body.rows)
        if errors:
            raise HTTPException(422, errors[0]["message"])
        return {"text": csvio.to_csv(rows, body.delimiter), "filename": _fname(body)}

    @app.post("/api/save")
    def save(body: SaveBody):
        rows, errors = csvio.normalize_rows(body.rows)
        if errors:
            raise HTTPException(422, errors[0]["message"])
        raw = body.path.strip().strip('"')
        if not raw:
            raise HTTPException(422, "Informe o caminho do arquivo.")
        path = Path(os.path.expandvars(raw)).expanduser()
        if not path.is_absolute():
            path = default_dir() / path
        if path.is_dir() or raw.endswith(("/", "\\")):
            path = path / _fname(body)
        if path.suffix.lower() != ".csv":
            path = path.with_name(path.name + ".csv")
        if path.exists() and not body.overwrite:
            raise HTTPException(409, f"O arquivo já existe: {path}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # utf-8 com BOM: o Excel em português abre os acentos corretamente
            path.write_bytes(csvio.to_csv(rows, body.delimiter, bom=True).encode("utf-8"))
        except OSError as e:
            raise HTTPException(422, f"Não foi possível salvar em {path}: {e.strerror or e}") from None
        return {"path": str(path.resolve()), "bytes": path.stat().st_size}

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _fname(body: Rows) -> str:
    return csvio.filename(body.ano, body.mes) if body.ano and 1 <= body.mes <= 12 else "fatura-inter.csv"


async def _run(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *args)
