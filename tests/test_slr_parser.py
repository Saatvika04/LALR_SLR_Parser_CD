#!/usr/bin/env python3
"""Small regression checks for Saatvika's existing SLR implementation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slr_parser


accepted = slr_parser.parse("x = 10 + 20 * 3;")
assert accepted["parser"] == "SLR"
assert accepted["result"] == "ACCEPTED"
assert accepted["steps"][-1]["action"] == "ACCEPT"

rejected = slr_parser.parse("x = 10 + * 20;")
assert rejected["parser"] == "SLR"
assert rejected["result"] == "SYNTAX ERROR"
assert rejected["steps"][-1]["action"] == "ERROR"

automaton = slr_parser.build_automaton()
assert automaton["parser"] == "SLR"
assert automaton["states"]
print("PASS existing SLR parser and automaton checks")
