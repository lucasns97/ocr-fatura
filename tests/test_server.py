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

    def test_index_injects_token_and_defaults(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-token="t0k"', r.text)
        self.assertNotIn("__DEFAULT", r.text)

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

    def test_csv_and_save(self):
        r = self.c.post("/api/csv", json={"rows": [ROW], "ano": 2026, "mes": 10}, headers=self.h)
        self.assertEqual(r.json()["filename"], "fatura-inter-2026-10.csv")
        self.assertIn("STREAMING ABC;PAGAMENTOS", r.json()["text"])

        target = self.home / "out" / "x.csv"
        body = {"rows": [ROW], "path": str(target), "ano": 2026, "mes": 10}
        r = self.c.post("/api/save", json=body, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(target.read_bytes().startswith(b"\xef\xbb\xbfData;"))   # BOM para o Excel
        self.assertEqual(self.c.post("/api/save", json=body, headers=self.h).status_code, 409)
        self.assertEqual(self.c.post("/api/save", json=dict(body, overwrite=True), headers=self.h).status_code, 200)
        # pasta -> nome padrão dentro dela
        r = self.c.post("/api/save", json=dict(body, path=str(self.home)), headers=self.h)
        self.assertTrue(r.json()["path"].endswith("fatura-inter-2026-10.csv"))


if __name__ == "__main__":
    unittest.main()
