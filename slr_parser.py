#!/usr/bin/env python3
"""SLR(1) parser with FIRST/FOLLOW, LR(0) item-set, and SLR-table
construction, plus a step-by-step trace emitted as JSON (same contract as
PRD 4). Run:

    python3 slr_parser.py "x = 10 + 20 * 3;"   # -> trace JSON
    python3 slr_parser.py --table              # -> FIRST/FOLLOW + automaton JSON

SLR scope: assignment + arithmetic only (no if/else -- the dangling-else
grammar is not cleanly SLR(1), which is the whole LALR-vs-SLR comparison).
"""

import sys
import json
import re
from collections import defaultdict

EOF = "$"

# --------------------------------------------------------------------------
# Lexer (matches the shared token table; the SLR grammar only uses the subset
# ID NUM ASSIGN SEMICOLON PLUS MINUS MULT DIV LPAREN RPAREN)
# --------------------------------------------------------------------------
_TOKEN_RE = re.compile(
    r"""
      (?P<WS>\s+)
    | (?P<IF>if\b)
    | (?P<ELSE>else\b)
    | (?P<LE><=)
    | (?P<GE>>=)
    | (?P<EQ>==)
    | (?P<NE>!=)
    | (?P<ID>[a-zA-Z_][a-zA-Z0-9_]*)
    | (?P<NUM>[0-9]+)
    | (?P<ASSIGN>=)
    | (?P<PLUS>\+)
    | (?P<MINUS>-)
    | (?P<MULT>\*)
    | (?P<DIV>/)
    | (?P<LT><)
    | (?P<GT>>)
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<SEMICOLON>;)
    | (?P<INVALID>.)
    """,
    re.VERBOSE,
)


class LexError(Exception):
    pass


def lex(source):
    tokens = []
    for m in _TOKEN_RE.finditer(source):
        kind = m.lastgroup
        if kind == "WS":
            continue
        if kind == "INVALID":
            raise LexError("Unexpected character %r" % m.group())
        tokens.append({"type": kind, "lexeme": m.group()})
    return tokens


# --------------------------------------------------------------------------
# Grammar (augmented with S'). SLR(1) -- arithmetic + assignment subset.
# --------------------------------------------------------------------------
PRODUCTIONS = [
    ("S'", ("program",)),
    ("program", ("assignment",)),
    ("assignment", ("ID", "ASSIGN", "expression", "SEMICOLON")),
    ("expression", ("expression", "PLUS", "term")),
    ("expression", ("expression", "MINUS", "term")),
    ("expression", ("term",)),
    ("term", ("term", "MULT", "factor")),
    ("term", ("term", "DIV", "factor")),
    ("term", ("factor",)),
    ("factor", ("ID",)),
    ("factor", ("NUM",)),
    ("factor", ("LPAREN", "expression", "RPAREN")),
]

TERMINALS = ["ID", "NUM", "ASSIGN", "SEMICOLON", "PLUS", "MINUS", "MULT", "DIV", "LPAREN", "RPAREN"]
NONTERMINALS = ["S'", "program", "assignment", "expression", "term", "factor"]


def prod_str(i):
    lhs, rhs = PRODUCTIONS[i]
    return lhs + " -> " + " ".join(rhs)


def item_str(i, dot):
    lhs, rhs = PRODUCTIONS[i]
    parts = list(rhs)
    parts.insert(dot, ".")
    return lhs + " -> " + " ".join(parts)


# --------------------------------------------------------------------------
# FIRST / FOLLOW
# --------------------------------------------------------------------------
def compute_first():
    first = defaultdict(set)
    for t in TERMINALS:
        first[t].add(t)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODUCTIONS:
            nullable = True
            for sym in rhs:
                for x in first[sym]:
                    if x != "" and x not in first[lhs]:
                        first[lhs].add(x)
                        changed = True
                if "" not in first[sym]:
                    nullable = False
                    break
            if nullable and "" not in first[lhs]:
                first[lhs].add("")
                changed = True
    return first


