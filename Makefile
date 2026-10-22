BISON ?= bison
FLEX ?= flex
CC ?= gcc
CFLAGS ?= -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -O2
BUILD_DIR ?= build

PARSER_C := $(BUILD_DIR)/lalr_parser.tab.c
PARSER_H := $(BUILD_DIR)/lalr_parser.tab.h
LEXER_C := $(BUILD_DIR)/lex.yy.c
PARSER_BIN := $(BUILD_DIR)/parser
LEXER_BIN := $(BUILD_DIR)/lexer

.PHONY: all test traces clean parser lexer

all: $(PARSER_BIN) $(LEXER_BIN) lalr_parser.output parser lexer

$(BUILD_DIR):
	mkdir -p $@

$(BUILD_DIR)/.bison.stamp: lalr_parser.y | $(BUILD_DIR)
	$(BISON) -v --report=all --report-file=lalr_parser.output --defines=$(PARSER_H) --output=$(PARSER_C) $<
	touch $@

$(PARSER_C) $(PARSER_H): $(BUILD_DIR)/.bison.stamp
	@test -f $@

lalr_parser.output: $(BUILD_DIR)/.bison.stamp
	@test -f $@

$(LEXER_C): lexer.l $(PARSER_H) | $(BUILD_DIR)
	$(FLEX) -o $@ $<

$(PARSER_BIN): parser_driver.c $(PARSER_C) $(PARSER_H) $(LEXER_C)
	$(CC) $(CFLAGS) -I$(BUILD_DIR) parser_driver.c $(PARSER_C) $(LEXER_C) -o $@

$(LEXER_BIN): lexer_driver.c $(PARSER_H) $(LEXER_C)
	$(CC) $(CFLAGS) -I$(BUILD_DIR) lexer_driver.c $(LEXER_C) -o $@

parser: $(PARSER_BIN)
	@if [ -e parser ]; then echo "Keeping existing ./parser; use $(PARSER_BIN) for this build"; else ln -s $(PARSER_BIN) parser; fi

lexer: $(LEXER_BIN)
	@if [ -e lexer ]; then echo "Keeping existing ./lexer; use $(LEXER_BIN) for this build"; else ln -s $(LEXER_BIN) lexer; fi

test: all
	python3 tests/test_lalr_trace.py --parser $(PARSER_BIN)
	python3 tests/test_lalr_automaton.py
	python3 tests/test_slr_parser.py
	bash test_lexer.sh

traces: $(PARSER_BIN)
	python3 tests/test_lalr_trace.py --parser $(PARSER_BIN)

clean:
	rm -rf $(BUILD_DIR)
