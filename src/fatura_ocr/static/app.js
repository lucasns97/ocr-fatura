"use strict";
const $ = (s, r = document) => r.querySelector(s);
const TOKEN = document.body.dataset.token;
const MONTHS = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
const FIELDS = ["data", "lancamento", "categoria", "tipo", "valor"];

const S = { files: [], original: [], rows: [], draft: [], edited: false, meta: null, nextId: 1e6 };

/* ---------- helpers ---------- */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (c) => (c < 0 ? "-" : "") + "R$ " + Math.floor(Math.abs(c) / 100).toLocaleString("pt-BR") + "," + String(Math.abs(c) % 100).padStart(2, "0");
const clone = (o) => JSON.parse(JSON.stringify(o));
let toastTimer;
function toast(msg, ms = 4500) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), ms);
}
async function api(path, body, isForm) {
  const res = await fetch(path, { method: "POST", headers: isForm ? { "X-Token": TOKEN } : { "X-Token": TOKEN, "Content-Type": "application/json" }, body: isForm ? body : JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(typeof data.detail === "string" ? data.detail : "Erro inesperado."); e.status = res.status; throw e; }
  return data;
}
const meta = () => ({ ano: +$("#ano").value, mes: +$("#mes").value });
// depois de ler, o mês que vale é o usado na leitura (as datas foram calculadas com ele)
const usedMeta = () => (S.meta ? { ano: S.meta.ano, mes: S.meta.mes } : meta());
const filename = () => { const m = usedMeta(); return `fatura-inter-${String(m.ano).padStart(4, "0")}-${String(m.mes).padStart(2, "0")}.csv`; };

/* ---------- step 1: form ---------- */
(function initForm() {
  const sel = $("#mes");
  MONTHS.forEach((m, i) => sel.append(new Option(m, i + 1)));
  // padrão (definido pelo servidor): a fatura em aberto, que vence no mês seguinte
  sel.value = document.body.dataset.month; $("#ano").value = document.body.dataset.year;
})();

/* Total da fatura: máscara de moeda. Digitando, cada dígito entra pela direita (R$ 0,01 -> R$ 0,18 ->
   ... -> R$ 1.896,14); apagar tira o último. Colando, o texto é lido como valor ("1.896,14", "1896,14",
   "R$ 1.896,14" e "1896" viram R$ 1.896,14 / R$ 1.896,00). */
const totalEl = $("#total");
const { parsePasted } = window.FaturaMoney; // static/money.js (testado em tests/js/money.test.js)
function setTotal(cents) {
  totalEl.value = cents > 0 ? fmt(cents) : "";
  totalEl.setSelectionRange(totalEl.value.length, totalEl.value.length); // cursor sempre no fim
}
function pasteValue(text) { // valor inteiro de uma vez: interpreta; se não fizer sentido, mantém o atual
  const c = parsePasted(text);
  if (c === null) toast("Isso não parece um valor. Digite só os números (ex.: 189614 para R$ 1.896,14).", 5000);
  else setTotal(c);
}
totalEl.addEventListener("paste", (e) => { e.preventDefault(); pasteValue((e.clipboardData || window.clipboardData).getData("text")); });
totalEl.addEventListener("drop", (e) => { e.preventDefault(); totalEl.focus(); pasteValue(e.dataTransfer.getData("text")); });
// Só dígitos podem ser digitados: vírgula, ponto e "R$" são colocados automaticamente.
// Teclados de celular e preenchimento automático podem inserir um valor inteiro sem "colar": tratamos igual.
totalEl.addEventListener("beforeinput", (e) => {
  if (e.inputType !== "insertText" && e.inputType !== "insertReplacementText") return;
  const data = e.data ?? (e.dataTransfer && e.dataTransfer.getData("text/plain"));
  if (data && data.length > 1) { e.preventDefault(); pasteValue(data); return; }
  if (data && /\D/.test(data)) e.preventDefault();
});
function reformat() {
  const digits = totalEl.value.replace(/\D/g, "").replace(/^0+/, "").slice(0, 11);
  setTotal(digits ? Number(digits) : 0);
}
totalEl.addEventListener("input", (e) => { if (!e.isComposing) reformat(); }); // não mexer durante composição (IME)
totalEl.addEventListener("compositionend", reformat);
totalEl.addEventListener("focus", () => setTimeout(() => totalEl.setSelectionRange(totalEl.value.length, totalEl.value.length), 0));

/* ---------- step 2: files ---------- */
const drop = $("#drop"), input = $("#file");
drop.addEventListener("click", () => { if (!S.busy) input.click(); });
drop.addEventListener("keydown", (e) => { if (S.busy) return; if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { if (!S.busy) addFiles(e.dataTransfer.files); });
input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });

