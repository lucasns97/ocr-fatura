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


if __name__ == "__main__":
    unittest.main()
