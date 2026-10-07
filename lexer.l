%option noyywrap noinput nounput
%{
#include <stdio.h>
#include "lalr_parser.tab.h"
%}

digit   [0-9]
letter  [a-zA-Z_]
id      {letter}({letter}|{digit})*

%%

[ \t\r\n]+   { /* skip whitespace */ }

"if"         { printf("IF ");   return IF; }
"else"       { printf("ELSE "); return ELSE; }

{id}         { printf("ID(%s) ", yytext); return ID; }
{digit}+     { printf("NUM(%s) ", yytext); return NUM; }

"="          { printf("ASSIGN "); return ASSIGN; }
"+"          { printf("PLUS ");   return PLUS; }
"-"          { printf("MINUS ");  return MINUS; }
"*"          { printf("MULT ");   return MULT; }
"/"          { printf("DIV ");    return DIV; }

"<="         { printf("LE "); return LE; }
">="         { printf("GE "); return GE; }
"=="         { printf("EQ "); return EQ; }
"!="         { printf("NE "); return NE; }
"<"          { printf("LT "); return LT; }
">"          { printf("GT "); return GT; }

"("          { printf("LPAREN "); return LPAREN; }
")"          { printf("RPAREN "); return RPAREN; }
";"          { printf("SEMICOLON "); return SEMICOLON; }

.            { /* ignore any other character */ }

%%
