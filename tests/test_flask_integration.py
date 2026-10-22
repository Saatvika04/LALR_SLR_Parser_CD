#!/usr/bin/env python3
"""Exercise the Flask endpoints when Flask is installed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as webapp

client = webapp.app.test_client()
for mode, source, expected in (
    ("lalr", "x = 10 + 20 * 3;", "ACCEPTED"),
    ("lalr", "x = 10 + * 20;", "SYNTAX ERROR"),
    ("slr", "x = 10 + 20 * 3;", "ACCEPTED"),
    ("slr", "x = 10 + * 20;", "SYNTAX ERROR"),
):
    response = client.post("/parse", json={"mode": mode, "input": source})
    assert response.status_code == 200
    result = response.get_json()
    assert result["result"] == expected
    assert result["parser"] == mode.upper()

lalr_automaton = client.get("/automaton?mode=lalr")
assert lalr_automaton.status_code == 200
lalr_data = lalr_automaton.get_json()
assert lalr_data["parser"] == "LALR"
assert len(lalr_data["states"]) == 43
assert lalr_data["conflicts"] == [{
    "state": 40,
    "token": "ELSE",
    "type": "shift/reduce",
    "resolution": "shift",
    "note": "dangling-else: else binds to the nearest unmatched if",
}]
else_actions = [
    action for action in lalr_data["states"][40]["actions"] if action["symbol"] == "ELSE"
]
assert [action["action"] for action in else_actions] == ["shift", "reduce"]
slr_automaton = client.get("/automaton?mode=slr")
assert slr_automaton.status_code == 200
slr_data = slr_automaton.get_json()
assert slr_data["parser"] == "SLR"
assert slr_data["states"] and slr_data["first"] and slr_data["follow"]
assert slr_data["grammar"][1] == "program → assignment"

comparison = client.post("/compare", json={"input": "if (x > 10) y = x + 5;"})
assert comparison.status_code == 200
comparison_data = comparison.get_json()
assert comparison_data["slr"]["parser"] == "SLR"
assert comparison_data["slr"]["result"] == "SYNTAX ERROR"
assert comparison_data["lalr"]["parser"] == "LALR"
assert comparison_data["lalr"]["result"] == "ACCEPTED"
arithmetic_comparison = client.post("/compare", json={"input": "x = 10 + 20 * 3;"})
assert arithmetic_comparison.status_code == 200
arithmetic_data = arithmetic_comparison.get_json()
assert arithmetic_data["slr"]["result"] == "ACCEPTED"
assert arithmetic_data["lalr"]["result"] == "ACCEPTED"
assert arithmetic_data["slr"]["steps"] and arithmetic_data["lalr"]["steps"]
invalid_comparison = client.post("/compare", json={"input": "x = 10 + * 20;"})
assert invalid_comparison.status_code == 200
invalid_data = invalid_comparison.get_json()
assert invalid_data["slr"]["result"] == "SYNTAX ERROR"
assert invalid_data["lalr"]["result"] == "SYNTAX ERROR"

page = client.get("/")
assert page.status_code == 200
html = page.get_data(as_text=True)
for required_id in (
    "state-count", "slr-automaton-count", "lalr-automaton-count",
    "state-select", "state-details", "conflicts",
):
    assert f'id="{required_id}"' in html
assert "LALR Grammar Conflicts" in html
assert "State Diagram" not in html and 'id="diagram"' not in html

app_source = (Path(__file__).resolve().parents[1] / "static" / "app.js").read_text(encoding="utf-8")
style_source = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text(encoding="utf-8")
assert "renderDiagram" not in app_source and "SVG_NS" not in app_source
assert ".state-diagram" not in style_source and ".edge-label" not in style_source

invalid_mode = client.get("/automaton?mode=unknown")
assert invalid_mode.status_code == 400
print("PASS Flask parse, compare, automaton, and visualizer endpoint checks")
