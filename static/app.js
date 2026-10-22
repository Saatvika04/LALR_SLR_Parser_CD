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
  selectedState: null,
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
const playbackInfo = $("playback-info");
const modeLabel = $("mode-label");
const stateCount = $("state-count");
const parserCounts = { slr: $("slr-automaton-count"), lalr: $("lalr-automaton-count") };
const stateSelect = $("state-select");
const stateDetails = $("state-details");
const stateDetailsTitle = $("state-details-title");
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
stateSelect.addEventListener("change", function () {
  const selectedState = Number(stateSelect.value);
  if (Number.isInteger(selectedState)) selectAutomatonState(selectedState);
});

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
  grammarEl.textContent = (Array.isArray(grammar) ? grammar : GRAMMAR).join("\n");
}

function isAutomaton(data) {
  if (!(data && typeof data.parser === "string" &&
    Array.isArray(data.terminals) && data.terminals.every(function (symbol) { return typeof symbol === "string"; }) &&
    Array.isArray(data.nonterminals) && data.nonterminals.every(function (symbol) { return typeof symbol === "string"; }) &&
    Array.isArray(data.grammar) && data.grammar.every(function (production) { return typeof production === "string"; }) &&
    Array.isArray(data.states) &&
    Array.isArray(data.conflicts) && data.conflicts.every(function (conflict) {
      return typeof conflict === "string" || (conflict && Number.isInteger(conflict.state) &&
        typeof conflict.token === "string" && typeof conflict.type === "string" &&
        typeof conflict.resolution === "string" &&
        (conflict.note === undefined || typeof conflict.note === "string"));
    }) && data.states.length && data.states.every(function (st) {
      return st && Number.isInteger(st.id) && Array.isArray(st.items) &&
        st.items.every(function (item) { return typeof item === "string"; }) &&
        Array.isArray(st.actions) && st.actions.every(function (action) {
          return action && typeof action.symbol === "string" &&
            ["shift", "reduce", "accept"].indexOf(action.action) !== -1 &&
            (action.action !== "shift" || Number.isInteger(action.to)) &&
            (action.action !== "reduce" || (typeof action.production === "string" && Number.isInteger(action.production_index)));
        }) && Array.isArray(st.gotos) && st.gotos.every(function (go) {
          return go && typeof go.symbol === "string" && Number.isInteger(go.to);
        });
    }))) return false;
  const ids = new Set(data.states.map(function (st) { return st.id; }));
  return data.states.every(function (st) {
    return st.actions.every(function (action) { return action.action !== "shift" || ids.has(action.to); }) &&
      st.gotos.every(function (go) { return ids.has(go.to); });
  });
}

function updateParserCount(mode, data) {
  parserCounts[mode].textContent = "(" + data.parser + " · " + data.states.length + " states)";
}

async function loadOtherParserCount(mode) {
  try {
    const res = await fetch("/automaton?mode=" + encodeURIComponent(mode));
    const data = await res.json();
    if (!res.ok || !isAutomaton(data)) throw new Error("Automaton is unavailable.");
    updateParserCount(mode, data);
    if (mode === "lalr") renderConflicts(data);
  } catch (err) {
    parserCounts[mode].textContent = "(state count unavailable)";
    if (mode === "lalr") {
      conflictsEl.innerHTML = '<p class="muted">LALR conflict information is unavailable.</p>';
    }
  }
}

function renderStateOptions(states, selectedState) {
  stateSelect.innerHTML = "";
  states.forEach(function (automatonState) {
    const option = document.createElement("option");
    option.value = String(automatonState.id);
    option.textContent = "State " + automatonState.id;
    stateSelect.appendChild(option);
  });
  stateSelect.disabled = false;
  stateSelect.value = String(selectedState);
}

