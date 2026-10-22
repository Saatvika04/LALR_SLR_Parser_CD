#!/bin/bash
set -euo pipefail

LEXER_BIN="${LEXER_BIN:-./build/lexer}"
if [[ ! -x "$LEXER_BIN" ]]; then
    LEXER_BIN=./lexer
fi

echo "Test 1: x = 10;"
echo 'x = 10;' | "$LEXER_BIN"
echo

echo "Test 2: x = 10 + 20 * 3;"
echo 'x = 10 + 20 * 3;' | "$LEXER_BIN"
echo

echo "Test 3: x = (10 + 20) * 3;"
echo 'x = (10 + 20) * 3;' | "$LEXER_BIN"
echo

echo "Test 4: if (x > 10) y = x + 5;"
echo 'if (x > 10) y = x + 5;' | "$LEXER_BIN"
echo

echo "Test 5: x = 10 + * 20;"
echo 'x = 10 + * 20;' | "$LEXER_BIN"
