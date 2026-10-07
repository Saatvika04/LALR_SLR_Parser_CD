%{
#include <stdio.h>

int yylex(void);
void yyerror(const char *s);
%}

%token IF ELSE ID NUM ASSIGN PLUS MINUS MULT DIV LT GT LE GE EQ NE LPAREN RPAREN SEMICOLON

%%

program
    : statements
    ;

statements
    : statements statement
    | statement
    ;

statement
    : assignment
    | conditional
    ;

assignment
    : ID ASSIGN expression SEMICOLON
    ;

expression
    : expression PLUS term
    | expression MINUS term
    | term
    ;

term
    : term MULT factor
    | term DIV factor
    | factor
    ;

factor
    : ID
    | NUM
    | LPAREN expression RPAREN
    ;

conditional
    : IF LPAREN condition RPAREN statement
    | IF LPAREN condition RPAREN statement ELSE statement
    ;

condition
    : expression relational_operator expression
    ;

relational_operator
    : LT
    | GT
    | LE
    | GE
    | EQ
    | NE
    ;

%%

void yyerror(const char *s) {
    fprintf(stderr, "Syntax Error: %s\n", s);
}

int main(void) {
    printf("================  LEXICAL ANALYSIS  ================\n");
    int r = yyparse();
    printf("================     PARSING    ================\n");
    printf("Parser: LALR\n");
    printf("Result: %s\n", r == 0 ? "ACCEPTED" : "SYNTAX ERROR");
    return r;
}
