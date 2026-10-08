#include <stdio.h>
#include "lalr_parser.tab.h"

int yylex(void);
extern char *yytext;

int main(void)
{
    int token;
    while ((token = yylex()) != 0)
    {
        switch (token)
        {
            case IF:
                printf("IF(%s)\n", yytext);
                break;
            case ELSE:
                printf("ELSE(%s)\n", yytext);
                break;
            case ID:
                printf("ID(%s)\n", yytext);
                break;
            case NUM:
                printf("NUM(%s)\n", yytext);
                break;
            case ASSIGN:
                printf("ASSIGN(%s)\n", yytext);
                break;
            case PLUS:
                printf("PLUS(%s)\n", yytext);
                break;
            case MINUS:
                printf("MINUS(%s)\n", yytext);
                break;
            case MULT:
                printf("MULT(%s)\n", yytext);
                break;
            case DIV:
                printf("DIV(%s)\n", yytext);
                break;
            case LT:
                printf("LT(%s)\n", yytext);
                break;
            case GT:
                printf("GT(%s)\n", yytext);
                break;
            case LE:
                printf("LE(%s)\n", yytext);
                break;
            case GE:
                printf("GE(%s)\n", yytext);
                break;
            case EQ:
                printf("EQ(%s)\n", yytext);
                break;
            case NE:
                printf("NE(%s)\n", yytext);
                break;
            case LPAREN:
                printf("LPAREN(%s)\n", yytext);
                break;
            case RPAREN:
                printf("RPAREN(%s)\n", yytext);
                break;
            case SEMICOLON:
                printf("SEMICOLON(%s)\n", yytext);
                break;
            default:
                printf("UNKNOWN(%s)\n", yytext);
                break;
        }
    }
    return 0;
}
