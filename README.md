# LALR and SLR Parser Visualizer

Compiler Design Lab project comparing a native C SLR parser with a Bison-generated C LALR parser. Both parsers use the shared Flex lexer. The SLR grammar covers assignments and arithmetic expressions. The LALR grammar also supports `if`/`else` statements and relational conditions. The Flask visualizer invokes both compiled parsers on the same input and displays their results and traces, along with a selected parser's automaton, parsing table, and grammar conflicts.

## Prerequisites and setup

Install Python 3, GNU Make, GCC, Bison, and Flex. Create and activate a virtual environment, then install Flask:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Build the parser and lexer from source:

```sh
make
```

This builds `build/parser` (LALR), `build/slr_parser` (SLR), and `build/lexer`, and writes Bison's report to `lalr_parser.output`. The SLR parser constructs canonical LR(0) states and FOLLOW-based SLR actions in C. The build generates its shared assignment and arithmetic productions from `lalr_parser.y`; only the SLR augmented start and `program → assignment` rules are SLR-specific. The root-level `parser`, `lexer`, and generated C files may be local untracked artifacts; the Makefile preserves existing root paths and uses the `build/` executables for project commands.

## Run the tests

Activate `.venv` first, then run:

```sh
make test
python tests/test_flask_integration.py
```

The suite checks LALR trace JSON, all seven saved samples, precedence, invalid input, dangling-`else`, the LALR automaton adapter, the native C SLR parser and automaton, Flask endpoints, and lexer output. The LALR trace harness regenerates the seven JSON files under `traces/` from the built parser and verifies their contracts.

## Parser commands

```sh
build/parser                 # Review 1 text output
build/parser --json < input.txt
build/parser --table         # Bison parser report
build/slr_parser --json < input.txt
build/slr_parser --automaton # SLR states, tables, FIRST and FOLLOW as JSON
build/lexer < input.txt      # standalone lexer
```

JSON mode emits the parser result, tokens, step-by-step trace, and statistics. Each trace step contains the parser stack, remaining input, action, current state, and action-specific token or production/GOTO fields.

## Launch the visualizer

After building and activating the virtual environment:

```sh
python app.py
```

Open the local address printed by Flask (the app uses Flask's default development server). Enter a sample such as `if (x > 10) y = x + 5;` and choose **Run Parser** to compare the SLR and LALR results and traces. Use the automaton context selector to switch the grammar and parsing table between SLR and LALR. The LALR dangling-`else` conflict is shown in the LALR Grammar Conflicts panel. Choose a state from **Inspect state**, or use **Prev/Next** to follow the active parser trace; the State Details panel lists that state's LR items, actions, and gotos.

## HTTP API

- `POST /parse` accepts `{"input": "...", "mode": "slr"}` or `{"input": "...", "mode": "lalr"}` and returns one parser's result and trace.
- `POST /compare` accepts `{"input": "..."}` and returns `{"input": "...", "slr": <SLR result>, "lalr": <LALR result>}`.
- `GET /automaton?mode=slr` returns the SLR automaton, including its SLR-specific `first` and `follow` fields.
- `GET /automaton?mode=lalr` adapts the committed Bison report `lalr_parser.output` to the shared automaton fields. It does not add SLR-only `first` or `follow` values.

The LALR automaton includes `parser`, `terminals`, `nonterminals`, the complete `grammar` production list, and `states`. Each state has a numeric `id`, human-readable LR `items`, `actions`, and `gotos`. Shift actions contain `symbol`, `action: "shift"`, and destination `to`; reduce actions contain `symbol`, `action: "reduce"`, `production`, and `production_index`; accept actions contain `symbol` and `action: "accept"`. The adapter reads these from the Bison report rather than constructing state transitions from hardcoded state data. The SLR automaton is built by the native SLR executable from its LR(0) collection and FOLLOW sets.

The current grammar has 43 LALR states and a dangling-`else` shift/reduce conflict in state 40 on `ELSE`. The report adapter returns a structured conflict with `state`, `token`, `type`, `resolution`, and `note`. Bison resolves it by shifting, so `else` binds to the nearest unmatched `if`; state 40 retains both the shift and reduce actions in its automaton data.

## Implementation languages

The runtime lexing and parsing paths are Flex/C: `lexer.l` supplies tokens to both the generated Bison parser and the native C SLR parser. `slr_parser.c` computes LR(0) closures, the canonical state collection, FIRST/FOLLOW data, SLR actions/GOTOs, and trace JSON. `lalr_parser.y` defines the LALR grammar, and Bison generates its parser. `tools/generate_slr_grammar.py` is build-time tooling that projects the shared arithmetic/assignment productions from that grammar into a generated header for the C SLR implementation. `app.py` is Python Flask routing; `lalr_automaton.py` is a Python adapter that reads the Bison report for UI state inspection; the remaining Python files are build/test/compatibility tooling, not runtime parser algorithms. `slr_parser.py` is a compatibility CLI that delegates to `build/slr_parser`.

## Known scope

This project compares SLR and LALR; it does not implement CLR. State inspection is provided as a selectable state list and LR item/action/GOTO details. Flask's built-in server is intended for lab demonstrations, not production deployment.