def compute_follow(first):
    follow = defaultdict(set)
    follow["S'"].add(EOF)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODUCTIONS:
            trailer = set(follow[lhs])
            for sym in reversed(rhs):
                if sym in NONTERMINALS:
                    for x in trailer:
                        if x not in follow[sym]:
                            follow[sym].add(x)
                            changed = True
                    if "" in first[sym]:
                        trailer |= first[sym] - {""}
                    else:
                        trailer = set(first[sym])
                else:
                    trailer = set(first[sym])
    return follow


# --------------------------------------------------------------------------
# LR(0) item sets (canonical collection) and SLR table
# --------------------------------------------------------------------------
def closure(items):
    result = set(items)
    changed = True
    while changed:
        changed = False
        for i, dot in list(result):
            rhs = PRODUCTIONS[i][1]
            if dot < len(rhs) and rhs[dot] in NONTERMINALS:
                sym = rhs[dot]
                for j, (l2, _) in enumerate(PRODUCTIONS):
                    if l2 == sym and (j, 0) not in result:
                        result.add((j, 0))
                        changed = True
    return frozenset(result)


def goto(items, sym):
    moved = set()
    for i, dot in items:
        rhs = PRODUCTIONS[i][1]
        if dot < len(rhs) and rhs[dot] == sym:
            moved.add((i, dot + 1))
    return closure(moved) if moved else None


def build_states():
    start = closure({(0, 0)})
    states = [start]
    ids = {start: 0}
    transitions = {}
    i = 0
    while i < len(states):
        for sym in TERMINALS + NONTERMINALS:
            g = goto(states[i], sym)
            if g is None:
                continue
            if g not in ids:
                ids[g] = len(states)
                states.append(g)
            transitions[(i, sym)] = ids[g]
        i += 1
    return states, transitions


def build_table(first, follow):
    states, transitions = build_states()
    action = {}
    gotos = {}
    for si, s in enumerate(states):
        for i, dot in s:
            lhs, rhs = PRODUCTIONS[i]
            if dot < len(rhs):
                a = rhs[dot]
                if a in TERMINALS:
                    to = transitions[(si, a)]
                    key = (si, a)
                    if key in action and action[key] != ("shift", to):
                        raise RuntimeError("shift/reduce conflict in state %d on %s" % (si, a))
                    action[key] = ("shift", to)
            else:
                if lhs == "S'":
                    action[(si, EOF)] = ("accept", None)
                else:
                    for a in follow[lhs]:
                        key = (si, a)
                        if key in action:
                            raise RuntimeError("conflict in state %d on %s (reduce by %s)" % (si, a, prod_str(i)))
                        action[key] = ("reduce", i)
        for nt in NONTERMINALS:
            if (si, nt) in transitions:
                gotos[(si, nt)] = transitions[(si, nt)]
    return states, transitions, action, gotos


