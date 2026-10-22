# LALR and SLR Parser Visualizer

Compiler Design Lab project comparing a Bison LALR parser with the existing Python SLR parser and Flask visualization.

## Dependencies and build

Install Bison, Flex, GCC, GNU Make, and Python 3. The web application also needs Flask:

```sh
python3 -m pip install -r requirements.txt
make
```

`make` generates the Bison parser and verbose report, runs Flex, and builds the executables under `build/`. The report is written to `lalr_parser.output`. Generated C files and binaries go under `build/` so pre-existing untracked files in the project root are preserved. On a clean checkout, `make` also creates `./parser` and `./lexer` symlinks to the build outputs; if either root path already exists, it is left untouched and the `build/` path is printed. The build invokes Bison with its verbose report option (`-v`) and explicit output paths for that reason.

## Parser CLI

Use the built executable (or `./parser` if `make` created the convenience symlink):

```sh
build/parser                 # Review 1 text output
build/parser --json < input.txt
build/parser --table         # print lalr_parser.output
build/lexer < input.txt      # standalone lexer
```

The existing root-level `parser`, `lexer`, and generated C files in this workspace are untracked local artifacts and are intentionally left untouched. The supported build outputs are `build/parser` and `build/lexer`.

JSON mode writes one JSON object to stdout. The `steps` array records Bison's actual parser debug events with the stack after each operation. `SHIFT` contains the shifted token; `REDUCE` contains the production and the resulting GOTO state. The end marker is represented as `$` in remaining input; Bison's internal end-marker transition appears in the final ACCEPT stack. `stats` counts emitted SHIFT, REDUCE, and ERROR records, excluding Bison's internal end-marker shift.

## Tests and saved traces

Run the parser, automaton, SLR regression, and lexer checks with:

```sh
make test
```

The LALR test harness runs all seven required inputs through the compiled executable, checks JSON and trace consistency, verifies multiplication precedence and dangling-`else` handling, and writes real executable output to `traces/`. The saved files are:

- `traces/01_simple_assignment.json`
- `traces/02_precedence.json`
- `traces/03_parentheses.json`
- `traces/04_conditional.json`
- `traces/05_invalid_operator.json`
- `traces/06_empty_input.json`
- `traces/07_missing_rhs.json`

The harness also checks incomplete expressions, unexpected characters, `--table`, and invalid CLI arguments.

## Grammar conflict

Bison reports one shift/reduce conflict in state 40 for the dangling `else`. The existing grammar is preserved. Bison's default shift resolution associates `else` with the nearest unmatched `if`; the test suite includes a nested conditional demonstrating that behavior. The report records the conflict and its shift/reduce derivation.

## Flask visualization

After building and installing Flask, run:

```sh
python3 app.py
```

The `/parse` endpoint keeps the existing SLR behavior and sends LALR requests to `build/parser --json` using an argument list and stdin (no shell command interpolation). `/automaton?mode=slr` keeps the existing SLR table; `/automaton?mode=lalr` adapts `lalr_parser.output` to the frontend's table and state-diagram format. Set `LALR_PARSER` to an alternate parser executable if needed. The frontend reloads the grammar, table, and diagram when parsing mode changes.
