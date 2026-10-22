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
  mode: "slr",
  automaton: null,
  compare: null,
  steps: [],
  current: -1,
};

// DOM refs
const sourceEl = $("source");
const modeSel = $("mode");
const sampleSel = $("sample");
const grammarEl = $("grammar");
const parseTable = $("parse-table");
const diagram = $("diagram");
const playbackInfo = $("playback-info");
const modeLabel = $("mode-label");
const conflictsEl = $("conflicts");

// Per-column DOM refs
const columns = {
  slr: {
    banner: $("banner-slr"),
    summary: $("summary-slr"),
    tbody: document.querySelector("#trace-table-slr tbody"),
    empty: $("empty-slr"),
  },
  lalr: {
    banner: $("banner-lalr"),
    summary: $("summary-lalr"),
    tbody: document.querySelector("#trace-table-lalr tbody"),
    empty: $("empty-lalr"),
  },
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
loadAutomaton();

modeSel.addEventListener("change", function () {
  state.mode = modeSel.value;
  modeLabel.textContent = modeSel.value.toUpperCase();
  $("grammar-title").textContent = "Grammar (" + modeSel.value.toUpperCase() + " mode)";
  $("table-title").textContent = modeSel.value.toUpperCase() + " Parsing Table";
  $("diagram-title").textContent = "State Diagram (" + modeSel.value.toUpperCase() + ")";
  loadAutomaton();
  syncStepsToMode();
});
sampleSel.addEventListener("change", function () {
  if (sampleSel.value !== "") sourceEl.value = sampleSel.value;
});
$("run").addEventListener("click", runCompare);
$("reset").addEventListener("click", resetAll);
$("prev").addEventListener("click", function () { stepTo(state.current - 1); });
$("next").addEventListener("click", function () { stepTo(state.current + 1); });

// Point playback at the active mode's trace after a mode switch or a parse.
function syncStepsToMode() {
  if (!state.compare) return;
  const side = state.compare[state.mode] || {};
  state.steps = side.steps || [];
  state.current = -1;
  stepTo(state.steps.length ? 0 : -1);
}

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
    renderConflicts(data);
    renderDiagram(data);
    highlightDiagram();
  } catch (err) {
    state.automaton = null;
    parseTable.textContent = err.message;
    conflictsEl.innerHTML = '<p class="muted">' + esc(err.message) + "</p>";
    diagram.innerHTML = "";
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

function renderConflicts(a) {
  const list = (a && a.conflicts) || [];
  if (!list.length) {
    conflictsEl.innerHTML = '<p class="muted">No conflicts reported.</p>';
    return;
  }
  conflictsEl.innerHTML = list.map(function (c) {
    if (typeof c === "string") {
      return '<div class="conflict"><span class="tag reduce">conflict</span> ' + esc(c) + "</div>";
    }
    return '<div class="conflict">' +
      '<span class="conflict-head">State ' + esc(c.state) + " · token " + esc(c.token) + "</span>" +
      ' <span class="tag reduce">' + esc(c.type || "conflict") + "</span>" +
      ' → <span class="tag shift">' + esc(c.resolution || "") + "</span>" +
      (c.note ? '<div class="conflict-note">' + esc(c.note) + "</div>" : "") +
      "</div>";
  }).join("");
}

// ---------------------------------------------------------------------------
// State diagram (circular layout, driven by the real automaton)
// ---------------------------------------------------------------------------
const SVG_NS = "http://www.w3.org/2000/svg";

function renderDiagram(a) {
  if (!a || !a.states || !a.states.length) { diagram.innerHTML = ""; return; }
  const states = a.states;
  const n = states.length;
  const W = 1000, H = 1000;
  const cx = W / 2, cy = H / 2;
  const R = Math.min(cx, cy) - 130;
  const nodeR = n > 30 ? 13 : 20;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("class", "state-diagram");

  const defs = document.createElementNS(SVG_NS, "defs");
  defs.innerHTML =
    '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
    '<path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker>';
  svg.appendChild(defs);

  const pos = {};
  states.forEach(function (st, i) {
    const ang = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[st.id] = { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
  });

  const edgeMap = new Map();
  states.forEach(function (st) {
    st.actions.forEach(function (act) {
      if (act.action === "shift") addEdgeData(edgeMap, st.id, act.to, act.symbol, "shift");
    });
    st.gotos.forEach(function (g) {
      addEdgeData(edgeMap, st.id, g.to, g.symbol, "goto");
    });
  });

  edgeMap.forEach(function (e) {
    drawEdge(svg, pos, e.from, e.to, e.labels.join(", "), e.kinds.has("shift") ? "shift" : "goto");
  });

  states.forEach(function (st) {
    const p = pos[st.id];
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "node-group");
    g.setAttribute("data-state", st.id);
    g.innerHTML =
      '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + nodeR + '" class="node"/>' +
      '<text x="' + p.x + '" y="' + (p.y + 4) + '" class="node-label" text-anchor="middle">' + st.id + "</text>";
    svg.appendChild(g);
  });

  diagram.innerHTML = "";
  diagram.appendChild(svg);
}

function addEdgeData(edgeMap, from, to, label, kind) {
  if (from === to) return; // skip self-loops (rare in LR automata)
  const key = from + "->" + to;
  if (!edgeMap.has(key)) edgeMap.set(key, { from: from, to: to, labels: [], kinds: new Set() });
  const e = edgeMap.get(key);
  if (e.labels.indexOf(label) === -1) e.labels.push(label);
  e.kinds.add(kind);
}

function drawEdge(svg, pos, from, to, label, kind) {
  const a = pos[from], b = pos[to];
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len < 1) return;
  const off = 26;
  const sx = a.x + (dx / len) * off, sy = a.y + (dy / len) * off;
  const ex = b.x - (dx / len) * (off + 8), ey = b.y - (dy / len) * (off + 8);

  const line = document.createElementNS(SVG_NS, "line");
  line.setAttribute("x1", sx); line.setAttribute("y1", sy);
  line.setAttribute("x2", ex); line.setAttribute("y2", ey);
  line.setAttribute("class", "edge " + kind);
  line.setAttribute("marker-end", "url(#arrow)");
  svg.appendChild(line);

  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const t = document.createElementNS(SVG_NS, "text");
  t.setAttribute("x", mx); t.setAttribute("y", my - 6);
  t.setAttribute("class", "edge-label");
  t.setAttribute("text-anchor", "middle");
  t.textContent = label;
  svg.appendChild(t);
}

