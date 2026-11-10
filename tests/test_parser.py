"""Dados fictícios (o repositório é público): estabelecimentos e valores inventados."""
import unittest

from fatura_ocr.parser import UNSURE_CONF, OcrLine, group_lines, parse_screen, restore_category

from helpers import H, screen, tx


class Parser(unittest.TestCase):
    def test_basic_layout(self):
        lines = screen(*tx("Domingo, 23 de ago", "Pagamentos", "-R$ 12,34", "STREAMING ABC SAO PAULO BRA"),
                       *tx("Sábado, 22 de ago", "Entretenimento", "-R$129.90", "ACADEMIA EXEMPLO SAO PAULO"), "BRA")
        rows = parse_screen(lines, H).rows
        self.assertEqual([(r.day, r.month, r.category, r.amount) for r in rows],
                         [(23, 8, "PAGAMENTOS", 1234), (22, 8, "ENTRETENIMENTO", 12990)])
        self.assertEqual(rows[1].merchant, "ACADEMIA EXEMPLO SAO PAULO BRA")  # nome em 2 linhas

    def test_same_date_multiple_rows_installments_and_credit(self):
        lines = screen(*tx("Domingo, 2 de ago", "Transporte", "-R$ 15,00", "TAXI EXEMPLO Sao Paulo BRA"),
                       *tx("", "Outros", "+R$ 2.000,00", "PAGAMENTO ON LINE"),
                       *tx("Segunda,15dejun", "Viagem", "-R$ 200,00", "HOTEL FICTICIO", "Parcela3de6"))
        rows = parse_screen(lines, H).rows
        self.assertEqual(len(rows), 3)
        self.assertEqual((rows[1].day, rows[1].amount, rows[1].merchant), (2, -200000, "PAGAMENTO ON LINE"))
        self.assertEqual((rows[2].month, rows[2].installment, rows[2].merchant), (6, "3/6", "HOTEL FICTICIO"))
        self.assertTrue(all(r.conf > UNSURE_CONF for r in rows))

    def test_ignores_status_bar_nav_bar_and_summary_card(self):
        lines = [OcrLine(40, "16:18", .9), OcrLine(120, "Faturas", .9),
                 OcrLine(330, "Setembro Paga", .9), OcrLine(380, "R$ 1.234,56", .9),
                 OcrLine(480, "Dia de vencimento 07/09", .9)]
        lines += screen(*tx("Quinta, 20 de ago", "Outros", "-R$ 4,20", "IOF INTERNACIONAL"), start=860)
        lines += [OcrLine(1555, "III O <", .5)]
        res = parse_screen(lines, H)
        self.assertEqual(len(res.rows), 1)
        self.assertEqual(res.card_month, 9)
        self.assertEqual(res.rows[0].merchant, "IOF INTERNACIONAL")
        self.assertEqual(res.last_date, (20, 8))

    def test_rows_above_first_header_use_previous_screenshot_date(self):
        # o cabeçalho de data rolou para fora da tela: a data vem da captura anterior
        lines = screen("Outros", "-R$ 10,00", "LOJA A", *tx("Segunda, 10 de ago", "Outros", "-R$ 20,00", "LOJA B"))
        self.assertEqual([r.amount for r in parse_screen(lines, H).rows], [2000])   # sem data anterior: ignora
        rows = parse_screen(lines, H, start_date=(12, 8)).rows
        self.assertEqual([(r.day, r.amount) for r in rows], [(12, 1000), (10, 2000)])
        self.assertLessEqual(rows[0].conf, UNSURE_CONF)   # data deduzida: marcada para revisar
        self.assertGreater(rows[1].conf, UNSURE_CONF)

    def test_missing_sign_is_flagged(self):
        rows = parse_screen(screen(*tx("Quinta, 20 de ago", "Outros", "R$ 500,00", "LOJA C")), H).rows
        self.assertEqual(rows[0].amount, 50000)                # lido como compra...
        self.assertLessEqual(rows[0].conf, UNSURE_CONF)        # ...mas pode ser pagamento: revisar

    def test_missing_category_is_blank_not_the_date(self):
        lines = screen("Quarta, 19 de ago", "-R$ 99,00", "SERVICO NUVEM XYZ")
        self.assertEqual(parse_screen(lines, H).rows[0].category, "")

    def test_category_accents_restored(self):
        self.assertEqual(restore_category("Servicos"), "SERVIÇOS")
        self.assertEqual(restore_category("Categoria Nova"), "CATEGORIA NOVA")

    def test_group_lines_merges_boxes_on_same_row(self):
        boxes = [(300, 400, "SAO PAULO", .9), (302, 186, "TAXI EXEMPLO", .8), (340, 186, "Parcela 1 de 2", .9)]
        out = group_lines(boxes, H)
        self.assertEqual([ln.text for ln in out], ["TAXI EXEMPLO SAO PAULO", "Parcela 1 de 2"])
        self.assertEqual(out[0].conf, .8)


if __name__ == "__main__":
    unittest.main()
