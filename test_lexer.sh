#!/bin/bash

echo "Test 1: x = 10;"
echo 'x = 10;' | ./lexer
echo

echo "Test 2: x = 10 + 20 * 3;"
echo 'x = 10 + 20 * 3;' | ./lexer
echo

echo "Test 3: x = (10 + 20) * 3;"
echo 'x = (10 + 20) * 3;' | ./lexer
echo

echo "Test 4: if (x > 10) y = x + 5;"
echo 'if (x > 10) y = x + 5;' | ./lexer
echo

echo "Test 5: x = 10 + * 20;"
echo 'x = 10 + * 20;' | ./lexer
