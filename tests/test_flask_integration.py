#!/usr/bin/env python3
"""Exercise the Flask endpoints when Flask is installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import flask  # noqa: F401
except ImportError:
    print("SKIP Flask endpoint checks: Flask is not installed")
    raise SystemExit(0)

import app as webapp

client = webapp.app.test_client()
for mode, source, expected in (
    ("lalr", "x = 10 + 20 * 3;", "ACCEPTED"),
    ("lalr", "x = 10 + * 20;", "SYNTAX ERROR"),
    ("slr", "x = 10 + 20 * 3;", "ACCEPTED"),
):
    response = client.post("/parse", json={"mode": mode, "input": source})
    assert response.status_code == 200
    result = response.get_json()
    assert result["result"] == expected
    assert result["parser"] == mode.upper()

lalr_automaton = client.get("/automaton?mode=lalr")
assert lalr_automaton.status_code == 200
assert lalr_automaton.get_json()["parser"] == "LALR"
slr_automaton = client.get("/automaton?mode=slr")
assert slr_automaton.status_code == 200
assert slr_automaton.get_json()["parser"] == "SLR"
print("PASS Flask SLR/LALR parse and automaton endpoint checks")
