#!/usr/bin/env python3
"""Run the required samples through the compiled LALR executable."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    ("01_simple_assignment.json", "x = 10;", "ACCEPTED"),
    ("02_precedence.json", "x = 10 + 20 * 3;", "ACCEPTED"),
    ("03_parentheses.json", "x = (10 + 20) * 3;", "ACCEPTED"),
    ("04_conditional.json", "if (x > 10) y = x + 5;", "ACCEPTED"),
    ("05_invalid_operator.json", "x = 10 + * 20;", "SYNTAX ERROR"),
    ("06_empty_input.json", "", "SYNTAX ERROR"),
    ("07_missing_rhs.json", "x = ;", "SYNTAX ERROR"),
]
EXTRA = [
    ("incomplete expression", "x = 10 +"),
    ("unexpected character", "x = 10 @;"),
    ("Unicode unexpected character", "x = 10 é;"),
]
NESTED_ELSE = "if (x > 0) if (y > 0) x = 1; else x = 2;"
TOP_LEVEL = {"parser", "input", "tokens", "result", "error", "steps", "stats"}
STEP_FIELDS = {"step", "stack", "remaining_input", "action", "state", "token", "production", "goto_state"}
STAT_FIELDS = {"token_count", "total_steps", "shifts", "reductions", "errors"}


def run(parser, source):
    result = subprocess.run(
        [str(parser), "--json"], input=source, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"parser exited {result.returncode}: {result.stderr}")
    if result.stderr:
        raise AssertionError(f"unexpected parser stderr: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout was not a single JSON object: {result.stdout!r}") from exc


def validate(data, source, expected):
    assert set(data) == TOP_LEVEL, set(data)
    assert data["parser"] == "LALR"
    assert data["input"] == source
    assert data["result"] == expected
    assert isinstance(data["tokens"], list)
    assert all(set(token) == {"type", "lexeme"} for token in data["tokens"])
    assert data["stats"]["token_count"] == len(data["tokens"])
    assert set(data["stats"]) == STAT_FIELDS

    steps = data["steps"]
    assert steps and all(set(step) == STEP_FIELDS for step in steps)
    consumed = 0
    action_counts = {"SHIFT": 0, "REDUCE": 0, "ERROR": 0}
    for index, step in enumerate(steps):
        assert step["step"] == index
        assert isinstance(step["state"], int)
        assert isinstance(step["stack"], list) and all(isinstance(item, str) for item in step["stack"])
        assert len(step["stack"]) % 2 == 1
        assert step["stack"][0].isdigit()
        assert all(step["stack"][offset].isdigit() for offset in range(2, len(step["stack"]), 2))
        input_cursor = consumed + (step["action"] == "SHIFT")
        expected_input = [token["lexeme"] for token in data["tokens"][input_cursor:]] + ["$"]
        assert step["remaining_input"] == expected_input, (index, step["remaining_input"], expected_input)
        assert step["state"] == int(step["stack"][-1])
        if step["action"] == "SHIFT":
            assert step["token"] == data["tokens"][consumed]
            assert step["production"] is None and step["goto_state"] is None
            consumed += 1
            action_counts["SHIFT"] += 1
        else:
            assert step["token"] is None
        if step["action"] == "REDUCE":
            assert isinstance(step["production"], str) and isinstance(step["goto_state"], int)
            assert step["goto_state"] == step["state"]
            action_counts["REDUCE"] += 1
        else:
            assert step["production"] is None and step["goto_state"] is None
        if step["action"] == "ERROR":
            action_counts["ERROR"] += 1

    assert steps[0]["action"] == "INIT"
    assert steps[0]["stack"] == ["0"]
    assert consumed == len(data["tokens"]) if expected == "ACCEPTED" else consumed <= len(data["tokens"])
    assert steps[-1]["action"] == ("ACCEPT" if expected == "ACCEPTED" else "ERROR")
    if expected == "ACCEPTED":
        assert data["error"] is None
    else:
        assert isinstance(data["error"], str) and data["error"]
    stats = data["stats"]
    assert stats["total_steps"] == len(steps)
    assert stats["shifts"] == action_counts["SHIFT"]
    assert stats["reductions"] == action_counts["REDUCE"]
    assert stats["errors"] == action_counts["ERROR"] == (0 if expected == "ACCEPTED" else 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parser", required=True, type=Path)
    args = parser.parse_args()
    executable = args.parser.resolve()
    outputs = []
    for filename, source, expected in SAMPLES:
        data = run(executable, source)
        validate(data, source, expected)
        outputs.append((filename, data))
        print(f"PASS {filename}: {expected}")
    for label, source in EXTRA:
        data = run(executable, source)
        validate(data, source, "SYNTAX ERROR")
        print(f"PASS {label}: SYNTAX ERROR")

    nested_else = run(executable, NESTED_ELSE)
    validate(nested_else, NESTED_ELSE, "ACCEPTED")
    assert any(
        step["production"] == "conditional -> IF LPAREN condition RPAREN statement ELSE statement"
        for step in nested_else["steps"]
    )
    print("PASS dangling-else input: ELSE is shifted into the nearest unmatched conditional")

    table = subprocess.run([str(executable), "--table"], text=True, capture_output=True, check=False)
    assert table.returncode == 0 and "State 0" in table.stdout and "shift, and go to state" in table.stdout
    invalid_cli = subprocess.run([str(executable), "--unknown"], text=True, capture_output=True, check=False)
    assert invalid_cli.returncode != 0 and "Usage:" in invalid_cli.stderr
    print("PASS --table output and invalid CLI argument handling")

    precedence = outputs[1][1]["steps"]
    multiply = next(i for i, step in enumerate(precedence) if step["production"] == "term -> term MULT factor")
    addition = next(i for i, step in enumerate(precedence) if step["production"] == "expression -> expression PLUS term")
    assert multiply < addition, (multiply, addition)
    print("PASS multiplication reduces before addition")

    trace_dir = ROOT / "traces"
    trace_dir.mkdir(exist_ok=True)
    for filename, data in outputs:
        (trace_dir / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(outputs)} sample traces to {trace_dir.relative_to(ROOT)}/")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
