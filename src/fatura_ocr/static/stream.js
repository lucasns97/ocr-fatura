// Leitura do progresso em tempo real: /api/process?stream=1 manda uma linha JSON por evento.
// Separado de app.js para ter teste automático (tests/js/stream.test.js).
(function (root) {
  "use strict";
  const LOST = "A conexão com o programa caiu no meio da leitura. Verifique se a janela do Fatura OCR ainda está aberta e tente de novo.";

  // body: ReadableStream de bytes. Eventos "image" vão para onEvent na hora; devolve o evento "result".
  // Erro do servidor ("error") vira exceção com a mensagem dele; qualquer outra falha vira LOST (em português).
  async function readEvents(body, onEvent) {
    const reader = body.getReader(), dec = new TextDecoder();
    let buf = "", result = null;
    const handle = (line) => {
      if (!line.trim()) return;
      const ev = JSON.parse(line);
      if (ev.event === "image") onEvent(ev);
      else if (ev.event === "result") result = ev;
      else if (ev.event === "error") throw Object.assign(new Error(ev.detail || "Erro inesperado."), { fromServer: true });
    };
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true }); // caractere de vários bytes pode vir partido entre pedaços
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) { handle(buf.slice(0, nl)); buf = buf.slice(nl + 1); }
      }
      handle(buf + dec.decode());
    } catch (e) {
      if (e.fromServer) throw e;
      throw new Error(LOST);
    }
    if (!result) throw new Error(LOST);
    return result;
  }

  const api = { readEvents, LOST };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FaturaStream = api;
})(typeof window !== "undefined" ? window : globalThis);
