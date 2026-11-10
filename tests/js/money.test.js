// Testa o parser de valores colados (static/money.js). Rodado por scripts/verify.sh com node.
const assert = require("assert");
const { parsePasted, MAX_CENTS } = require("../../src/fatura_ocr/static/money.js");
const cases = [
  ["1.896,14", 189614], ["1896,14", 189614], ["R$ 1.896,14", 189614], ["1896.14", 189614], ["1,896.14", 189614],
  ["1896", 189600], ["1.234", 123400], ["0,5", 50], ["0,001", 100], [" R$ 12,34 ", 1234], ["R$ 999.999.999,99", MAX_CENTS],
  ["-1.896,14", null], ["(1.896,14)", null], ["R$ -3,00", null], ["abc", null], ["", null],
  ["Vence 10/12/2026 R$ 1.896,14", null], ["1.000.000.000,00", null],
];
for (const [text, want] of cases) assert.strictEqual(parsePasted(text), want, JSON.stringify(text));
console.log(`money.js: ${cases.length} casos OK`);