async function loadAutomaton() {
  try {
    const res = await fetch("/automaton?mode=" + encodeURIComponent(state.mode));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Automaton could not be loaded.");
    if (!isAutomaton(data)) throw new Error("Automaton response did not match the expected format.");
    state.automaton = data;
    state.selectedState = null;
    stateCount.textContent = "· " + data.states.length + " states";
    updateParserCount(state.mode, data);
    loadOtherParserCount(state.mode === "slr" ? "lalr" : "slr");
    renderGrammar(data.grammar);
    renderParseTable(data);
    if (data.parser === "LALR") renderConflicts(data);
    const initialState = state.steps.length && state.steps[state.current]
      ? state.steps[state.current].state
      : data.states[0].id;
    const selectedState = data.states.some(function (item) { return item.id === initialState; })
      ? initialState
      : data.states[0].id;
    renderStateOptions(data.states, selectedState);
    selectAutomatonState(selectedState);
  } catch (err) {
    state.automaton = null;
    stateCount.textContent = "";
    parserCounts[state.mode].textContent = "(state count unavailable)";
    parseTable.textContent = err.message;
    stateSelect.innerHTML = '<option value="">Automaton unavailable</option>';
    stateSelect.disabled = true;
    stateDetails.innerHTML = '<p class="muted">' + esc(err.message) + "</p>";
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

function selectAutomatonState(stateId) {
  const automatonState = state.automaton && state.automaton.states.find(function (item) {
    return item.id === stateId;
  });
  if (!automatonState) return;
  state.selectedState = stateId;
  renderStateDetails(stateId);
  stateSelect.value = String(stateId);
}

function appendDetailList(parent, title, values) {
  const heading = document.createElement("h3");
  heading.textContent = title;
  parent.appendChild(heading);
  const list = document.createElement("ul");
  values.forEach(function (value) {
    const item = document.createElement("li");
    item.textContent = value;
    list.appendChild(item);
  });
  if (!values.length) {
    const item = document.createElement("li");
    item.textContent = "None";
    list.appendChild(item);
  }
  parent.appendChild(list);
}

function renderStateDetails(stateId) {
  const automatonState = state.automaton && state.automaton.states.find(function (item) {
    return item.id === stateId;
  });
  if (!automatonState) return;
  stateDetailsTitle.textContent = state.automaton.parser + " State " + stateId;
  stateDetails.innerHTML = "";
  appendDetailList(stateDetails, "LR Items", automatonState.items);
  appendDetailList(stateDetails, "Actions", automatonState.actions.map(function (action) {
    if (action.action === "shift") return action.symbol + ": shift to state " + action.to;
    if (action.action === "reduce") return action.symbol + ": reduce by r" + action.production_index + " (" + action.production + ")";
    return action.symbol + ": " + action.action;
  }));
  appendDetailList(stateDetails, "Gotos", automatonState.gotos.map(function (go) {
    return go.symbol + ": go to state " + go.to;
  }));
}

function syncSelectedStateToTrace() {
  if (!state.automaton) return;
  const s = (state.current >= 0 && state.steps[state.current]) ? state.steps[state.current].state : -1;
  if (s >= 0) selectAutomatonState(s);
  else if (state.selectedState !== null) renderStateDetails(state.selectedState);
}

// ---------------------------------------------------------------------------
// Comparison / parse
// ---------------------------------------------------------------------------
async function runCompare() {
  try {
    const res = await fetch("/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: sourceEl.value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Parser comparison failed.");
    if (!data || typeof data !== "object") throw new Error("Comparison response was invalid.");
    state.compare = {
      slr: data.slr && typeof data.slr === "object" ? data.slr : unavailableResult("SLR result is missing."),
      lalr: data.lalr && typeof data.lalr === "object" ? data.lalr : unavailableResult("LALR result is missing."),
    };
  } catch (err) {
    state.compare = { slr: unavailableResult(err.message), lalr: unavailableResult(err.message) };
  }
  renderColumn("slr", state.compare.slr);
  renderColumn("lalr", state.compare.lalr);
  syncStepsToMode();
}

function unavailableResult(message) {
  return { result: "UNAVAILABLE", error: message, steps: [], stats: {} };
}

function renderColumn(mode, data) {
  const col = columns[mode];
  data = data && typeof data === "object" ? data : unavailableResult("Parser result is invalid.");
  renderBanner(col.banner, data);
  renderSummary(col.summary, data.stats && typeof data.stats === "object" ? data.stats : {});
  const steps = Array.isArray(data.steps) ? data.steps : [];
  renderTrace(col.tbody, steps);
  col.empty.style.display = steps.length ? "none" : "block";
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
    const value = document.createElement("span");
    value.className = "stat-val";
    value.textContent = Number.isFinite(pair[1]) ? String(pair[1]) : "0";
    const label = document.createElement("span");
    label.className = "stat-label";
    label.textContent = pair[0];
    d.appendChild(value);
    d.appendChild(label);
    el.appendChild(d);
  });
}

function renderTrace(tbody, steps) {
  tbody.innerHTML = "";
  steps.filter(function (s) {
    return s && Array.isArray(s.stack) && Array.isArray(s.remaining_input);
  }).forEach(function (s, idx) {
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
  syncSelectedStateToTrace();
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
  syncSelectedStateToTrace();
}