# --------------------------------------------------------------------------
# Trace / parse
# --------------------------------------------------------------------------
def parse(source):
    try:
        tokens = lex(source)
    except LexError as exc:
        return {
            "parser": "SLR",
            "input": source,
            "tokens": [],
            "result": "SYNTAX ERROR",
            "error": str(exc),
            "steps": [],
            "stats": {"token_count": 0, "total_steps": 0, "shifts": 0, "reductions": 0, "errors": 1},
        }

    tokens_out = [{"type": t["type"], "lexeme": t["lexeme"]} for t in tokens]

    first = compute_first()
    follow = compute_follow(first)
    try:
        _states, _transitions, action, gotos = build_table(first, follow)
    except RuntimeError as exc:
        return {
            "parser": "SLR",
            "input": source,
            "tokens": tokens_out,
            "result": "CONFIGURATION ERROR",
            "error": str(exc),
            "steps": [],
            "stats": {"token_count": len(tokens), "total_steps": 0, "shifts": 0, "reductions": 0, "errors": 1},
        }

    input_tokens = tokens + [{"type": EOF, "lexeme": "$"}]
    state_stack = [0]
    sym_stack = []

    def display_stack():
        out = [str(state_stack[0])]
        for i, s in enumerate(sym_stack):
            out.append(s)
            out.append(str(state_stack[i + 1]))
        return out

    def display_input(ip):
        return [(t["lexeme"] if t["type"] != EOF else "$") for t in input_tokens[ip:]]

    steps = []
    stats = {"token_count": len(tokens), "total_steps": 0, "shifts": 0, "reductions": 0, "errors": 0}

    def push(action_name, state, token=None, production=None, goto_state=None):
        steps.append({
            "step": len(steps),
            "stack": display_stack(),
            "remaining_input": display_input(ip),
            "action": action_name,
            "state": state,
            "token": token,
            "production": production,
            "goto_state": goto_state,
        })

    ip = 0
    push("INIT", state_stack[-1])

    while True:
        s = state_stack[-1]
        a = input_tokens[ip]["type"]
        act = action.get((s, a))
        if act is None:
            stats["errors"] += 1
            push("ERROR", s)
            stats["total_steps"] = len(steps)
            return {
                "parser": "SLR",
                "input": source,
                "tokens": tokens_out,
                "result": "SYNTAX ERROR",
                "error": "Unexpected token %s (lexeme %r)" % (a, input_tokens[ip]["lexeme"]),
                "steps": steps,
                "stats": stats,
            }
        kind, val = act
        if kind == "shift":
            t = input_tokens[ip]
            sym_stack.append(a)
            state_stack.append(val)
            ip += 1
            stats["shifts"] += 1
            push("SHIFT", val, token={"type": a, "lexeme": t["lexeme"]})
        elif kind == "reduce":
            lhs, rhs = PRODUCTIONS[val]
            for _ in range(len(rhs)):
                sym_stack.pop()
                state_stack.pop()
            to = gotos[(state_stack[-1], lhs)]
            sym_stack.append(lhs)
            state_stack.append(to)
            stats["reductions"] += 1
            push("REDUCE", to, production=prod_str(val), goto_state=to)
        elif kind == "accept":
            push("ACCEPT", s)
            stats["total_steps"] = len(steps)
            return {
                "parser": "SLR",
                "input": source,
                "tokens": tokens_out,
                "result": "ACCEPTED",
                "error": None,
                "steps": steps,
                "stats": stats,
            }
        stats["total_steps"] = len(steps)


# --------------------------------------------------------------------------
# Automaton / table export (for the parsing-table and state-diagram panels)
# --------------------------------------------------------------------------
def build_automaton():
    first = compute_first()
    follow = compute_follow(first)
    states, _transitions, action, gotos = build_table(first, follow)
    out = []
    for si, s in enumerate(states):
        items = sorted(item_str(i, d) for i, d in s)
        actions = []
        for (st, sym), (kind, val) in sorted(action.items()):
            if st != si:
                continue
            if kind == "shift":
                actions.append({"symbol": sym, "action": "shift", "to": val})
            elif kind == "reduce":
                actions.append({"symbol": sym, "action": "reduce", "production": prod_str(val), "production_index": val})
            else:
                actions.append({"symbol": sym, "action": "accept"})
        g = [{"symbol": nt, "to": to} for (st, nt), to in sorted(gotos.items()) if st == si]
        out.append({"id": si, "items": items, "actions": actions, "gotos": g})
    return {
        "parser": "SLR",
        "terminals": TERMINALS,
        "nonterminals": [n for n in NONTERMINALS if n != "S'"],
        "first": {n: sorted(first[n]) for n in NONTERMINALS},
        "follow": {n: sorted(follow[n]) for n in NONTERMINALS},
        "states": out,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--table":
        print(json.dumps(build_automaton(), indent=2))
    else:
        src = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
        print(json.dumps(parse(src), indent=2))
