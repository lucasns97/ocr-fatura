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
  // padrão: a fatura que vence no mês corrente
  sel.value = document.body.dataset.month; $("#ano").value = document.body.dataset.year;
})();

/* ---------- step 2: files ---------- */
const drop = $("#drop"), input = $("#file");
drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });

function addFiles(list) {
  const imgs = [...list].filter((f) => f.type.startsWith("image/"));
  if (imgs.length < list.length) toast("Arquivos que não são imagem foram ignorados.");
  // ordem natural pelo nome (capturas do celular têm data/hora no nome)
  imgs.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  imgs.forEach((f) => S.files.push({ file: f, url: URL.createObjectURL(f) }));
  renderFiles();
}
function renderFiles() {
  const ol = $("#files"); ol.innerHTML = "";
  S.files.forEach((f, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<img alt=""><span class="nm"></span><span class="ctl"><button title="Subir" aria-label="Mover para cima">↑</button><button title="Descer" aria-label="Mover para baixo">↓</button><button title="Remover" aria-label="Remover">✕</button></span>`;
    $("img", li).src = f.url; $(".nm", li).textContent = `${i + 1}. ${f.file.name}`;
    const [up, down, rm] = li.querySelectorAll("button");
    up.disabled = i === 0; down.disabled = i === S.files.length - 1;
    up.onclick = () => { [S.files[i - 1], S.files[i]] = [S.files[i], S.files[i - 1]]; renderFiles(); };
    down.onclick = () => { [S.files[i + 1], S.files[i]] = [S.files[i], S.files[i + 1]]; renderFiles(); };
    rm.onclick = () => { URL.revokeObjectURL(f.url); S.files.splice(i, 1); renderFiles(); };
    ol.append(li);
  });
  $("#go").disabled = S.files.length === 0;
}

$("#go").addEventListener("click", async () => {
  if (S.meta && (S.edited || diffCount(S.rows, S.draft)) && !confirm("Ler de novo descarta suas edições. Continuar?")) return;
  const btn = $("#go"), status = $("#status");
  btn.disabled = true; status.textContent = "Lendo as capturas… (cerca de 1 s por imagem)";
  const fd = new FormData();
  const m = meta(); fd.append("ano", m.ano); fd.append("mes", m.mes);
  fd.append("fechamento", $("#fechamento").value); fd.append("total", $("#total").value);
  S.files.forEach((f) => fd.append("files", f.file, f.file.name));
  try {
    const r = await api("/api/process", fd, true);
    S.meta = { ...m, stats: r.stats };
    S.original = clone(r.rows); S.rows = clone(r.rows); S.draft = clone(r.rows); S.edited = false;
    showResults(r);
    status.textContent = "";
  } catch (e) { status.textContent = ""; toast(e.message, 8000); }
  btn.disabled = S.files.length === 0;
});

/* ---------- results ---------- */
function showResults(r) {
  $("#results").hidden = false;
  const w = $("#warnings"); w.innerHTML = "";
  r.warnings.forEach((t) => { const d = document.createElement("div"); d.className = "notice"; d.textContent = t; w.append(d); });
  const rec = r.stats.reconciliation;
  if (rec && rec.ok) { const d = document.createElement("div"); d.className = "notice ok"; d.textContent = `✓ A soma bate com o total informado (${fmt(rec.total)}).`; w.append(d); }
  const st = r.stats;
  const info = document.createElement("div"); info.className = "muted small"; info.style.marginBottom = "10px";
  info.textContent = `${st.rows} transações de ${st.images} captura(s); ${st.duplicates_removed} repetida(s) por sobreposição removida(s).`;
  w.append(info);
  $("#fname").textContent = filename();
  $("#path").value = defaultPath();
  renderTable(); renderBadge(); refreshCsv(); renderSummary(); setTab("tabela");
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}
function defaultPath() {
  const dir = document.body.dataset.dir; const sep = dir.includes("\\") ? "\\" : "/";
  return dir + sep + filename();
}

/* ---------- tabs ---------- */
function setTab(name) {
  document.querySelectorAll("[role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  document.querySelectorAll(".tabpanel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
  if (name === "csv") refreshCsv();
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
    if (r.revisar) { const c = document.createElement("span"); c.className = "chip warn"; c.textContent = "revisar"; c.title = "Leitura incerta (confiança " + Math.round(r.conf * 100) + "%)"; td.append(c); }
    const del = document.createElement("button"); del.className = "del"; del.textContent = "✕"; del.title = "Remover linha"; del.setAttribute("aria-label", "Remover linha " + (i + 1));
    del.onclick = () => { S.draft.splice(i, 1); renderTable(); updatePending(); };
    td.append(del); tr.append(td); tb.append(tr);
  });
  updatePending();
}
function updatePending() {
  const n = diffCount(S.rows, S.draft);
  $("#save").disabled = n === 0;
  $("#pending").textContent = n ? `${n} alteração(ões) não salva(s)` : "";
  $("#csvstale").hidden = n === 0;
}
$("#add").addEventListener("click", () => {
  const today = new Date(); const dd = String(today.getDate()).padStart(2, "0") + "/" + String(today.getMonth() + 1).padStart(2, "0") + "/" + today.getFullYear();
  S.draft.unshift({ id: S.nextId++, data: dd, lancamento: "", categoria: "", tipo: "Compra à vista", valor: "R$ 0,00", conf: 1, revisar: false, chave: "", lancamento_ocr: "" });
  renderTable(); const first = $("#grid tbody input"); if (first) first.focus();
});
$("#save").addEventListener("click", async () => {
  try {
    const r = await api("/api/normalize", { rows: S.draft, remember: $("#remember").checked });
    if (r.errors.length) {
      renderTable();
      r.errors.forEach((e) => { const inp = $(`#grid input[data-i="${e.index}"][data-f="${/Valor/.test(e.message) ? "valor" : "data"}"]`); if (inp) inp.classList.add("err"); });
      toast("Corrija antes de salvar: " + r.errors[0].message, 7000); return;
    }
    S.rows = clone(r.rows); S.draft = clone(r.rows);
    const n = diffCount(S.original, S.rows); S.edited = n > 0;
    renderTable(); renderBadge(); refreshCsv(); renderSummary();
    toast(S.edited ? "Alterações aplicadas. O resultado foi modificado manualmente." : "Alterações aplicadas. O resultado voltou a ser idêntico à leitura automática.");
  } catch (e) { toast(e.message, 7000); }
});
$("#reset").addEventListener("click", () => {
  if (!confirm("Descartar todas as edições e voltar ao resultado da leitura automática?")) return;
  S.rows = clone(S.original); S.draft = clone(S.original); S.edited = false;
  renderTable(); renderBadge(); refreshCsv(); renderSummary(); toast("Voltou ao resultado da leitura automática.");
  // desfaz também os nomes corrigidos que tinham sido lembrados
  api("/api/normalize", { rows: S.original, remember: $("#remember").checked }).catch((e) => toast(e.message, 6000));
});
function renderBadge() {
  const b = $("#edited"), n = diffCount(S.original, S.rows);
  b.hidden = !S.edited; $("#reset").hidden = !S.edited;
  if (S.edited) b.textContent = `✎ Editado manualmente · ${n} alteração(ões) desde a leitura automática`;
}

