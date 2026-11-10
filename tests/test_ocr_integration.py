"""OCR de verdade sobre uma captura sintética (desenhada com Pillow, sem dados reais)."""
import tempfile
import unittest
from pathlib import Path

from helpers import font_path, render_screenshot

try:
    import rapidocr_onnxruntime  # noqa: F401
    import PIL  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE and font_path(), "rapidocr/Pillow ou fonte TTF ausentes")
class RealOcr(unittest.TestCase):
    def test_synthetic_screens_round_trip(self):
        from fatura_ocr.aliases import AliasStore
        from fatura_ocr.pipeline import process_images

        s1 = render_screenshot([
            ("Domingo, 23 de ago", [("Pagamentos", "-R$ 12,34", "STREAMING ABC SAO PAULO BRA", "")]),
            ("Sexta, 14 de ago", [("Transporte", "-R$ 25,00", "TAXI EXEMPLO Sao Paulo BRA", ""),
                                  ("Outros", "+R$ 2.000,00", "PAGAMENTO ON LINE", "")]),
        ])
        s2 = render_screenshot([
            ("Sexta, 14 de ago", [("Outros", "+R$ 2.000,00", "PAGAMENTO ON LINE", "")]),
            ("Segunda, 15 de jun", [("Viagem", "-R$ 200,00", "HOTEL FICTICIO SAO PAULO", "Parcela 3 de 6")]),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([s1, s2], 2026, 9, None, 23734, AliasStore(Path(tmp) / "a.json"))
        got = [(r["data"], r["valor"], r["tipo"]) for r in res.rows]
        self.assertEqual(got, [
            ("23/08/2026", "R$ 12,34", "Compra à vista"),
            ("14/08/2026", "R$ 25,00", "Compra à vista"),
            ("14/08/2026", "-R$ 2.000,00", "Compra à vista"),
            ("15/06/2026", "R$ 200,00", "Parcela 3 de 6"),
        ])
        self.assertEqual(res.stats["duplicates_removed"], 1)
        self.assertTrue(res.stats["reconciliation"]["ok"], res.stats)
        self.assertEqual(res.rows[3]["categoria"], "VIAGEM")


    def test_tall_screenshot_header_on_a_piece_seam(self):
        """Cabeçalho de data logo abaixo do topo de um pedaço (descartado por ele como texto cortado):
        as linhas abaixo ainda recebem a data certa, sem duplicar nem marcar "revisar"."""
        from fatura_ocr.aliases import AliasStore
        from fatura_ocr.ocr import tile_tops
        from fatura_ocr.pipeline import process_images

        def blocks():
            out, total = [], 0
            for k in range(6):
                rows = []
                for j in range(3 if k == 1 else 1):  # dia com várias compras atravessando o pedaço
                    cents = 1111 * (k + 1) + 37 * j
                    total += cents
                    rows.append(("Compras", f"-R$ {cents // 100},{cents % 100:02d}", f"LOJA FICTICIA {k}{j}", ""))
                out.append((f"{['Sexta', 'Quinta', 'Quarta', 'Terça', 'Segunda', 'Domingo'][k]}, {28 - k} de ago", rows))
            return out, total

        h, w = 3000, 738
        seam = tile_tops(h, w)[1]
        b, total = blocks()
        # 1º bloco: cabeçalho (80) + linha (108+60) = 248 px; o 2º cabeçalho fica 4 px abaixo do topo do pedaço 2
        png = render_screenshot(b, height=h, top=seam + 4 - 248)
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([png], 2026, 9, None, total, AliasStore(Path(tmp) / "a.json"))
        self.assertEqual(len(res.rows), 8, [(r["data"], r["valor"]) for r in res.rows])
        self.assertTrue(res.stats["reconciliation"]["ok"], res.stats)
        self.assertEqual(sum(r["data"] == "27/08/2026" for r in res.rows), 3)
        self.assertFalse([r for r in res.rows if r["revisar"]])

    def test_low_resolution_image_is_flagged(self):
        from fatura_ocr.aliases import AliasStore
        from fatura_ocr.pipeline import process_images
        small = render_screenshot([("Sexta, 14 de ago", [("Outros", "-R$ 1,00", "LOJA", "")])], width=300, height=650)
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([small], 2026, 9, None, None, AliasStore(Path(tmp) / "a.json"))
        self.assertTrue(any("resolução baixa" in w for w in res.warnings), res.warnings)

    def test_tall_scrolled_screenshot_is_read_in_pieces(self):
        """Captura "rolada" (uma imagem bem alta): lida em pedaços sobrepostos, sem duplicar nem perder."""
        from fatura_ocr.aliases import AliasStore
        from fatura_ocr.ocr import tile_tops
        from fatura_ocr.pipeline import process_images

        days = ["Sexta, 28 de ago", "Quinta, 27 de ago", "Quarta, 26 de ago", "Terça, 25 de ago",
                "Segunda, 24 de ago", "Domingo, 23 de ago", "Sábado, 22 de ago", "Sexta, 21 de ago"]
        blocks, total = [], 0
        for k, day in enumerate(days):
            rows = []
            for j in range(2 if k % 2 == 0 else 1):  # dias com duas compras: a 2ª fica sem cabeçalho logo acima
                cents = 1000 + 111 * (k * 2 + j)
                total += cents
                rows.append(("Compras", f"-R$ {cents // 100},{cents % 100:02d}", f"LOJA FICTICIA {k}{j}", ""))
            blocks.append((day, rows))
        png = render_screenshot(blocks, height=3700)
        self.assertGreater(len(tile_tops(3700, 738)), 2)  # foi mesmo dividida em pedaços
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([png], 2026, 9, None, total, AliasStore(Path(tmp) / "a.json"),
                                 progress=lambda i, st, **kw: events.append((st, kw.get("frac"))))
        self.assertEqual(len(res.rows), 12, [(r["data"], r["valor"]) for r in res.rows])
        self.assertTrue(res.stats["reconciliation"]["ok"], res.stats)
        self.assertEqual(res.stats["images"], 1)
        self.assertEqual(sorted({r["data"] for r in res.rows}), sorted(f"{d}/08/2026" for d in range(21, 29)))
        self.assertFalse(any(r["revisar"] for r in res.rows))
        fracs = [f for st, f in events if st == "part"]
        self.assertEqual((fracs[0], fracs[-1]), (0, 1))  # progresso por pedaço, do 0 ao fim


if __name__ == "__main__":
    unittest.main()
