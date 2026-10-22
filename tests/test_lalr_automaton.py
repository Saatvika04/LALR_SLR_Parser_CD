#!/usr/bin/env python3
"""Validate the Bison report adapter used by the LALR automaton endpoint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lalr_automaton


automaton = lalr_automaton.build_automaton()
assert automaton["parser"] == "LALR"
assert len(automaton["states"]) > 1
assert "conditional" in automaton["nonterminals"]
assert any(state["items"] for state in automaton["states"])
assert any(action["action"] == "shift" for state in automaton["states"] for action in state["actions"])
assert any(action["action"] == "reduce" for state in automaton["states"] for action in state["actions"])
assert any(state["gotos"] for state in automaton["states"])
assert automaton["conflicts"] == ["State 40 conflicts: 1 shift/reduce"]
assert any(
    action.get("symbol") == "ELSE" and action["action"] == "shift"
    for state in automaton["states"] for action in state["actions"]
)
print(f"PASS LALR automaton adapter ({len(automaton['states'])} states, {automaton['conflicts'][0]})")
