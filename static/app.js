"use strict";

// ---------------------------------------------------------------------------
// Static data + helpers
// ---------------------------------------------------------------------------
const GRAMMAR = [
  "S' → program",
  "program → assignment",
  "assignment → ID = expression ;",
  "expression → expression + term | expression - term | term",
  "term → term * factor | term / factor | factor",
  "factor → ID | NUM | ( expression )",
];

const ACTION_CLASS = { INIT: "init", SHIFT: "shift", REDUCE: "reduce", ACCEPT: "accept", ERROR: "error" };

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

const $ = (id) => document.getElementById(id);

const state = {
  automaton: null,
  steps: [],
  current: -1,
  mode: "slr",
};

// DOM refs
const sourceEl = $("source");
const modeSel = $("mode");
const sampleSel = $("sample");
const banner = $("banner");
const summary = $("summary");
const tbody = document.querySelector("#trace-table tbody");
const emptyTrace = $("empty-trace");
const grammarEl = $("grammar");
const parseTable = $("parse-table");
const playbackInfo = $("playback-info");
const modeLabel = $("mode-label");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
loadAutomaton();

modeSel.addEventListener("change", function () {
  state.mode = modeSel.value;
  modeLabel.textContent = modeSel.value.toUpperCase();
  $("grammar-title").textContent = "Grammar (" + modeSel.value.toUpperCase() + " mode)";
  $("table-title").textContent = modeSel.value.toUpperCase() + " Parsing Table";
  loadAutomaton();
});
sampleSel.addEventListener("change", function () {
  if (sampleSel.value !== "") sourceEl.value = sampleSel.value;
});
$("run").addEventListener("click", runParse);
$("reset").addEventListener("click", resetAll);
$("prev").addEventListener("click", function () { stepTo(state.current - 1); });
$("next").addEventListener("click", function () { stepTo(state.current + 1); });

// ---------------------------------------------------------------------------
// Grammar + automaton
// ---------------------------------------------------------------------------
function renderGrammar(grammar) {
  grammarEl.textContent = (grammar || GRAMMAR).join("\n");
}

async function loadAutomaton() {
  try {
    const res = await fetch("/automaton?mode=" + encodeURIComponent(state.mode));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Automaton could not be loaded.");
    state.automaton = data;
    renderGrammar(data.grammar);
    renderParseTable(data);
  } catch (err) {
    state.automaton = null;
    parseTable.textContent = err.message;
  }
}

function renderParseTable(a) {
  const terms = a.terminals.concat(["$"]);
  const nts = a.nonterminals;
  let html = "<thead><tr><th>State</th>";
  terms.forEach(function (t) { html += "<th>" + esc(t) + "</th>"; });
  nts.forEach(function (n) { html += "<th class='nt'>" + esc(n) + "</th>"; });
  html += "</tr></thead><tbody>";

  a.states.forEach(function (st) {
    html += "<tr><td class='num'>" + st.id + "</td>";
    terms.forEach(function (t) {
      const act = st.actions.find(function (x) { return x.symbol === t; });
      if (!act) { html += "<td></td>"; return; }
      if (act.action === "shift") html += "<td class='shift'>s" + act.to + "</td>";
      else if (act.action === "reduce") html += "<td class='reduce' title='" + esc(act.production) + "'>r" + act.production_index + "</td>";
      else html += "<td class='accept'>acc</td>";
    });
    nts.forEach(function (n) {
      const g = st.gotos.find(function (x) { return x.symbol === n; });
      html += g ? "<td class='nt'>" + g.to + "</td>" : "<td></td>";
    });
    html += "</tr>";
  });

  html += "</tbody>";
  parseTable.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Parse + rendering
// ---------------------------------------------------------------------------
async function runParse() {
  const res = await fetch("/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: sourceEl.value, mode: state.mode }),
  });
  const data = await res.json();
  renderBanner(data);
  renderSummary(data.stats || {});
  renderTrace(data.steps || []);
  state.steps = data.steps || [];
  stepTo(state.steps.length ? 0 : -1);
}

function renderBanner(data) {
  banner.classList.remove("hidden", "ok", "bad", "warn");
  if (data.result === "ACCEPTED") {
    banner.classList.add("ok");
    banner.textContent = "ACCEPTED";
  } else if (data.result === "SYNTAX ERROR") {
    banner.classList.add("bad");
    banner.textContent = "SYNTAX ERROR" + (data.error ? " — " + data.error : "");
  } else if (!data.result) {
    banner.classList.add("warn");
    banner.textContent = "PARSER UNAVAILABLE" + (data.error ? " — " + data.error : "");
  } else {
    banner.classList.add("warn");
    banner.textContent = data.result + (data.error ? " — " + data.error : "");
  }
}

function renderSummary(stats) {
  const items = [
    ["Tokens", stats.token_count || 0],
    ["Steps", stats.total_steps || 0],
    ["Shifts", stats.shifts || 0],
    ["Reduces", stats.reductions || 0],
    ["Errors", stats.errors || 0],
  ];
  summary.innerHTML = "";
  items.forEach(function (pair) {
    const d = document.createElement("div");
    d.className = "stat";
    d.innerHTML = '<span class="stat-val">' + pair[1] + '</span><span class="stat-label">' + pair[0] + "</span>";
    summary.appendChild(d);
  });
}

function renderTrace(steps) {
  tbody.innerHTML = "";
  emptyTrace.style.display = steps.length ? "none" : "block";
  steps.forEach(function (s, idx) {
    const tr = document.createElement("tr");
    tr.setAttribute("data-idx", idx);
    const cls = ACTION_CLASS[s.action] || "init";
    let prod = s.production ? '<span class="prod">' + esc(s.production) + "</span>" : "";
    tr.innerHTML =
      '<td class="num">' + s.step + "</td>" +
      '<td class="mono stack">' + esc(s.stack.join(" ")) + "</td>" +
      '<td class="mono input">' + esc(s.remaining_input.join(" ")) + "</td>" +
      '<td><span class="tag ' + cls + '">' + esc(s.action) + "</span>" + prod + "</td>";
    tbody.appendChild(tr);
  });
}

function stepTo(i) {
  if (!state.steps.length) { playbackInfo.textContent = "—"; return; }
  i = Math.max(0, Math.min(i, state.steps.length - 1));
  state.current = i;
  document.querySelectorAll("#trace-table tbody tr").forEach(function (tr, idx) {
    tr.classList.toggle("active", idx === i);
  });
  const row = document.querySelector('#trace-table tbody tr[data-idx="' + i + '"]');
  if (row) row.scrollIntoView({ block: "nearest" });
  playbackInfo.textContent = "Step " + i + " / " + (state.steps.length - 1);
}

function resetAll() {
  sourceEl.value = "";
  banner.classList.add("hidden");
  summary.innerHTML = "";
  tbody.innerHTML = "";
  emptyTrace.style.display = "block";
  state.steps = [];
  state.current = -1;
  playbackInfo.textContent = "—";
}
