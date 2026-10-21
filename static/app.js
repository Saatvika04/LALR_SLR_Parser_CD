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
const diagram = $("diagram");
const playbackInfo = $("playback-info");
const modeLabel = $("mode-label");

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
renderGrammar();
loadAutomaton();

modeSel.addEventListener("change", function () {
  state.mode = modeSel.value;
  modeLabel.textContent = modeSel.value.toUpperCase();
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
function renderGrammar() {
  grammarEl.textContent = GRAMMAR.join("\n");
}

async function loadAutomaton() {
  const res = await fetch("/automaton");
  state.automaton = await res.json();
  renderParseTable(state.automaton);
  renderDiagram(state.automaton);
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
// State diagram (simple circular layout)
// ---------------------------------------------------------------------------
const SVG_NS = "http://www.w3.org/2000/svg";

function renderDiagram(a) {
  const states = a.states;
  const n = states.length;
  const W = 900, H = 900;
  const cx = W / 2, cy = H / 2;
  const R = Math.min(cx, cy) - 100;

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  svg.setAttribute("class", "state-diagram");

  const pos = {};
  states.forEach(function (st, i) {
    const ang = (2 * Math.PI * i) / n - Math.PI / 2;
    pos[st.id] = { x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
  });

  const defs = document.createElementNS(SVG_NS, "defs");
  defs.innerHTML =
    '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
    '<path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker>';
  svg.appendChild(defs);

  states.forEach(function (st) {
    st.actions.forEach(function (act) {
      if (act.action === "shift") addEdge(svg, pos, st.id, act.to, act.symbol, "shift");
    });
    st.gotos.forEach(function (g) {
      addEdge(svg, pos, st.id, g.to, g.symbol, "goto");
    });
  });

  states.forEach(function (st) {
    const p = pos[st.id];
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "node-group");
    g.setAttribute("data-state", st.id);
    g.innerHTML =
      '<circle cx="' + p.x + '" cy="' + p.y + '" r="22" class="node"/>' +
      '<text x="' + p.x + '" y="' + (p.y + 5) + '" class="node-label" text-anchor="middle">' + st.id + "</text>";
    svg.appendChild(g);
  });

  diagram.innerHTML = "";
  diagram.appendChild(svg);
}

function addEdge(svg, pos, from, to, label, kind) {
  const a = pos[from], b = pos[to];
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len < 1) return; // skip self-loops for now
  const off = 24;
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
  highlightDiagram();
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
  highlightDiagram();
}