function addFiles(list) {
  const imgs = [...list].filter((f) => f.type.startsWith("image/"));
  if (imgs.length < list.length) toast("Arquivos que não são imagem foram ignorados.");
  // ordem natural pelo nome (capturas do celular têm data/hora no nome)
  // ordem natural pelo nome SEM a extensão: o WhatsApp numera repetidas como "X.jpeg", "X 2.jpeg",
  // "X 3.jpeg"; comparando com a extensão, "X 2" vinha antes de "X" (a primeira captura)
  const stem = (n) => n.replace(/\.[^.]+$/, "");
  imgs.sort((a, b) => stem(a.name).localeCompare(stem(b.name), undefined, { numeric: true }) || a.name.localeCompare(b.name));
  const same = (a, b) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;
  let dup = 0;
  imgs.forEach((f) => { if (S.files.some((x) => same(x.file, f))) dup += 1; else S.files.push({ file: f, url: URL.createObjectURL(f) }); });
  if (dup) toast(`${dup} captura(s) já estava(m) na lista e não foi(ram) adicionada(s) de novo.`);
  renderFiles();
}
function renderFiles() {
  const ol = $("#files"); ol.innerHTML = "";
  S.files.forEach((f, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<img alt=""><span class="nm"><span class="t"></span></span><span class="ctl"><button title="Subir" aria-label="Mover para cima">↑</button><button title="Descer" aria-label="Mover para baixo">↓</button><button title="Remover" aria-label="Remover">✕</button></span>`;
    $("img", li).src = f.url; $(".nm .t", li).textContent = `${i + 1}. ${f.file.name}`;
    const [up, down, rm] = li.querySelectorAll("button");
    up.disabled = i === 0; down.disabled = i === S.files.length - 1;
    up.onclick = () => { [S.files[i - 1], S.files[i]] = [S.files[i], S.files[i - 1]]; renderFiles(); };
    down.onclick = () => { [S.files[i + 1], S.files[i]] = [S.files[i], S.files[i + 1]]; renderFiles(); };
    rm.onclick = () => { URL.revokeObjectURL(f.url); S.files.splice(i, 1); renderFiles(); };
    ol.append(li);
  });
  $("#go").disabled = S.busy || S.files.length === 0;
  if (S.meta) $("#sum-files").textContent = S.files.length === S.readCount
    ? `${S.readCount} captura(s) lida(s) · clique para trocar ou ler de novo`
    : `${S.files.length} captura(s) · a lista mudou, clique em Ler capturas`;
}

$("#go").addEventListener("click", async () => {
  if (S.busy) return;
  if (S.meta && (S.edited || diffCount(S.rows, S.draft)) && !confirm("Ler de novo descarta suas edições. Continuar?")) return;
  const btn = $("#go"), status = $("#status");
  btn.disabled = true; status.textContent = "Lendo as capturas… (cerca de 1 s por imagem)";
  const fd = new FormData();
  const m = meta(); fd.append("ano", m.ano); fd.append("mes", m.mes);
  fd.append("fechamento", $("#fechamento").value); fd.append("total", $("#total").value);
  S.files.forEach((f) => fd.append("files", f.file, f.file.name));
  const progress = startProgress();
  try {
    const r = await processStream(fd, progress.event); // eventos reais de cada captura + resultado
    progress.finish(true);
    S.meta = { ...m, stats: r.stats };
    S.original = clone(r.rows); S.rows = clone(r.rows); S.draft = clone(r.rows); S.edited = false;
    showResults(r);
    status.textContent = "";
  } catch (e) { progress.finish(false); status.textContent = ""; toast(e.message, 8000); }
  btn.disabled = S.files.length === 0;
});

/* /api/process?stream=1: eventos de cada captura em tempo real (leitura em static/stream.js, testada). */
async function processStream(fd, onEvent) {
  let res;
  try { res = await fetch("/api/process?stream=1", { method: "POST", headers: { "X-Token": TOKEN }, body: fd }); }
  catch { throw new Error(window.FaturaStream.LOST); }
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(typeof d.detail === "string" ? d.detail : "Erro inesperado."); }
  return window.FaturaStream.readEvents(res.body, onEvent);
}

/* Progresso da leitura, guiado pelos eventos reais do servidor (ele lê uma captura por vez):
   - "start": o cartão começa a encher, pelo tempo médio por imagem, e para em 95% se demorar mais;
   - "done": o fundo vai a 100% e o contorno + ✓ aparecem juntos (pula do meio para o fim, se preciso);
   - "part": captura rolada lida em pedaços; cada pedaço lido avança a barra de verdade (frac);
   - "skipped": captura igual a uma anterior, marcada como ignorada.
   O tempo médio é aprendido com as durações reais e guardado para a próxima leitura. */
const MS_KEY = "fatura-ocr:ms-por-imagem";
function msPerImage() {
  try { const v = Number(localStorage.getItem(MS_KEY)); return v > 200 && v < 20000 ? v : 1500; } catch { return 1500; }
}
function startProgress() {
  const ol = $("#files"), lis = [...ol.children], n = lis.length, status = $("#status");
  let per = msPerImage();
  // por cartão em leitura: t0 (início do trecho atual), base (fração já confirmada pelo servidor),
  // span (quanto o trecho atual vale), parts (pedaços de uma captura rolada), first (início real), shown
  const started = new Map(), durations = [];
  // trava a lista de verdade (mouse e teclado) enquanto lê
  S.busy = true;
  const btns = [...ol.querySelectorAll("button")], prev = btns.map((b) => b.disabled);
  btns.forEach((b) => { b.disabled = true; });
  ol.classList.add("busy"); drop.classList.add("busy"); drop.setAttribute("aria-disabled", "true");
  lis.forEach((li) => { li.classList.remove("done", "skipped", "reading"); li.style.setProperty("--p", "0%"); });
  const tick = () => {
    const now = performance.now();
    started.forEach((c, i) => {
      // estimativa dentro do trecho atual, sem passar de 95% e sem nunca voltar
      c.shown = Math.max(c.shown, Math.min(0.95, c.base + c.span * Math.min(1, (now - c.t0) / per)));
      lis[i].style.setProperty("--p", (c.shown * 100).toFixed(1) + "%");
    });
  };
  const timer = setInterval(tick, 80);
  const finished = () => lis.filter((li) => li.classList.contains("done") || li.classList.contains("skipped")).length;
  return {
    event({ index: i, state, frac = 0, parts = 0 }) {
      const li = lis[i]; if (!li) return;
      if (state === "start") {
        const now = performance.now();
        started.set(i, { t0: now, first: now, base: 0, span: 1, parts: 1, shown: 0 }); li.classList.add("reading");
        status.textContent = `Lendo captura ${i + 1} de ${n}…`;
      } else if (state === "part") { // captura rolada: o servidor confirmou mais um pedaço lido
        const c = started.get(i); if (!c) return;
        c.parts = parts || 1; c.base = Math.max(c.base, frac); c.span = 1 / c.parts; c.t0 = performance.now();
        c.shown = Math.max(c.shown, Math.min(0.95, c.base));
      } else {
        const c = started.get(i);
        if (state === "done" && c) { // tempo por "tela": uma captura rolada conta como seus pedaços
          durations.push((performance.now() - c.first) / c.parts); per = durations.reduce((a, b) => a + b, 0) / durations.length;
        }
        started.delete(i); li.classList.remove("reading");
        li.style.setProperty("--p", "100%"); li.classList.add(state === "skipped" ? "skipped" : "done");
        if (finished() === n) status.textContent = "Montando a tabela…";
      }
    },
    finish(ok) {
      clearInterval(timer);
      S.busy = false; btns.forEach((b, i) => { b.disabled = prev[i]; });
      ol.classList.remove("busy"); drop.classList.remove("busy"); drop.removeAttribute("aria-disabled");
      if (ok && durations.length) {
        try { localStorage.setItem(MS_KEY, String(Math.round(per))); } catch { /* sem armazenamento: usa o padrão */ }
      }
      if (!ok) lis.forEach((li) => { li.classList.remove("done", "skipped", "reading"); li.style.setProperty("--p", "0%"); });
    },
  };
}

/* ---------- results ---------- */
function showResults(r) {
  $("#results").hidden = false;
  const w = $("#warnings"); w.innerHTML = "";
  r.warnings.forEach((t) => { const d = document.createElement("div"); d.className = "notice"; d.textContent = t; w.append(d); });
  const st = r.stats;
  const info = document.createElement("div"); info.className = "muted small"; info.style.marginBottom = "10px";
  info.textContent = `${st.rows} transações de ${st.images} captura(s)${st.ignored_images ? ` (${st.ignored_images} igual(is) ignorada(s))` : ""}; ${st.duplicates_removed} repetida(s) por sobreposição removida(s).`;
  w.append(info);
  renderTable(); renderBadge(); renderSummary(); renderRecon(); setTab("tabela");
  collapseSteps();
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* Conferência com o total e linhas a revisar: recalculada a partir da tabela salva (S.rows),
   então some ou muda assim que o usuário corrige e salva. */
// Conferência com o total informado, a partir das linhas salvas (mesma regra de reconcile() no servidor:
// bate se o total for a soma das compras ou o líquido com pagamentos/estornos). Usada na mensagem e no Resumo.
function reconcile(rows) {
  const rec0 = S.meta && S.meta.stats.reconciliation;
  if (!rec0) return null;
  const charges = rows.reduce((s, r) => s + (r.valor_centavos > 0 ? r.valor_centavos : 0), 0);
  const net = rows.reduce((s, r) => s + (r.valor_centavos || 0), 0);
  return { total: rec0.total, charges, net, ok: rec0.total === charges || rec0.total === net, diff: charges - rec0.total };
}
function renderRecon() {
  const el = $("#recon"); el.innerHTML = "";
  const add = (cls, text) => { const d = document.createElement("div"); d.className = "notice" + (cls ? " " + cls : ""); d.textContent = text; el.append(d); };
  const rec = reconcile(S.rows);
  const toReview = S.rows.filter((r) => r.revisar).length;
  const reviewTxt = toReview ? ` ${toReview} linha(s) ainda marcada(s) com "revisar".` : "";
  if (rec) {
    if (rec.ok) add("ok", `✓ A soma bate com o total informado (${fmt(rec.total)}).` + reviewTxt);
    else if (rec.diff > 0) add("", `A soma das compras (${fmt(rec.charges)}) passa do total informado (${fmt(rec.total)}) em ${fmt(rec.diff)}. Provável: um valor lido errado (confira as linhas "revisar"), ou uma transação repetida ou de outra fatura.` + reviewTxt);
    else add("", `A soma das compras (${fmt(rec.charges)}) é menor que o total informado (${fmt(rec.total)}): faltam ${fmt(-rec.diff)}. Provável: falta uma captura, um valor lido errado, ou o fechamento da fatura não é o padrão (Avançado).` + reviewTxt);
  } else if (toReview) add("", `${toReview} linha(s) marcada(s) com "revisar": confira o valor e a data delas.`);
}

/* passos 1 e 2 recolhidos depois da leitura, com um resumo do que foi usado */
function collapseSteps() {
  const m = usedMeta(), total = $("#total").value.trim();
  $("#sum-form").textContent = `${MONTHS[m.mes - 1]}/${m.ano}` + (total ? ` · total ${total}` : "");
  S.readCount = S.files.length;
  $("#sum-files").textContent = `${S.readCount} captura(s) lida(s) · clique para trocar ou ler de novo`;
  $("#step-form").open = false; $("#step-files").open = false;
  // o botão "Ler capturas" sumiu ao recolher: leva o foco do teclado para a tabela
  $('[role=tab][aria-selected="true"]').focus({ preventScroll: true });
}

/* ---------- tabs ---------- */
function setTab(name) {
  document.querySelectorAll("[role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  document.querySelectorAll(".tabpanel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
}
document.querySelectorAll("[role=tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

/* ---------- editable table ---------- */
const rowById = (arr, id) => arr.find((r) => r.id === id);
function cellDirty(i, f) {
  const base = rowById(S.rows, S.draft[i].id);
  return !base || String(base[f]) !== String(S.draft[i][f]);
}
function diffCount(a, b) { // células alteradas + linhas adicionadas/removidas entre dois conjuntos
  let n = 0; const ids = new Set(b.map((r) => r.id));
  a.forEach((r) => { if (!ids.has(r.id)) n += 1; });
  b.forEach((r) => { const o = rowById(a, r.id); if (!o) n += 1; else FIELDS.forEach((f) => { if (String(o[f]) !== String(r[f])) n += 1; }); });
  return n;
}
function renderTable() {
  const tb = $("#grid tbody"); tb.innerHTML = "";
  S.draft.forEach((r, i) => {
    const tr = document.createElement("tr");
    if (r.revisar) tr.className = "review";
    FIELDS.forEach((f) => {
      const td = document.createElement("td"); if (f === "valor") td.className = "num";
      const inp = document.createElement("input"); inp.type = "text"; inp.value = r[f]; inp.dataset.i = i; inp.dataset.f = f;
      inp.setAttribute("aria-label", f + " linha " + (i + 1));
      if (f === "valor" && /^-/.test(r.valor)) inp.classList.add("neg");
      if (cellDirty(i, f)) inp.classList.add("dirty");
      inp.addEventListener("input", () => {
        S.draft[i][f] = inp.value; inp.classList.remove("err");
        inp.classList.toggle("dirty", cellDirty(i, f)); updatePending();
      });
      td.append(inp); tr.append(td);
    });
    const td = document.createElement("td");
    if (r.revisar) {
      const c = document.createElement("button"); c.className = "chip warn"; c.textContent = "revisar";
      c.title = "Leitura incerta (confiança " + Math.round(r.conf * 100) + "%). Clique quando tiver conferido a linha.";
      c.setAttribute("aria-label", "Marcar linha " + (i + 1) + " como conferida");
      c.onclick = () => { // conferida: tira a marca (não altera os dados)
        [S.rows, S.draft, S.original].forEach((arr) => { const x = rowById(arr, r.id); if (x) x.revisar = false; });
        renderTable(); renderRecon();
      };
      td.append(c);
    }
    const del = document.createElement("button"); del.className = "del"; del.textContent = "✕"; del.title = "Remover linha"; del.setAttribute("aria-label", "Remover linha " + (i + 1));
    del.onclick = () => { S.draft.splice(i, 1); renderTable(); updatePending(); };
    td.append(del); tr.append(td); tb.append(tr);
  });
  updatePending();
}
function updatePending() {
  const n = diffCount(S.rows, S.draft);
  $("#save").disabled = n === 0;
  $("#pending").textContent = n ? `${n} alteração(ões) ainda não aplicada(s). Clique em Salvar alterações antes de copiar ou salvar o CSV.` : "";
}
$("#add").addEventListener("click", () => {
  const today = new Date(); const dd = String(today.getDate()).padStart(2, "0") + "/" + String(today.getMonth() + 1).padStart(2, "0") + "/" + today.getFullYear();
  S.draft.unshift({ id: S.nextId++, data: dd, lancamento: "", categoria: "", tipo: "Compra à vista", valor: "R$ 0,00", conf: 1, revisar: false, chave: "", lancamento_ocr: "" });
  renderTable(); const first = $("#grid tbody input"); if (first) first.focus();
});
$("#save").addEventListener("click", async () => {
  try {
    // linha corrigida e salva = linha conferida: sai a marca "revisar"
    // (só na cópia enviada: se o salvamento falhar, a marca continua na tabela)
    const payload = S.draft.map((d) => { const b = rowById(S.rows, d.id); return b && FIELDS.some((f) => String(b[f]) !== String(d[f])) ? { ...d, revisar: false } : d; });
    const r = await api("/api/normalize", { rows: payload, remember: $("#remember").checked });
    if (r.errors.length) {
      renderTable();
      r.errors.forEach((e) => { const inp = $(`#grid input[data-i="${e.index}"][data-f="${/Valor/.test(e.message) ? "valor" : "data"}"]`); if (inp) inp.classList.add("err"); });
      toast("Corrija antes de salvar: " + r.errors[0].message, 7000); return;
    }
    S.rows = clone(r.rows); S.draft = clone(r.rows);
    const n = diffCount(S.original, S.rows); S.edited = n > 0;
    renderTable(); renderBadge(); renderSummary(); renderRecon();
    toast(S.edited ? "Alterações aplicadas. O resultado foi modificado manualmente." : "Alterações aplicadas. O resultado voltou a ser idêntico à leitura automática.");
  } catch (e) { toast(e.message, 7000); }
});
$("#reset").addEventListener("click", () => {
  if (!confirm("Descartar todas as edições e voltar ao resultado da leitura automática?")) return;
  S.rows = clone(S.original); S.draft = clone(S.original); S.edited = false;
  renderTable(); renderBadge(); renderSummary(); renderRecon(); toast("Voltou ao resultado da leitura automática.");
  // desfaz também os nomes corrigidos que tinham sido lembrados
  api("/api/normalize", { rows: S.original, remember: $("#remember").checked }).catch((e) => toast(e.message, 6000));
});
function renderBadge() {
  const b = $("#edited"), n = diffCount(S.original, S.rows);
  b.hidden = !S.edited; $("#reset").hidden = !S.edited;
  if (S.edited) b.textContent = `✎ Editado manualmente · ${n} alteração(ões) desde a leitura automática`;
}