function highlightDiagram() {
  if (!state.automaton) return;
  const s = (state.current >= 0 && state.steps[state.current]) ? state.steps[state.current].state : -1;
  diagram.querySelectorAll(".node-group").forEach(function (g) {
    g.classList.toggle("active", parseInt(g.getAttribute("data-state"), 10) === s);
  });
}

// ---------------------------------------------------------------------------
// Comparison / parse
// ---------------------------------------------------------------------------
async function runCompare() {
  const res = await fetch("/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input: sourceEl.value }),
  });
  const data = await res.json();
  state.compare = data;
  renderColumn("slr", data.slr || {});
  renderColumn("lalr", data.lalr || {});
  syncStepsToMode();
}

function renderColumn(mode, data) {
  const col = columns[mode];
  renderBanner(col.banner, data);
  renderSummary(col.summary, data.stats || {});
  renderTrace(col.tbody, data.steps || []);
  col.empty.style.display = (data.steps || []).length ? "none" : "block";
}

function renderBanner(el, data) {
  el.classList.remove("hidden", "ok", "bad", "warn");
  if (data.result === "ACCEPTED") {
    el.classList.add("ok");
    el.textContent = "ACCEPTED";
  } else if (data.result === "SYNTAX ERROR") {
    el.classList.add("bad");
    el.textContent = "SYNTAX ERROR" + (data.error ? " — " + data.error : "");
  } else if (data.result === "UNAVAILABLE") {
    el.classList.add("warn");
    el.textContent = "UNAVAILABLE" + (data.error ? " — " + data.error : "");
  } else {
    el.classList.add("warn");
    el.textContent = data.result + (data.error ? " — " + data.error : "");
  }
}

function renderSummary(el, stats) {
  const items = [
    ["Tokens", stats.token_count || 0],
    ["Steps", stats.total_steps || 0],
    ["Shifts", stats.shifts || 0],
    ["Reduces", stats.reductions || 0],
    ["Errors", stats.errors || 0],
  ];
  el.innerHTML = "";
  items.forEach(function (pair) {
    const d = document.createElement("div");
    d.className = "stat";
    d.innerHTML = '<span class="stat-val">' + pair[1] + '</span><span class="stat-label">' + pair[0] + "</span>";
    el.appendChild(d);
  });
}

function renderTrace(tbody, steps) {
  tbody.innerHTML = "";
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

// ---------------------------------------------------------------------------
// Playback
// ---------------------------------------------------------------------------
function stepTo(i) {
  if (!state.steps.length) { playbackInfo.textContent = "—"; return; }
  i = Math.max(0, Math.min(i, state.steps.length - 1));
  state.current = i;
  playbackInfo.textContent = "Step " + i + " / " + (state.steps.length - 1);
  const tbody = columns[state.mode].tbody;
  tbody.querySelectorAll("tr").forEach(function (tr, idx) {
    tr.classList.toggle("active", idx === i);
  });
  highlightDiagram();
}

function resetAll() {
  sourceEl.value = "";
  state.compare = null;
  state.steps = [];
  state.current = -1;
  Object.keys(columns).forEach(function (mode) {
    const col = columns[mode];
    col.banner.classList.add("hidden");
    col.summary.innerHTML = "";
    col.tbody.innerHTML = "";
    col.empty.style.display = "block";
  });
  playbackInfo.textContent = "—";
  highlightDiagram();
}
