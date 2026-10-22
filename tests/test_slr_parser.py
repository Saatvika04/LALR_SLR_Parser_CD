#!/usr/bin/env python3
"""Regression checks against the native C SLR parser and automaton."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(executable, arguments, source=""):
    result = subprocess.run([str(executable), *arguments], input=source, text=True,
                            capture_output=True, cwd=ROOT, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parser", required=True, type=Path)
    executable = parser.parse_args().parser.resolve()

    for source, expected in (
        ("x = 10 + 20 * 3;", "ACCEPTED"),
        ("x = (10 + 20) * 3;", "ACCEPTED"),
        ("x = 10 - 3 / 2;", "ACCEPTED"),
        ("x = 10 + * 20;", "SYNTAX ERROR"),
        ("x = ;", "SYNTAX ERROR"),
        ("", "SYNTAX ERROR"),
        ("if (x > 10) y = x + 5;", "SYNTAX ERROR"),
    ):
        result = run(executable, ["--json"], source)
        assert result["parser"] == "SLR"
        assert result["result"] == expected
        assert result["stats"]["total_steps"] == len(result["steps"])
        assert result["stats"]["token_count"] == len(result["tokens"])
        assert result["steps"]
        assert result["steps"][-1]["action"] == ("ACCEPT" if expected == "ACCEPTED" else "ERROR")
    lexical_error = run(executable, ["--json"], "x = 10 @;")
    assert lexical_error["result"] == "SYNTAX ERROR" and lexical_error["tokens"] == []
    assert lexical_error["error"] == "Unexpected character '@'"
    assert lexical_error["stats"]["errors"] == 1
    unicode_error = run(executable, ["--json"], "x = 10 é;")
    assert unicode_error["result"] == "SYNTAX ERROR" and unicode_error["tokens"] == []
    assert unicode_error["error"] == "Unexpected character 'é'"

    automaton = run(executable, ["--automaton"])
    assert automaton["parser"] == "SLR"
    assert set(automaton) == {"parser", "terminals", "nonterminals", "grammar", "conflicts", "first", "follow", "states"}
    assert automaton["states"] and automaton["first"] and automaton["follow"]
    assert automaton["grammar"][0] == "S' → program"
    assert automaton["grammar"][1] == "program → assignment"
    assert any(action["action"] == "reduce" for state in automaton["states"] for action in state["actions"])
    print(f"PASS native C SLR parser and automaton ({len(automaton['states'])} LR(0) states)")


if __name__ == "__main__":
    main()
