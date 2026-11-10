// Testa a leitura do progresso em tempo real (static/stream.js). Rodado por scripts/verify.sh com node.
const assert = require("assert");
const { readEvents, LOST } = require("../../src/fatura_ocr/static/stream.js");
const enc = new TextEncoder();
function streamOf(chunks) { // ReadableStream que entrega os bytes nos pedaços dados (pode partir caracteres)
  return new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(x)); c.close(); } });
}
function bytes(text, cuts) { const b = enc.encode(text); const out = []; let at = 0; for (const c of cuts) { out.push(b.slice(at, c)); at = c; } out.push(b.slice(at)); return out; }
function failing(chunks) {
  return new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(x)); }, pull(c) { c.error(new TypeError("network error")); } });
}

(async () => {
  // eventos em ordem, linha e "ç" partidos entre pedaços
  const text = '{"event":"image","index":0,"state":"start"}\n{"event":"image","index":0,"state":"done"}\n' +
               '{"event":"result","rows":[{"lancamento":"AÇAÍ"}],"filename":"fatura-inter-2026-09.csv"}\n';
  const cut = enc.encode(text).indexOf(0xc3) + 1; // no meio do "Ç"
  const seen = [];
  const res = await readEvents(streamOf(bytes(text, [17, 60, cut])), (e) => seen.push(`${e.index}:${e.state}`));
  assert.deepStrictEqual(seen, ["0:start", "0:done"]);
  assert.strictEqual(res.rows[0].lancamento, "AÇAÍ");
  assert.strictEqual(res.filename, "fatura-inter-2026-09.csv");

  // erro do servidor: mensagem dele
  await assert.rejects(readEvents(streamOf([enc.encode('{"event":"error","detail":"Imagem 2: ilegível"}\n')]), () => {}),
    { message: "Imagem 2: ilegível" });
  // conexão caiu no meio / linha cortada / acabou sem resultado: mensagem em português
  await assert.rejects(readEvents(failing([enc.encode('{"event":"image","index":0,"state":"start"}\n')]), () => {}), { message: LOST });
  await assert.rejects(readEvents(streamOf([enc.encode('{"event":"image","ind')]), () => {}), { message: LOST });
  await assert.rejects(readEvents(streamOf([enc.encode('{"event":"image","index":0,"state":"start"}\n')]), () => {}), { message: LOST });
  console.log("stream.js: 5 casos OK");
})().catch((e) => { console.error(e); process.exit(1); });