/* ---------- exportar: copiar para planilha / salvar CSV ---------- */
// Copiar para planilha: Google Sheets/Excel só separam em colunas texto com TAB (ou uma tabela HTML).
const HEAD = ["Data", "Lançamento", "Categoria", "Tipo", "Valor"];
// tab/quebra de linha viram espaço; campo com aspas é citado (senão a planilha junta células)
const tsvCell = (v) => { const s = String(v).replace(/[\t\r\n]+/g, " "); return s.includes('"') ? '"' + s.replace(/"/g, '""') + '"' : s; };
// Valor vai como NÚMERO, não como texto "R$ 31,90": assim a planilha soma, e o usuário escolhe o formato.
// Texto: vírgula decimal e sem separador de milhar ("1896,14", "-8530,63"), que uma planilha em português
// lê como número. Tabela HTML: também data-sheets-value com o número exato (o Google Sheets usa isso ao
// colar entre planilhas), para valer mesmo numa planilha em outro idioma.
const numBR = (cents) => (cents / 100).toFixed(2).replace(".", ",");
const cellsOf = (r) => [r.data, r.lancamento, r.categoria, r.tipo, numBR(r.valor_centavos)];
function tableText() {
  return [HEAD, ...S.rows.map(cellsOf)].map((row) => row.map(tsvCell).join("\t")).join("\r\n");
}
function tableHtml() {
  const td = (c) => `<td>${esc(c)}</td>`;
  const num = (cents) => `<td data-sheets-value="${esc(JSON.stringify({ 1: 3, 3: cents / 100 }))}">${esc(numBR(cents))}</td>`;
  const head = "<tr>" + HEAD.map((h) => `<th>${esc(h)}</th>`).join("") + "</tr>";
  const body = S.rows.map((r) => "<tr>" + cellsOf(r).slice(0, 4).map(td).join("") + num(r.valor_centavos) + "</tr>").join("");
  return `<meta charset="utf-8"><table>${head}${body}</table>`;
}
function copyFallback(text) { // navegadores sem API de área de transferência
  const t = document.createElement("textarea"); t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
  document.body.append(t); t.select();
  try { return document.execCommand("copy"); } catch { return false; } finally { t.remove(); }
}
$("#copy").addEventListener("click", async () => {
  const text = tableText();
  try {
    if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
      await navigator.clipboard.write([new ClipboardItem({
        "text/html": new Blob([tableHtml()], { type: "text/html" }),
        "text/plain": new Blob([text], { type: "text/plain" }),
      })]);
    } else { await navigator.clipboard.writeText(text); }
  } catch { if (!copyFallback(text)) { toast("Não foi possível copiar. Use Salvar CSV.", 6000); return; } }
  toast("Tabela copiada. Na planilha, clique em uma célula e cole (Ctrl+V).");
});

// Salvar CSV: o arquivo sai com ';' e BOM (abre direto no Excel em português; o Google Sheets também importa).
async function csvBlob() {
  const r = await api("/api/csv", { rows: S.rows, delimiter: "semicolon", ...usedMeta() });
  return new Blob(["\ufeff" + r.text], { type: "text/csv;charset=utf-8" });
}
function download(blob) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename();
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast("Baixado como " + filename() + " (pasta de downloads do navegador).", 6000);
}
let saving = false;
$("#savecsv").addEventListener("click", async () => {
  if (saving) return; // clique duplo: um salvamento por vez
  saving = true; $("#savecsv").disabled = true;
  try {
    const blob = await csvBlob(); // primeiro o conteúdo: se falhar, nenhum arquivo vazio é criado
    if (window.showSaveFilePicker) { // Chrome/Edge: janela "Salvar como" do Windows, com o nome já preenchido
      let handle = null;
      try {
        handle = await window.showSaveFilePicker({ suggestedName: filename(), types: [{ description: "Planilha CSV", accept: { "text/csv": [".csv"] } }] });
      } catch (e) { if (e.name === "AbortError") return; } // cancelou: nada a fazer; outro erro: cai no download
      if (handle) {
        const w = await handle.createWritable();
        try { await w.write(blob); await w.close(); } catch (e) { await w.abort().catch(() => {}); throw e; }
        toast("Salvo: " + handle.name + "."); return;
      }
    }
    download(blob); // outros navegadores (ou seletor indisponível): download comum
  } catch (e) { toast("Não foi possível salvar: " + e.message, 7000); }
  finally { saving = false; $("#savecsv").disabled = false; }
});
["#mes", "#ano"].forEach((s) => $(s).addEventListener("change", () => {
  if (S.meta) toast("Mês alterado: clique em Ler capturas de novo para recalcular as datas e o nome do arquivo.", 7000);
}));

