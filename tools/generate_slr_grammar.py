#!/usr/bin/env python3
"""Generate the native SLR grammar from the shared Bison grammar source."""

import re
import sys
from pathlib import Path


def read_grammar(path):
    source = Path(path).read_text(encoding="utf-8")
    sections = source.split("%%")
    if len(sections) < 3:
        raise ValueError("Bison grammar must contain two %% separators")
    tokens = re.search(r"(?m)^%token\s+(.+)$", sections[0])
    if not tokens:
        raise ValueError("Bison grammar has no %token declaration")
    token_names = tokens.group(1).split()
    productions = {}
    full_rules = []
    for match in re.finditer(r"(?m)^\s*([A-Za-z_][A-Za-z_0-9]*)\s*:\s*(.*?)\s*;\s*$", sections[1]):
        lhs, alternatives = match.groups()
        productions[lhs] = [tuple(alt.split()) for alt in alternatives.split("|")]
        full_rules.extend((lhs, tuple(alt.split())) for alt in alternatives.split("|"))
    required = ("assignment", "expression", "term", "factor")
    if any(name not in productions for name in required):
        raise ValueError("Bison grammar is missing an SLR-shared production group")

    terminals = ["ID", "NUM", "ASSIGN", "SEMICOLON", "PLUS", "MINUS", "MULT", "DIV", "LPAREN", "RPAREN"]
    if any(token not in token_names for token in terminals):
        raise ValueError("Bison grammar is missing an SLR terminal")
    rules = [("S'", ("program",)), ("program", ("assignment",))]
    for name in required:
        rules.extend((name, rhs) for rhs in productions[name])
    nonterminals = ["S'", "program", "assignment", "expression", "term", "factor"]
    for lhs, rhs in rules:
        if not rhs or lhs not in nonterminals or any(sym not in terminals and sym not in nonterminals for sym in rhs):
            raise ValueError(f"SLR projection contains an unsupported symbol in {lhs}: {rhs}")
    if not full_rules or max(len(rhs) for _, rhs in full_rules) > 7:
        raise ValueError("Bison productions cannot be represented in the parser trace metadata")
    return terminals, nonterminals, rules, full_rules


def c_string(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def generate(source, output):
    terminals, nonterminals, rules, full_rules = read_grammar(source)
    symbols = terminals + ["$", *nonterminals]
    def enum_name(name):
        if name == "S'":
            return "S_PRIME"
        if name == "$":
            return "EOF_SYMBOL"
        return re.sub(r'[^A-Za-z0-9]', '_', name).upper()

    enum_lines = [f"    G_{enum_name(name)} = {i}," for i, name in enumerate(symbols)]
    production_lines = []
    max_rhs = max(len(rhs) for _, rhs in rules)
    for lhs, rhs in rules:
        rhs_ids = ", ".join(f"{symbols.index(sym)}" for sym in rhs)
        text = f"{lhs} -> {' '.join(rhs)}"
        production_lines.append(
            "    { " + str(symbols.index(lhs)) + ", { " + rhs_ids + " }, " + str(len(rhs)) + ", " + c_string(text) + " },"
        )
    bison_production_lines = ['    {"", {NULL}, 0, ""},']
    for lhs, rhs in full_rules:
        padded_rhs = [*rhs, *("NULL" for _ in range(7 - len(rhs)))]
        rhs_text = ", ".join("NULL" if name == "NULL" else c_string(name) for name in padded_rhs)
        text = f"{lhs} -> {' '.join(rhs)}"
        bison_production_lines.append(
            "    { " + c_string(lhs) + ", { " + rhs_text + " }, " + str(len(rhs)) + ", " + c_string(text) + " },"
        )
    header = [
        "/* Generated from lalr_parser.y by tools/generate_slr_grammar.py. */",
        "#ifndef SLR_GRAMMAR_GENERATED_H",
        "#define SLR_GRAMMAR_GENERATED_H",
        f"#define SLR_TERMINAL_COUNT {len(terminals)}",
        f"#define SLR_EOF {len(terminals)}",
        f"#define SLR_NONTERMINAL_COUNT {len(nonterminals)}",
        f"#define SLR_SYMBOL_COUNT {len(symbols)}",
        f"#define SLR_PRODUCTION_COUNT {len(rules)}",
        f"#define SLR_MAX_RHS {max_rhs}",
        "enum SlrGrammarSymbol {",
        *enum_lines,
        "};",
        "typedef struct { int lhs; int rhs[SLR_MAX_RHS]; unsigned rhs_count; const char *text; } SlrProduction;",
        "static const char *const slr_symbol_names[SLR_SYMBOL_COUNT] = {",
        "    " + ", ".join(c_string(name) for name in symbols),
        "};",
        "static const char *const slr_nonterminal_names[SLR_NONTERMINAL_COUNT] = {",
        "    " + ", ".join(c_string(name) for name in nonterminals),
        "};",
        "static const SlrProduction slr_productions[SLR_PRODUCTION_COUNT] = {",
        *production_lines,
        "};",
        "#ifdef GENERATE_LALR_PRODUCTION_METADATA",
        "static const Production productions[] = {",
        *bison_production_lines,
        "};",
        "#endif",
        "#endif",
        "",
    ]
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text("\n".join(header), encoding="utf-8")


if __name__ == "__main__":
    try:
        generate(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, IndexError) as exc:
        print(f"SLR grammar generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
