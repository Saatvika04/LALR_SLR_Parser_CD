#!/usr/bin/env python3
"""Flask backend for the SLR and Bison LALR parser visualization."""

import json
import os
from pathlib import Path
import subprocess

import lalr_automaton
import slr_parser
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent
_parser_setting = Path(os.environ.get("LALR_PARSER", ROOT / "build" / "parser"))
LALR_PARSER = _parser_setting if _parser_setting.is_absolute() else ROOT / _parser_setting

SAMPLES = [
    {"label": "x = 10;", "input": "x = 10;"},
    {"label": "x = 10 + 20 * 3;", "input": "x = 10 + 20 * 3;"},
    {"label": "x = (10 + 20) * 3;", "input": "x = (10 + 20) * 3;"},
    {"label": "if (x > 10) y = x + 5;", "input": "if (x > 10) y = x + 5;"},
    {"label": "x = 10 + * 20;  (invalid)", "input": "x = 10 + * 20;"},
    {"label": "empty input  (invalid)", "input": ""},
    {"label": "x = ;  (invalid)", "input": "x = ;"},
]

_LALR_REQUIRED = {"parser", "input", "tokens", "result", "error", "steps", "stats"}


def _unavailable_lalr(source, message):
    return {
        "parser": "LALR",
        "input": source,
        "tokens": [],
        "result": "UNAVAILABLE",
        "error": message,
        "steps": [],
        "stats": {"token_count": 0, "total_steps": 0, "shifts": 0, "reductions": 0, "errors": 0},
    }


def _run_lalr(source):
    """Run the compiled LALR parser.

    Returns ``(result, None)`` on success or ``(None, (error_dict, status))``
    on failure, where ``status`` is the HTTP status to report.
    """
    try:
        completed = subprocess.run(
            [str(LALR_PARSER), "--json"],
            input=source,
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return None, ({"error": "LALR parser executable is missing; run `make` first."}, 503)
    except subprocess.TimeoutExpired:
        return None, ({"error": "LALR parser timed out."}, 504)

    if completed.returncode != 0:
        app.logger.error("LALR parser failed: %s", completed.stderr.strip())
        return None, ({"error": "LALR parser execution failed; check the server log."}, 502)

    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        app.logger.error("LALR parser returned invalid JSON: %s", completed.stderr.strip())
        return None, ({"error": "LALR parser returned an invalid response."}, 502)

    if not _LALR_REQUIRED.issubset(result) or result.get("parser") != "LALR":
        return None, ({"error": "LALR parser response did not match its JSON contract."}, 502)

    return result, None


@app.route("/")
def index():
    return render_template("index.html", samples=SAMPLES)


@app.route("/parse", methods=["POST"])
def parse():
    data = request.get_json(silent=True) or {}
    source = data.get("input", "")
    if not isinstance(source, str):
        return jsonify({"error": "input must be a string"}), 400
    mode = data.get("mode", "slr")
    if not isinstance(mode, str):
        return jsonify({"error": "mode must be 'slr' or 'lalr'"}), 400
    mode = mode.lower()
    if mode == "lalr":
        result, err = _run_lalr(source)
        if err is not None:
            return jsonify(err[0]), err[1]
        return jsonify(result)
    if mode != "slr":
        return jsonify({"error": "mode must be 'slr' or 'lalr'"}), 400
    return jsonify(slr_parser.parse(source))


@app.route("/compare", methods=["POST"])
def compare():
    data = request.get_json(silent=True) or {}
    source = data.get("input", "")
    if not isinstance(source, str):
        return jsonify({"error": "input must be a string"}), 400

    slr = slr_parser.parse(source)
    lalr, err = _run_lalr(source)
    if err is not None:
        # Degrade gracefully: keep the SLR result and mark LALR unavailable.
        lalr = _unavailable_lalr(source, err[0]["error"])

    return jsonify({"input": source, "slr": slr, "lalr": lalr})


@app.route("/automaton")
def automaton():
    mode = request.args.get("mode", "slr").lower()
    if mode not in {"slr", "lalr"}:
        return jsonify({"error": "mode must be 'slr' or 'lalr'"}), 400
    if mode == "lalr":
        try:
            return jsonify(lalr_automaton.build_automaton())
        except (OSError, ValueError, KeyError) as exc:
            app.logger.error("Unable to load LALR automaton: %s", exc)
            return jsonify({"error": "LALR automaton report is unavailable; run `make` first."}), 503
    return jsonify(slr_parser.build_automaton())


if __name__ == "__main__":
    app.run(debug=True)
