#!/usr/bin/env python3
"""Validate the Bison report adapter used by the LALR automaton endpoint."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lalr_automaton


automaton = lalr_automaton.build_automaton()
assert automaton["parser"] == "LALR"
assert len(automaton["states"]) == 43
assert set(automaton) == {"parser", "terminals", "nonterminals", "grammar", "states", "conflicts"}
assert set(automaton["terminals"]) == {
    "ID", "NUM", "ASSIGN", "SEMICOLON", "PLUS", "MINUS", "MULT", "DIV",
    "LPAREN", "RPAREN", "IF", "ELSE", "LT", "GT", "LE", "GE", "EQ", "NE",
}
assert set(automaton["nonterminals"]) == {
    "program", "statements", "statement", "assignment", "conditional",
    "expression", "term", "factor", "condition", "relational_operator",
}
assert len(automaton["grammar"]) == 24
assert all(" → " in production for production in automaton["grammar"])
assert [state["id"] for state in automaton["states"]] == list(range(43))
for state in automaton["states"]:
    assert set(state) == {"id", "items", "actions", "gotos"}
    assert state["items"]
    assert all(isinstance(item, str) for item in state["items"])
    assert all(set(go) == {"symbol", "to"} and 0 <= go["to"] < 43 for go in state["gotos"])
    for action in state["actions"]:
        assert "symbol" in action and action["action"] in {"shift", "reduce", "accept"}
        if action["action"] == "shift":
            assert set(action) == {"symbol", "action", "to"}
            assert 0 <= action["to"] < 43
        elif action["action"] == "reduce":
            assert set(action) == {"symbol", "action", "production", "production_index"}
        else:
            assert set(action) == {"symbol", "action"}

assert automaton["conflicts"] == [{
    "state": 40,
    "token": "ELSE",
    "type": "shift/reduce",
    "resolution": "shift",
    "note": "dangling-else: else binds to the nearest unmatched if",
}]
else_actions = [
    action for action in automaton["states"][40]["actions"] if action["symbol"] == "ELSE"
]
assert [(action["action"], action.get("to"), action.get("production_index")) for action in else_actions] == [
    ("shift", 41, None), ("reduce", None, 16)
]

with TemporaryDirectory() as temp_dir:
    malformed = Path(temp_dir) / "malformed.output"
    malformed.write_text("not a Bison report", encoding="utf-8")
    try:
        lalr_automaton.build_automaton(malformed)
    except ValueError as exc:
        assert "Terminals" in str(exc)
    else:
        raise AssertionError("malformed report should fail clearly")

print("PASS LALR automaton adapter (43 states, structured dangling-else conflict)")
