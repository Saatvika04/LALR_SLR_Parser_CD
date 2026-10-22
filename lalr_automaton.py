"""Read Bison's verbose LALR report in the shape used by the visualizer."""

import re
from pathlib import Path

REPORT = Path(__file__).resolve().with_name("lalr_parser.output")


def _section(text, heading, next_heading):
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"Bison report is missing its {heading!r} section")
    start += len(heading)
    end = text.find(next_heading, start)
    if end < 0:
        raise ValueError(f"Bison report is missing its {next_heading!r} section")
    return text[start:end]


def _symbols_section(text, heading, next_heading):
    section = _section(text, heading, next_heading)
    return [
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"\s+(\S+)\s+\(\d+\)", line))
    ]


def _parse_productions(text):
    grammar = _section(text, "Grammar\n", "Terminals, with rules where they appear")
    productions = {}
    current_lhs = None
    for line in grammar.splitlines():
        rule = re.match(r"\s*(\d+)\s+([A-Za-z_][A-Za-z_0-9']*):\s*(.*?)\s*$", line)
        if rule:
            index, current_lhs, rhs = rule.groups()
            index = int(index)
        else:
            alternative = re.match(r"\s*(\d+)\s+\|\s*(.*?)\s*$", line)
            if alternative and current_lhs is not None:
                index, rhs = alternative.groups()
                index = int(index)
            else:
                continue
        # Rule zero is Bison's internal augmented start production.
        if index:
            productions[index] = f"{current_lhs} → {' '.join(rhs.split())}"
    if not productions:
        raise ValueError("Bison report contains no grammar productions")
    return productions


def _add_action(actions, action):
    options = actions.setdefault(action["symbol"], [])
    if action not in options:
        options.append(action)


def _reduce_action(symbol, rule, production_text):
    try:
        production = production_text[rule]
    except KeyError as exc:
        raise ValueError(f"Bison report references unknown production {rule}") from exc
    return {
        "symbol": symbol,
        "action": "reduce",
        "production": production,
        "production_index": rule,
    }


def _parse_conflicts(state_id, body):
    conflicts = []
    for match in re.finditer(
        r"(?m)^\s+(shift/reduce|reduce/reduce) conflict on token (\S+):", body
    ):
        conflict_type, token = match.groups()
        if conflict_type == "shift/reduce":
            resolution = "shift"
            note = (
                "dangling-else: else binds to the nearest unmatched if"
                if token == "ELSE"
                else "Bison resolves shift/reduce conflicts by shifting"
            )
        else:
            resolution = "reduce"
            note = "Bison resolves reduce/reduce conflicts using the earlier grammar rule"
        conflicts.append({
            "state": state_id,
            "token": "$" if token == "$end" else token,
            "type": conflict_type,
            "resolution": resolution,
            "note": note,
        })
    return conflicts


def build_automaton(path=REPORT):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Unable to read Bison report {path}: {exc}") from exc

    terminal_symbols = _symbols_section(
        text, "Terminals, with rules where they appear", "Nonterminals, with rules where they appear"
    )
    terminals = [
        "$" if symbol == "$end" else symbol
        for symbol in terminal_symbols
        if symbol not in {"error", "$undefined", "INVALID"}
    ]
    nonterminals = [
        symbol
        for symbol in _symbols_section(
            text, "Nonterminals, with rules where they appear", "State 0"
        )
        if symbol != "$accept"
    ]
    production_text = _parse_productions(text)

    states = []
    conflicts = []
    chunks = re.split(r"(?m)^State (\d+)\s*$", text)
    for index in range(1, len(chunks), 2):
        state_id = int(chunks[index])
        body = chunks[index + 1]
        items = []
        reading_items = False
        for line in body.splitlines():
            if not line.strip():
                if reading_items:
                    break
                continue
            reading_items = True
            items.append(line.strip())

        actions = {}
        gotos = []
        default_reduce = None
        default_accept = False
        for line in body.splitlines():
            match = re.match(r"\s*(\S+)\s+shift, and go to state (\d+)\s*$", line)
            if match:
                symbol, destination = match.groups()
                symbol = "$" if symbol == "$end" else symbol
                _add_action(actions, {
                    "symbol": symbol,
                    "action": "shift",
                    "to": int(destination),
                })
                continue

            match = re.match(r"\s*(\S+)\s+reduce using rule (\d+) \(.*\)\s*$", line)
            if not match:
                match = re.match(
                    r"\s*(\S+)\s+\[reduce using rule (\d+) \(.*\)\]\s*$", line
                )
            if match:
                symbol, production_index = match.groups()
                symbol = "$" if symbol == "$end" else symbol
                _add_action(actions, _reduce_action(symbol, int(production_index), production_text))
                continue

            match = re.match(r"\s*\$default\s+reduce using rule (\d+) \(.*\)\s*$", line)
            if match:
                default_reduce = int(match.group(1))
                continue
            if re.match(r"\s*\$default\s+accept\s*$", line):
                default_accept = True
                continue

            match = re.match(r"\s*([A-Za-z_][A-Za-z_0-9']*)\s+go to state (\d+)\s*$", line)
            if match:
                symbol, destination = match.groups()
                gotos.append({"symbol": symbol, "to": int(destination)})

        if default_reduce is not None:
            for symbol in terminals:
                if symbol not in actions:
                    _add_action(actions, _reduce_action(symbol, default_reduce, production_text))
        if default_accept:
            for symbol in terminals:
                if symbol not in actions:
                    _add_action(actions, {"symbol": symbol, "action": "accept"})

        states.append({
            "id": state_id,
            "items": items,
            "actions": [action for symbol in terminals for action in actions.get(symbol, [])],
            "gotos": sorted(gotos, key=lambda item: item["symbol"]),
        })
        conflicts.extend(_parse_conflicts(state_id, body))

    if not states:
        raise ValueError(f"No parser states found in {path}")
    states.sort(key=lambda state: state["id"])
    if [state["id"] for state in states] != list(range(len(states))):
        raise ValueError(f"Bison report has missing or duplicate state IDs in {path}")

    return {
        "parser": "LALR",
        "terminals": [symbol for symbol in terminals if symbol != "$"],
        "nonterminals": nonterminals,
        "grammar": [production_text[index] for index in sorted(production_text)],
        "states": states,
        "conflicts": conflicts,
    }
