%option noyywrap noinput nounput
%{
#include <stdio.h>
#include "lalr_parser.tab.h"
%}

digit   [0-9]
letter  [a-zA-Z_]
id      {letter}({letter}|{digit})*

%%

[ \t\r\n]+   { }
"if"         { return IF; }
"else"       { return ELSE; }
{id}         { return ID; }
{digit}+     { return NUM; }
"="          { return ASSIGN; }
"+"          { return PLUS; }
"-"          { return MINUS; }
"*"          { return MULT; }
"/"          { return DIV; }
"<="         { return LE; }
">="         { return GE; }
"=="         { return EQ; }
"!="         { return NE; }
"<"          { return LT; }
">"          { return GT; }
"("          { return LPAREN; }
")"          { return RPAREN; }
";"          { return SEMICOLON; }
.            { fprintf(stderr, "LEXICAL ERROR: unexpected character '%s'\n", yytext); }

%%
