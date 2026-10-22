%option noyywrap noinput nounput
%{
#include <stdio.h>
#include "lalr_parser.tab.h"
%}

digit   [0-9]
letter  [a-zA-Z_]
id      {letter}({letter}|{digit})*
utf8char ([\xC2-\xDF][\x80-\xBF]|[\xE0][\xA0-\xBF][\x80-\xBF]|[\xE1-\xEC\xEE\xEF][\x80-\xBF]{2}|[\xED][\x80-\x9F][\x80-\xBF]|[\xF0][\x90-\xBF][\x80-\xBF]{2}|[\xF1-\xF3][\x80-\xBF]{3}|[\xF4][\x80-\x8F][\x80-\xBF]{2})

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
{utf8char}   { return INVALID; }
.            { return INVALID; }

%%