/* ---------- summary (SVG/HTML, sem bibliotecas) ---------- */
const tip = $("#tip");
document.addEventListener("mouseover", (e) => { const t = e.target.closest("[data-tip]"); if (t) { tip.textContent = t.dataset.tip; tip.hidden = false; } });
document.addEventListener("mousemove", (e) => { if (!tip.hidden) { tip.style.left = Math.min(e.clientX + 14, innerWidth - 270) + "px"; tip.style.top = e.clientY + 16 + "px"; } });
document.addEventListener("mouseout", (e) => { if (e.target.closest("[data-tip]")) tip.hidden = true; });
document.addEventListener("focusin", (e) => { // teclado: mostra a dica junto ao elemento focado
  const t = e.target.closest("[data-tip]"); if (!t) return;
  const b = t.getBoundingClientRect(); tip.textContent = t.dataset.tip; tip.hidden = false;
  tip.style.left = Math.min(b.left, innerWidth - 270) + "px"; tip.style.top = b.bottom + 8 + "px";
});
document.addEventListener("focusout", (e) => { if (e.target.closest("[data-tip]")) tip.hidden = true; });

function sumBy(rows, keyFn) {
  const m = new Map(); rows.forEach((r) => m.set(keyFn(r), (m.get(keyFn(r)) || 0) + r.valor_centavos));
  return [...m].sort((a, b) => b[1] - a[1]);
}
function hbars(title, pairs, max = 8) {
  let list = pairs.slice(0, max);
  if (pairs.length > max) list = pairs.slice(0, max - 1).concat([["Demais", pairs.slice(max - 1).reduce((s, p) => s + p[1], 0)]]);
  const top = Math.max(...list.map((p) => p[1]), 1);
  const body = list.map(([k, v]) => `<div class="hbar${k === "Demais" && pairs.length > max ? " rest" : ""}"><span class="nm" title="${esc(k)}">${esc(k)}</span><span class="tr"><span class="fl" style="display:block;width:${(v / top * 100).toFixed(1)}%" data-tip="${esc(k)}: ${fmt(v)}" tabindex="0"></span></span><span class="vl">${fmt(v)}</span></div>`).join("");
  return `<div class="card chart"><h3>${esc(title)}</h3>${body || '<p class="muted">Sem dados.</p>'}</div>`;
}
function monthColumns(rows) {
  const m = new Map();
  rows.forEach((r) => { const k = r.data.slice(6) + "-" + r.data.slice(3, 5); m.set(k, (m.get(k) || 0) + r.valor_centavos); });
  const keys = [...m.keys()].sort(); if (!keys.length) return `<div class="card chart"><h3>Compras por mês de origem</h3><p class="muted">Sem dados.</p></div>`;
  const W = 520, H = 170, pad = 22, top = Math.max(...m.values(), 1), bw = Math.min(34, (W - pad) / keys.length - 6);
  const bars = keys.map((k, i) => {
    const v = m.get(k), h = Math.max(2, (v / top) * (H - 46)), x = pad + i * ((W - pad) / keys.length) + 3, y = H - 22 - h;
    const label = k.slice(5) + "/" + k.slice(2, 4);
    const short = v >= 100000 ? "R$ " + (v / 100000).toFixed(1).replace(".", ",") + " mil" : "R$ " + Math.round(v / 100);
    return `<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="4" data-tip="${label}: ${fmt(v)}" tabindex="0"/><text class="val" x="${x + bw / 2}" y="${y - 5}" text-anchor="middle">${short}</text><text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${label}</text>`;
  }).join("");
  return `<div class="card chart"><h3>Compras por mês de origem</h3><svg class="cols" viewBox="0 0 ${W} ${H}" role="img" aria-label="Valor das compras por mês da compra original">${`<line x1="${pad}" x2="${W}" y1="${H - 22}" y2="${H - 22}"/>`}${bars}</svg><p class="muted small">Parcelas aparecem no mês da compra original.</p></div>`;
}
function splitBar(rows) {
  const a = rows.filter((r) => !/^Parcela/.test(r.tipo)).reduce((s, r) => s + r.valor_centavos, 0);
  const p = rows.filter((r) => /^Parcela/.test(r.tipo)).reduce((s, r) => s + r.valor_centavos, 0), t = a + p || 1;
  return `<div class="card chart"><h3>À vista × parcelado</h3><div class="stack" role="img" aria-label="À vista ${fmt(a)}, parcelado ${fmt(p)}">
    <span style="flex:${a};background:var(--series-1)" data-tip="À vista: ${fmt(a)} (${(a / t * 100).toFixed(0)}%)"></span>
    <span style="flex:${p};background:var(--series-2)" data-tip="Parcelado: ${fmt(p)} (${(p / t * 100).toFixed(0)}%)"></span></div>
    <div class="legend"><span><i style="background:var(--series-1)"></i>À vista ${fmt(a)}</span><span><i style="background:var(--series-2)"></i>Parcelado ${fmt(p)}</span></div></div>`;
}
function renderSummary() {
  const el = $("#tab-resumo"), rows = S.rows;
  const spend = rows.filter((r) => r.valor_centavos > 0), credits = rows.filter((r) => r.valor_centavos < 0);
  const total = spend.reduce((s, r) => s + r.valor_centavos, 0), cr = credits.reduce((s, r) => s + r.valor_centavos, 0);
  const big = spend.reduce((b, r) => (!b || r.valor_centavos > b.valor_centavos ? r : b), null);
  // conferência recalculada com as linhas atuais (edições salvas incluídas)
  const rec = reconcile(rows);
  let recK = "";
  if (rec) {
    const sub = rec.ok ? "Total " + fmt(rec.total) : (rec.diff < 0 ? "Faltam " : "Sobram ") + fmt(Math.abs(rec.diff)) + " vs. " + fmt(rec.total);
    recK = `<div class="kpi"><div class="l">Conferência com o total</div><div class="v">${rec.ok ? "✓ Bate" : "✗ Difere"}</div><div class="s">${sub}</div></div>`;
  }
  el.innerHTML = `<div class="kpis">
    <div class="kpi"><div class="l">Total em compras</div><div class="v">${fmt(total)}</div><div class="s">${spend.length} lançamentos</div></div>
    <div class="kpi"><div class="l">Ticket médio</div><div class="v">${fmt(spend.length ? Math.round(total / spend.length) : 0)}</div><div class="s">por compra</div></div>
    <div class="kpi"><div class="l">Maior compra</div><div class="v">${big ? fmt(big.valor_centavos) : "–"}</div><div class="s">${big ? esc(big.lancamento) : ""}</div></div>
    <div class="kpi"><div class="l">Pagamentos e estornos</div><div class="v">${fmt(cr)}</div><div class="s">${credits.length} lançamento(s)</div></div>${recK}</div>
    <div class="charts">${hbars("Gasto por categoria", sumBy(spend, (r) => r.categoria || "SEM CATEGORIA"))}${hbars("Maiores estabelecimentos", sumBy(spend, (r) => r.lancamento || "(sem nome)"), 6)}${splitBar(spend)}${monthColumns(spend)}</div>
    <p class="muted small">Os gráficos usam as linhas da tabela (já com suas edições salvas). Pagamentos e estornos ficam fora dos gráficos.</p>`;
}
