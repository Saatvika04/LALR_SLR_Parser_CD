"""Read Bison's verbose LALR report in the shape used by the visualizer."""

import re
from pathlib import Path

REPORT = Path(__file__).resolve().with_name("lalr_parser.output")

PRODUCTIONS = [
    ("program", "statements"),
    ("statements", "statements statement"),
    ("statements", "statement"),
    ("statement", "assignment"),
    ("statement", "conditional"),
    ("assignment", "ID ASSIGN expression SEMICOLON"),
    ("expression", "expression PLUS term"),
    ("expression", "expression MINUS term"),
    ("expression", "term"),
    ("term", "term MULT factor"),
    ("term", "term DIV factor"),
    ("term", "factor"),
    ("factor", "ID"),
    ("factor", "NUM"),
    ("factor", "LPAREN expression RPAREN"),
    ("conditional", "IF LPAREN condition RPAREN statement"),
    ("conditional", "IF LPAREN condition RPAREN statement ELSE statement"),
    ("condition", "expression relational_operator expression"),
    ("relational_operator", "LT"),
    ("relational_operator", "GT"),
    ("relational_operator", "LE"),
    ("relational_operator", "GE"),
    ("relational_operator", "EQ"),
    ("relational_operator", "NE"),
]
PRODUCTION_TEXT = {
    index: f"{lhs} -> {rhs}" for index, (lhs, rhs) in enumerate(PRODUCTIONS, 1)
}


def _symbols_section(text, heading, next_heading):
    section = text.split(heading, 1)[1].split(next_heading, 1)[0]
    return [
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"\s+(\S+)\s+\(\d+\)", line))
    ]


def build_automaton(path=REPORT):
    text = Path(path).read_text(encoding="utf-8")
    terminals = [
        "$" if symbol == "$end" else symbol
        for symbol in _symbols_section(text, "Terminals, with rules where they appear", "Nonterminals, with rules where they appear")
        if symbol not in {"error", "$undefined"}
    ]
    nonterminals = [
        symbol
        for symbol in _symbols_section(text, "Nonterminals, with rules where they appear", "State 0")
        if symbol != "$accept"
    ]
    states = []
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
                actions["$" if symbol == "$end" else symbol] = {
                    "symbol": "$" if symbol == "$end" else symbol,
                    "action": "shift",
                    "to": int(destination),
                }
                continue
            match = re.match(r"\s*\$default\s+reduce using rule (\d+) \(.*\)\s*$", line)
            if match:
                default_reduce = int(match.group(1))
                continue
            match = re.match(r"\s*(\S+)\s+reduce using rule (\d+) \(.*\)\s*$", line)
            if match:
                symbol, production_index = match.groups()
                symbol = "$" if symbol == "$end" else symbol
                rule = int(production_index)
                actions[symbol] = {
                    "symbol": symbol,
                    "action": "reduce",
                    "production": PRODUCTION_TEXT[rule],
                    "production_index": rule,
                }
                continue
            if re.match(r"\s*\$default\s+accept\s*$", line):
                default_accept = True
                continue
            match = re.match(r"\s*([A-Za-z_][A-Za-z_0-9']*)\s+go to state (\d+)\s*$", line)
            if match:
                symbol, destination = match.groups()
                gotos.append({"symbol": symbol, "to": int(destination)})

        if default_reduce is not None:
            rule = default_reduce
            for symbol in terminals:
                if symbol not in actions:
                    actions[symbol] = {
                        "symbol": symbol,
                        "action": "reduce",
                        "production": PRODUCTION_TEXT[rule],
                        "production_index": rule,
                    }
        if default_accept:
            for symbol in terminals:
                if symbol not in actions:
                    actions[symbol] = {"symbol": symbol, "action": "accept"}

        states.append({
            "id": state_id,
            "items": items,
            "actions": [actions[symbol] for symbol in terminals if symbol in actions],
            "gotos": sorted(gotos, key=lambda item: item["symbol"]),
        })

    if not states:
        raise ValueError(f"No parser states found in {path}")
    return {
        "parser": "LALR",
        "terminals": [symbol for symbol in terminals if symbol != "$"],
        "nonterminals": nonterminals,
        "grammar": [f"{lhs} → {rhs}" for lhs, rhs in PRODUCTIONS],
        "states": states,
        "conflicts": re.findall(r"(?m)^State \d+ conflicts:.*$", text),
    }
