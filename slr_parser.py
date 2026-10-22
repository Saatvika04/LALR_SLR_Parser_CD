#!/usr/bin/env python3
"""Compatibility CLI for the native C SLR parser in ``build/slr_parser``."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARSER = ROOT / "build" / "slr_parser"


def _run(arguments, source=""):
    try:
        completed = subprocess.run(
            [str(PARSER), *arguments], input=source, text=True,
            capture_output=True, cwd=ROOT, check=False,
        )
    except OSError as exc:
        raise RuntimeError("Native SLR executable is unavailable; run `make` first.") from exc
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "Native SLR parser failed.")
    return completed.stdout


def parse(source):
    return json.loads(_run(["--json"], source))


def build_automaton():
    return json.loads(_run(["--automaton"]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        print(json.dumps(build_automaton(), indent=2))
    else:
        source = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
        print(json.dumps(parse(source), indent=2))
