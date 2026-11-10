// Valores em reais digitados/colados pelo usuário, no navegador.
// Mesma regra de money.py (parse_user_money) para valores positivos; tests/js/money.test.js confere.
(function (root) {
  "use strict";
  const MAX_CENTS = 99999999999; // R$ 999.999.999,99

  // Texto colado -> centavos (inteiro), ou null se não for um valor positivo plausível.
  // Vírgula ou ponto seguido de 1-2 dígitos no fim = centavos; senão, reais inteiros.
  function parsePasted(text) {
    const s = String(text).trim();
    if (/^[(\-−–]|^R\$\s*[-−–]/.test(s)) return null; // negativo: o total nunca é
    const core = s.replace(/[^\d.,]/g, "");
    if (!/\d/.test(core)) return null;
    const m = core.match(/[.,](\d{1,2})$/);
    const whole = (m ? core.slice(0, m.index) : core).replace(/\D/g, "") || "0";
    const cents = Number(whole) * 100 + (m ? Number(m[1].padEnd(2, "0")) : 0);
    return cents > MAX_CENTS ? null : cents; // número enorme = texto com outras coisas (datas etc.)
  }

  const api = { MAX_CENTS, parsePasted };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FaturaMoney = api;
})(typeof window !== "undefined" ? window : globalThis);
