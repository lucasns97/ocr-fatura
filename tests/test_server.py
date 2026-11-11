import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # httpx ausente
    TestClient = None

from fatura_ocr.server import create_app

from helpers import H, screen, tx

# dados fictícios (o repositório é público)
ROW = {"data": "23/08/2026", "lancamento": "STREAMING ABC", "categoria": "PAGAMENTOS", "tipo": "Compra à vista",
       "valor": "R$ 12,34", "chave": "STREAMINGABC", "lancamento_ocr": "STREAMING ABC"}


@unittest.skipIf(TestClient is None, "httpx não instalado (uv sync instala)")
class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        lines = screen(*tx("Domingo, 23 de ago", "Pagamentos", "-R$ 12,34", "STREAMING ABC"))
        app = create_app(token="t0k", home=self.home, read_lines=lambda _: (lines, H))
        self.c = TestClient(app, base_url="http://127.0.0.1:8765")
        self.h = {"X-Token": "t0k"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_due_month_is_next_month(self):
        from datetime import date
        from fatura_ocr.server import default_due
        self.assertEqual(default_due(date(2026, 11, 10)), (2026, 12))
        self.assertEqual(default_due(date(2026, 12, 31)), (2027, 1))

    def test_index_injects_token_and_defaults(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-token="t0k"', r.text)
        from datetime import date
        from fatura_ocr.server import default_due
        y, m = default_due(date.today())
        self.assertIn(f'data-year="{y}" data-month="{m}"', r.text)
        self.assertNotIn("__DEFAULT", r.text)

    def test_js_ids_exist_in_html(self):
        # app.js referenciando um elemento que a página não tem quebra a tela inteira
        import re
        from fatura_ocr.server import STATIC
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        ids = set(re.findall(r'\$\("#([\w-]+)', js))
        self.assertGreater(len(ids), 10)
        for i in ids:
            self.assertIn(f'id="{i}"', html, i)

    def test_assets_are_versioned_and_revalidated(self):
        # depois de uma atualização, o navegador não pode usar app.js/style.css antigos com a página nova
        from fatura_ocr.server import asset_version
        r = self.c.get("/")
        v = asset_version()
        self.assertIn(f'/static/app.js?v={v}"', r.text)
        self.assertIn(f'/static/style.css?v={v}"', r.text)
        self.assertIn(f'/static/money.js?v={v}"', r.text)
        self.assertIn(f'/static/stream.js?v={v}"', r.text)
        self.assertIn(f'/static/icon.svg?v={v}"', r.text)  # ícone (favicon e logo)
        self.assertEqual(self.c.get(f"/static/icon.svg?v={v}").headers["content-type"].split(";")[0], "image/svg+xml")
        self.assertEqual(r.headers["cache-control"], "no-cache")
        self.assertEqual(self.c.get(f"/static/app.js?v={v}").headers["cache-control"], "no-cache")

    def test_api_requires_token_and_local_host(self):
        self.assertEqual(self.c.post("/api/csv", json={"rows": []}).status_code, 403)
        evil = TestClient(self.c.app, base_url="http://evil.example:8765")
        self.assertEqual(evil.get("/").status_code, 403)   # DNS rebinding
        self.assertEqual(self.c.post("/api/csv", json={"rows": []}, headers=self.h).status_code, 200)

    def test_process(self):
        files = [("files", ("a.png", b"img", "image/png"))]
        r = self.c.post("/api/process", data={"ano": "2026", "mes": "9", "total": "12,34"}, files=files, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["filename"], "fatura-inter-2026-09.csv")
        self.assertEqual(body["rows"][0]["valor"], "R$ 12,34")
        self.assertTrue(body["stats"]["reconciliation"]["ok"])
        bad = self.c.post("/api/process", data={"ano": "2026", "mes": "13"}, files=files, headers=self.h)
        self.assertEqual(bad.status_code, 422)

    def test_process_stream_reports_each_image_then_result(self):
        import json
        files = [("files", ("a.png", b"img-a", "image/png")), ("files", ("b.png", b"img-b", "image/png")),
                 ("files", ("c.png", b"img-a", "image/png"))]
        r = self.c.post("/api/process?stream=1", data={"ano": "2026", "mes": "9"}, files=files, headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("application/x-ndjson"))
        evs = [json.loads(line) for line in r.text.splitlines() if line.strip()]
        self.assertEqual([(e["index"], e["state"]) for e in evs if e["event"] == "image"],
                         [(0, "start"), (0, "done"), (1, "start"), (1, "done"), (2, "skipped")])
        self.assertEqual(evs[-1]["event"], "result")
        self.assertEqual(evs[-1]["filename"], "fatura-inter-2026-09.csv")
        self.assertEqual(evs[-1]["stats"]["ignored_images"], 1)

    def test_process_stream_reports_errors(self):
        import json

        def broken(_):
            raise ValueError("arquivo não é uma imagem legível")
        app = create_app(token="t0k", home=self.home, read_lines=broken)
        c = TestClient(app, base_url="http://127.0.0.1:8765")
        r = c.post("/api/process?stream=1", data={"ano": "2026", "mes": "9"},
                   files=[("files", ("a.png", b"x", "image/png"))], headers=self.h)
        self.assertEqual(r.status_code, 200)
        last = json.loads(r.text.strip().splitlines()[-1])
        self.assertEqual(last["event"], "error")
        self.assertIn("Imagem 1", last["detail"])

    def test_process_stream_reports_unexpected_errors(self):
        import json

        def crash(_):
            raise RuntimeError("boom")
        c = TestClient(create_app(token="t0k", home=self.home, read_lines=crash), base_url="http://127.0.0.1:8765")
        r = c.post("/api/process?stream=1", data={"ano": "2026", "mes": "9"},
                   files=[("files", ("a.png", b"x", "image/png"))], headers=self.h)
        self.assertEqual(r.status_code, 200)
        last = json.loads(r.text.strip().splitlines()[-1])
        self.assertEqual(last, {"event": "error", "detail": "Erro inesperado ao ler as capturas."})

    def test_normalize_remembers_rename_and_its_undo(self):
        aliases = self.home / "merchant_aliases.json"
        r = self.c.post("/api/normalize", json={"rows": [dict(ROW, lancamento="Streaming")]}, headers=self.h)
        self.assertEqual(r.json()["errors"], [])
        self.assertIn('"Streaming"', aliases.read_text(encoding="utf-8"))
        self.c.post("/api/normalize", json={"rows": [ROW]}, headers=self.h)   # desfez a correção
        self.assertIn('"STREAMING ABC"', aliases.read_text(encoding="utf-8"))
        self.assertNotIn('"Streaming"', aliases.read_text(encoding="utf-8"))
        r = self.c.post("/api/normalize", json={"rows": [dict(ROW, valor="abc")]}, headers=self.h)
        self.assertEqual(r.json()["errors"][0]["index"], 0)

    def test_csv(self):
        r = self.c.post("/api/csv", json={"rows": [ROW], "ano": 2026, "mes": 10}, headers=self.h)
        self.assertEqual(r.json()["filename"], "fatura-inter-2026-10.csv")
        self.assertIn("STREAMING ABC;PAGAMENTOS", r.json()["text"])

    def test_no_server_side_file_writes(self):
        # o CSV é salvo pelo navegador; o servidor não tem rota para gravar caminhos escolhidos
        r = self.c.post("/api/save", json={"rows": [ROW], "path": str(self.home / "x.csv")}, headers=self.h)
        self.assertIn(r.status_code, (404, 405))
        self.assertFalse((self.home / "x.csv").exists())


if __name__ == "__main__":
    unittest.main()
