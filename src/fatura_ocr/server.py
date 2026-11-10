"""Servidor local (127.0.0.1). A página e a API são servidas por aqui; nada sai da máquina.

Proteções: só aceita requisições cujo Host seja local (contra DNS rebinding) e exige um token
aleatório, entregue só dentro da página, em toda chamada /api (impede que outro site aberto no
navegador use a API, que lê imagens e grava os nomes de estabelecimentos). Quem salva o CSV é o
navegador (janela "Salvar como" ou download); o servidor não grava arquivos escolhidos pelo usuário.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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


ASSETS = ("app.js", "money.js", "style.css")  # arquivos da página; todos ganham ?v= (cache)


def asset_version() -> str:
    """Muda quando algum arquivo da página muda: o link novo força o navegador a baixar a versão nova."""
    h = hashlib.sha256()
    for name in ASSETS:
        h.update((STATIC / name).read_bytes())
    return h.hexdigest()[:12]


def default_due(today: date) -> tuple[int, int]:
    """Mês de vencimento sugerido: o próximo. O normal é capturar a fatura ainda aberta, que vence no
    mês seguinte (a do mês corrente costuma já estar fechada ou paga)."""
    return (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)


class Rows(BaseModel):
    rows: list[dict]
    delimiter: str = "semicolon"
    ano: int = 0
    mes: int = 0


class NormalizeBody(BaseModel):
    rows: list[dict]
    remember: bool = True


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
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            # sempre revalida: depois de atualizar o programa o navegador não pode misturar versões
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        due_year, due_month = default_due(date.today())
        v = asset_version()
        for name in ASSETS:
            page = page.replace(f"/static/{name}", f"/static/{name}?v={v}")
        return (page.replace("__TOKEN__", token)
                    .replace("__DEFAULT_YEAR__", str(due_year))
                    .replace("__DEFAULT_MONTH__", str(due_month)))

    @app.post("/api/process")
    async def process(ano: int = Form(...), mes: int = Form(...), fechamento: str = Form(""),
                      total: str = Form(""), files: list[UploadFile] = File(...), stream: bool = False):
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
        result = lambda res: {"rows": res.rows, "warnings": res.warnings, "stats": res.stats,  # noqa: E731
                              "filename": csvio.filename(ano, mes)}
        if not stream:
            try:
                res = await _run(process_images, images, ano, mes, closing, total_cents, aliases, read_lines)
            except ValueError as e:
                raise HTTPException(422, str(e)) from None
            return result(res)

        # ?stream=1: uma linha JSON por evento, na hora em que acontece ({"event": "image", "index", "state"}),
        # e por último {"event": "result", ...} ou {"event": "error", "detail"}. A página mostra o progresso real.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def progress(i: int, state: str) -> None:  # chamado na thread do OCR
            loop.call_soon_threadsafe(queue.put_nowait, {"event": "image", "index": i, "state": state})

        async def work() -> None:
            try:
                res = await _run(process_images, images, ano, mes, closing, total_cents, aliases, read_lines, progress)
                await queue.put({"event": "result", **result(res)})
            except ValueError as e:
                await queue.put({"event": "error", "detail": str(e)})
            except Exception:  # noqa: BLE001 - a página precisa saber que acabou
                await queue.put({"event": "error", "detail": "Erro inesperado ao ler as capturas."})
            await queue.put(None)

        task = asyncio.create_task(work())

        async def events():
            while (item := await queue.get()) is not None:
                yield json.dumps(item, ensure_ascii=False) + "\n"
            await task

        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

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

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def _fname(body: Rows) -> str:
    return csvio.filename(body.ano, body.mes) if body.ano and 1 <= body.mes <= 12 else "fatura-inter.csv"


async def _run(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *args)
