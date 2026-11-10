"""Dados fictícios (o repositório é público): estabelecimentos e valores inventados."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fatura_ocr.aliases import AliasStore
from fatura_ocr.parser import RawRow
from fatura_ocr.pipeline import default_closing, infer_date, merge_screens, process_images, reconcile

from helpers import H, screen, tx


def R(day, month, amount, merchant, inst="", cat="OUTROS", conf=.9):
    return RawRow(day, month, cat, amount, merchant, inst, conf)


class Dates(unittest.TestCase):
    def test_default_closing(self):
        self.assertEqual(default_closing(2026, 9), date(2026, 8, 31))
        self.assertEqual(default_closing(2026, 1), date(2025, 12, 31))
        self.assertEqual(default_closing(2024, 3), date(2024, 2, 29))

    def test_year_inference(self):
        c = date(2026, 8, 31)
        self.assertEqual(infer_date(23, 8, c), date(2026, 8, 23))
        self.assertEqual(infer_date(23, 3, c, "6/6"), date(2026, 3, 23))
        self.assertEqual(infer_date(24, 9, c, "12/12"), date(2025, 9, 24))   # parcela antiga: ano anterior
        self.assertEqual(infer_date(15, 8, c, "12/12"), date(2025, 8, 15))   # parcela 12: compra ~11 meses antes
        self.assertEqual(infer_date(15, 8, c), date(2026, 8, 15))
        self.assertEqual(infer_date(29, 2, c), date(2024, 2, 29))            # ano bissexto mais próximo

    def test_closing_a_few_days_later_than_default(self):
        # fechamento real no começo do mês do vencimento: não vira compra do ano passado
        self.assertEqual(infer_date(3, 9, date(2026, 8, 31)), date(2026, 9, 3))


class Merge(unittest.TestCase):
    def test_overlap_removed_and_fuller_reading_kept(self):
        a = [R(16, 8, 1500, "TAXI EXEMPLO"), R(14, 8, 2500, "TAXIEXEMPLO"), R(14, 8, 8000, "PET SHOP FICTICIO SAO PAULO")]
        b = [R(14, 8, 2500, "TAXI EXEMPLO Sao Paulo BRA"), R(14, 8, 8000, "PET SHOP FICTICIO SAO PAULO BRA"),
             R(10, 8, 7000, "OPERADORA TEL")]
        rows, removed = merge_screens([a, b])
        self.assertEqual(removed, [2])
        self.assertEqual([r.amount for r in rows], [1500, 2500, 8000, 7000])
        self.assertTrue(rows[2].merchant.endswith("BRA"))  # versão truncada substituída pela completa

    def test_edge_row_without_merchant_or_installment_still_matches(self):
        a = [R(8, 6, 30000, "INGRESSOS SHOW"), R(23, 3, 25000, "")]           # nome cortado na borda
        b = [R(23, 3, 25000, "HOTEL FICTICIO", "6/6"), R(24, 9, 5000, "CURSO ONLINE", "12/12")]
        rows, removed = merge_screens([a, b])
        self.assertEqual(removed, [1])
        self.assertEqual(len(rows), 3)
        self.assertEqual((rows[1].merchant, rows[1].installment), ("HOTEL FICTICIO", "6/6"))

    def test_identical_legit_purchases_are_kept(self):
        a = [R(10, 8, 7000, "OPERADORA TEL"), R(10, 8, 9000, "OPERADORA TEL")]
        b = [R(9, 8, 2000, "TAXI"), R(9, 8, 2000, "TAXI")]   # duas corridas iguais, sem sobreposição
        rows, removed = merge_screens([a, b])
        self.assertEqual((len(rows), removed), (4, [0]))

    def test_repeated_purchase_across_the_seam(self):
        a = [R(9, 8, 2000, "TAXI"), R(9, 8, 2000, "TAXI")]
        b = [R(9, 8, 2000, "TAXI"), R(8, 8, 500, "PADARIA")]   # só a última de `a` reaparece em `b`
        rows, _ = merge_screens([a, b])
        self.assertEqual([r.amount for r in rows], [2000, 2000, 500])


class Aliases(unittest.TestCase):
    def test_only_ocr_lookalikes_are_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            al = AliasStore(Path(tmp) / "a.json")
            names = al.canonicalise([("LOJA FICTICIA FlOOV", .9), ("LOJAFICTICIA FIOOV", .8),      # l/I: mesmo lugar
                                     ("FARMACIA 1234 CENTRO", .9), ("FARMACIA 1235 CENTRO", .9),  # filiais diferentes
                                     ("RESTAURANTE BOM", .9), ("RESTAURANTES BOM", .9)])
            self.assertEqual(names[0], names[1])
            self.assertEqual(len({names[2], names[3]}), 2)
            self.assertEqual(len({names[4], names[5]}), 2)


class Reconcile(unittest.TestCase):
    def test_reconcile(self):
        rows = [{"valor_centavos": 1000}, {"valor_centavos": 500}, {"valor_centavos": -200}]
        self.assertTrue(reconcile(rows, 1500)["ok"])
        self.assertTrue(reconcile(rows, 1300)["ok"])   # líquido
        self.assertEqual(reconcile(rows, 1600)["diff"], 100)
        self.assertIsNone(reconcile(rows, None))


class Process(unittest.TestCase):
    def test_end_to_end_with_fake_ocr(self):
        s1 = screen(*tx("Domingo, 23 de ago", "Pagamentos", "-R$ 12,34", "STREAMING ABC"),
                    *tx("Quinta, 20 de ago", "Outros", "-R$ 4,20", "IOFINTERNACIONAL"))
        s2 = screen(*tx("Quinta, 20 de ago", "Outros", "-R$ 4,20", "IOF INTERNACIONAL"),
                    *tx("Quarta, 24 de set", "Ensino", "-R$ 50,00", "CURSO ONLINE", "Parcela 12 de 12"))
        fake = {b"1": (s1, H), b"2": (s2, H)}
        with tempfile.TemporaryDirectory() as tmp:
            aliases = AliasStore(Path(tmp) / "a.json")
            res = process_images([b"1", b"2"], 2026, 9, None, 6654, aliases, read_lines=fake.__getitem__)
            self.assertEqual(res.stats["duplicates_removed"], 1)
            self.assertEqual([r["data"] for r in res.rows], ["23/08/2026", "20/08/2026", "24/09/2025"])
            self.assertEqual(res.rows[2]["tipo"], "Parcela 12 de 12")
            self.assertTrue(res.stats["reconciliation"]["ok"])
            self.assertTrue((Path(tmp) / "a.json").exists())
            # mesmo estabelecimento, outra grafia, outro mês: sai com o nome já salvo
            s3 = screen(*tx("Terça, 1 de set", "Outros", "-R$ 1,00", "IOF INTERNACIONAL"))
            res2 = process_images([b"3"], 2026, 10, None, None, aliases, read_lines=lambda _: (s3, H))
            self.assertEqual(res2.rows[0]["lancamento"], "IOFINTERNACIONAL")

    def test_date_carries_over_when_header_scrolled_off(self):
        s1 = screen(*tx("Sexta, 14 de ago", "Outros", "-R$ 1,00", "LOJA A"), *tx("", "Outros", "-R$ 2,00", "LOJA B"))
        s2 = screen("Outros", "-R$ 3,00", "LOJA C", *tx("Quinta, 13 de ago", "Outros", "-R$ 4,00", "LOJA D"))
        fake = {b"1": (s1, H), b"2": (s2, H)}
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([b"1", b"2"], 2026, 9, None, None, AliasStore(Path(tmp) / "a.json"),
                                 read_lines=fake.__getitem__)
        self.assertEqual([(r["data"], r["valor"]) for r in res.rows],
                         [("14/08/2026", "R$ 1,00"), ("14/08/2026", "R$ 2,00"), ("14/08/2026", "R$ 3,00"),
                          ("13/08/2026", "R$ 4,00")])
        self.assertTrue(res.rows[2]["revisar"])

    def test_warnings_month_mismatch_and_after_closing(self):
        s = [*screen("Setembro Paga", start=330)] + screen(*tx("Quinta, 3 de set", "Outros", "-R$ 4,20", "IOF"), start=860)
        with tempfile.TemporaryDirectory() as tmp:
            res = process_images([b"x"], 2026, 10, None, None, AliasStore(Path(tmp) / "a.json"), read_lines=lambda _: (s, H))
        self.assertTrue(any("Setembro" in w for w in res.warnings))
        res2 = None
        with tempfile.TemporaryDirectory() as tmp:
            res2 = process_images([b"x"], 2026, 9, None, None, AliasStore(Path(tmp) / "a.json"), read_lines=lambda _: (s, H))
        self.assertEqual(res2.rows[0]["data"], "03/09/2026")
        self.assertTrue(any("depois do fechamento" in w for w in res2.warnings))


if __name__ == "__main__":
    unittest.main()
