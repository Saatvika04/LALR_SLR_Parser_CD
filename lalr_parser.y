%{
#include <stdio.h>
int yylex(void);
void yyerror(const char *s);
%}

%define parse.trace

%token IF ELSE ID NUM ASSIGN PLUS MINUS MULT DIV LT GT LE GE EQ NE LPAREN RPAREN SEMICOLON INVALID

%%

program : statements ;
statements : statements statement | statement ;
statement : assignment | conditional ;
assignment : ID ASSIGN expression SEMICOLON ;
expression : expression PLUS term | expression MINUS term | term ;
term : term MULT factor | term DIV factor | factor ;
factor : ID | NUM | LPAREN expression RPAREN ;
conditional : IF LPAREN condition RPAREN statement | IF LPAREN condition RPAREN statement ELSE statement ;
condition : expression relational_operator expression ;
relational_operator : LT | GT | LE | GE | EQ | NE ;

%%