/* ---------- CSV tab ---------- */
let csvText = "";
async function refreshCsv() {
  if (!S.rows.length && !S.original.length) return;
  try {
    const r = await api("/api/csv", { rows: S.rows, delimiter: $("#delim").value, ...usedMeta() });
    csvText = r.text; $("#csvtext").value = r.text;
  } catch (e) { toast(e.message, 6000); }
}
$("#delim").addEventListener("change", refreshCsv);
$("#copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(csvText); }
  catch { const t = $("#csvtext"); t.select(); document.execCommand("copy"); }
  toast("CSV copiado para a área de transferência.");
});
const blobOf = () => new Blob(["﻿" + csvText], { type: "text/csv;charset=utf-8" });
$("#download").addEventListener("click", () => {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blobOf()); a.download = filename();
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast("Baixado como " + filename() + " (pasta de downloads do navegador).");
});
if (window.showSaveFilePicker) {
  $("#saveas").hidden = false;
  $("#saveas").addEventListener("click", async () => {
    try {
      const h = await window.showSaveFilePicker({ suggestedName: filename(), types: [{ description: "CSV", accept: { "text/csv": [".csv"] } }] });
      const w = await h.createWritable(); await w.write(blobOf()); await w.close(); toast("Salvo em " + h.name + ".");
    } catch (e) { if (e.name !== "AbortError") toast("Não foi possível salvar: " + e.message, 6000); }
  });
}
$("#savepath").addEventListener("click", () => savePath(false));
async function savePath(overwrite) {
  try {
    const r = await api("/api/save", { rows: S.rows, delimiter: $("#delim").value, path: $("#path").value, overwrite, ...usedMeta() });
    toast("Salvo em " + r.path, 7000);
  } catch (e) {
    if (e.status === 409 && confirm(e.message + "\n\nSobrescrever?")) return savePath(true);
    if (e.status !== 409) toast(e.message, 8000);
  }
}
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
  const rec0 = S.meta && S.meta.stats.reconciliation;
  let recK = "";
  if (rec0) {
    const net = total + cr, ok = rec0.total === total || rec0.total === net, diff = rec0.total - total;
    const sub = ok ? "Total " + fmt(rec0.total) : (diff > 0 ? "Faltam " : "Sobram ") + fmt(Math.abs(diff)) + " vs. " + fmt(rec0.total);
    recK = `<div class="kpi"><div class="l">Conferência com o total</div><div class="v">${ok ? "✓ Bate" : "✗ Difere"}</div><div class="s">${sub}</div></div>`;
  }
  el.innerHTML = `<div class="kpis">
    <div class="kpi"><div class="l">Total em compras</div><div class="v">${fmt(total)}</div><div class="s">${spend.length} lançamentos</div></div>
    <div class="kpi"><div class="l">Ticket médio</div><div class="v">${fmt(spend.length ? Math.round(total / spend.length) : 0)}</div><div class="s">por compra</div></div>
    <div class="kpi"><div class="l">Maior compra</div><div class="v">${big ? fmt(big.valor_centavos) : "–"}</div><div class="s">${big ? esc(big.lancamento) : ""}</div></div>
    <div class="kpi"><div class="l">Pagamentos e estornos</div><div class="v">${fmt(cr)}</div><div class="s">${credits.length} lançamento(s)</div></div>${recK}</div>
    <div class="charts">${hbars("Gasto por categoria", sumBy(spend, (r) => r.categoria || "SEM CATEGORIA"))}${hbars("Maiores estabelecimentos", sumBy(spend, (r) => r.lancamento || "(sem nome)"), 6)}${splitBar(spend)}${monthColumns(spend)}</div>
    <p class="muted small">Os gráficos usam as linhas da tabela (já com suas edições salvas). Pagamentos e estornos ficam fora dos gráficos.</p>`;
}
