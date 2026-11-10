import unittest

from fatura_ocr import csvio
from fatura_ocr.money import format_money, ocr_money, parse_user_money


class Money(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_money(123456), "R$ 1.234,56")
        self.assertEqual(format_money(5), "R$ 0,05")
        self.assertEqual(format_money(-200000), "-R$ 2.000,00")

    def test_ocr_money_tolerates_misread_separators(self):
        self.assertEqual(ocr_money("-R$ 129,90"), 12990)
        self.assertEqual(ocr_money("-R$129.90"), 12990)       # vírgula lida como ponto
        self.assertEqual(ocr_money("+R$2.000.00"), -200000)   # crédito: sinal oposto
        self.assertEqual(ocr_money("R$ 12,34"), 1234)         # sinal perdido: compra

    def test_parse_user_money(self):
        cases = {"R$ 1.234,56": 123456, "1234,5": 123450, "12": 1200, "12.50": 1250, "-R$ 2.000,00": -200000,
                 "R$ -4,20": -420, "(12,50)": -1250, "1.234": 123400, " 0,99 ": 99}
        for text, cents in cases.items():
            self.assertEqual(parse_user_money(text), cents, text)
        # mesmos casos positivos do parser do navegador (static/money.js, tests/js/money.test.js)
        for text, cents in {"1.896,14": 189614, "1896,14": 189614, "R$ 1.896,14": 189614, "1896.14": 189614,
                            "1,896.14": 189614, "1896": 189600, "R$ 999.999.999,99": 99999999999}.items():
            self.assertEqual(parse_user_money(text), cents, text)
        for bad in ("", "abc", "R$"):
            with self.assertRaises(ValueError):
                parse_user_money(bad)


class Csv(unittest.TestCase):
    ROW = {"data": "05/11/2026", "lancamento": "TAXI EXEMPLO * TRIP", "categoria": "transporte",
           "tipo": "Compra à vista", "valor": "45,67"}

    def test_filename(self):
        self.assertEqual(csvio.filename(2026, 10), "fatura-inter-2026-10.csv")
        self.assertEqual(csvio.filename(2026, 1), "fatura-inter-2026-01.csv")

    def test_normalize_and_csv(self):
        rows, errors = csvio.normalize_rows([self.ROW])
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["valor"], "R$ 45,67")
        self.assertEqual(rows[0]["categoria"], "TRANSPORTE")
        text = csvio.to_csv(rows)
        self.assertEqual(text.splitlines()[0], "Data;Lançamento;Categoria;Tipo;Valor")
        self.assertEqual(text.splitlines()[1], "05/11/2026;TAXI EXEMPLO * TRIP;TRANSPORTE;Compra à vista;R$ 45,67")
        self.assertTrue(csvio.to_csv(rows, "comma", bom=True).startswith("﻿Data,"))
        self.assertIn('"R$ 45,67"', csvio.to_csv(rows, "comma"))  # vírgula no valor é citada

    def test_invalid_rows_are_reported(self):
        _, errors = csvio.normalize_rows([dict(self.ROW, data="31/02/2026"), dict(self.ROW, valor="xx")])
        self.assertEqual([e["index"] for e in errors], [0, 1])
        self.assertIn("Data", errors[0]["message"])
        self.assertIn("Valor", errors[1]["message"])


if __name__ == "__main__":
    unittest.main()
