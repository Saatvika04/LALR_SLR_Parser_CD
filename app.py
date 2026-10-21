#!/usr/bin/env python3
"""Flask backend for the parser visualization UI.

Serves the frontend and exposes the SLR parser (and, later, Deepak's LALR
bison parser) as JSON endpoints.

Run:  python3 app.py   then open http://127.0.0.1:5000
"""

import slr_parser
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

SAMPLES = [
    {"label": "x = 10;", "input": "x = 10;"},
    {"label": "x = 10 + 20 * 3;", "input": "x = 10 + 20 * 3;"},
    {"label": "x = (10 + 20) * 3;", "input": "x = (10 + 20) * 3;"},
    {"label": "x = 10 + * 20;  (invalid)", "input": "x = 10 + * 20;"},
    {"label": "empty input  (invalid)", "input": ""},
]


@app.route("/")
def index():
    return render_template("index.html", samples=SAMPLES)


@app.route("/parse", methods=["POST"])
def parse():
    data = request.get_json(silent=True) or {}
    source = data.get("input", "")
    mode = data.get("mode", "slr").lower()
    if mode == "lalr":
        return jsonify({
            "parser": "LALR",
            "input": source,
            "tokens": [],
            "result": "NOT AVAILABLE",
            "error": "LALR trace is not wired up yet (Deepak's bison parser is pending).",
            "steps": [],
            "stats": {"token_count": 0, "total_steps": 0, "shifts": 0, "reductions": 0, "errors": 0},
        })
    return jsonify(slr_parser.parse(source))


@app.route("/automaton")
def automaton():
    return jsonify(slr_parser.build_automaton())


if __name__ == "__main__":
    app.run(debug=True)
